"""Storage backends: local file, SQLite, MySQL, PostgreSQL, Elasticsearch.

All storage I/O is extracted from the FastAPI app so it can be shared
across HTTP, gRPC, and Celery ingestion paths.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import requests

# Optional dependencies — graceful degradation
try:
    import psycopg
except ImportError:
    psycopg = None  # type: ignore[assignment]

try:
    import mysql.connector as mysql_connector
except ImportError:
    mysql_connector = None  # type: ignore[assignment]

try:
    import pymysql
except ImportError:
    pymysql = None  # type: ignore[assignment]

logger = logging.getLogger("log_center.storage")

# ---------------------------------------------------------------------------
# Configuration (all LOG_CENTER_* env vars)
# ---------------------------------------------------------------------------

LOG_PATH = Path(os.getenv("LOG_CENTER_FILE", "logs/log_center.log"))
DB_PATH = Path(os.getenv("LOG_CENTER_DB_PATH", "data/log_center/log_center.db"))
STORE_BACKEND = (os.getenv("LOG_CENTER_STORE") or "local").lower()
MAX_LOCAL_BYTES = int(float(os.getenv("LOG_CENTER_MAX_LOCAL_MB", "500")) * 1024 * 1024)
FORWARD_URLS = [u.strip() for u in os.getenv("LOG_CENTER_FORWARD_URLS", "").split(",") if u.strip()]

MYSQL_DSN = {
    "host": os.getenv("LOG_CENTER_MYSQL_HOST"),
    "port": int(os.getenv("LOG_CENTER_MYSQL_PORT", "3306")),
    "user": os.getenv("LOG_CENTER_MYSQL_USER"),
    "password": os.getenv("LOG_CENTER_MYSQL_PASSWORD"),
    "database": os.getenv("LOG_CENTER_MYSQL_DB"),
}
PG_DSN = {
    "host": os.getenv("LOG_CENTER_PG_HOST"),
    "port": int(os.getenv("LOG_CENTER_PG_PORT", "5432")),
    "user": os.getenv("LOG_CENTER_PG_USER"),
    "password": os.getenv("LOG_CENTER_PG_PASSWORD"),
    "dbname": os.getenv("LOG_CENTER_PG_DB"),
}
ES_ENDPOINT = os.getenv("LOG_CENTER_ES_ENDPOINT")
ES_INDEX = os.getenv("LOG_CENTER_ES_INDEX", "log-center")
ES_USER = os.getenv("LOG_CENTER_ES_USER")
ES_PASSWORD = os.getenv("LOG_CENTER_ES_PASSWORD")
ES_VERIFY_SSL = os.getenv("LOG_CENTER_ES_VERIFY_SSL", "true").lower() in ("true", "1", "yes")

ES_AUTH = (ES_USER, ES_PASSWORD) if ES_USER and ES_PASSWORD else None

# Ensure directories exist
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def normalize_entries(entries: list[dict[str, Any]], trace_id_hint: str | None = None) -> list[dict[str, Any]]:
    """Filter non-dict entries and inject trace_id_hint where missing."""
    normed: list[dict[str, Any]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if trace_id_hint and not e.get("trace_id"):
            e["trace_id"] = trace_id_hint
        normed.append(e)
    return normed


# ---------------------------------------------------------------------------
# Local file (always active)
# ---------------------------------------------------------------------------


def write_file(entries: list[dict[str, Any]]) -> None:
    """Append JSON-lines to local file; truncate when exceeding MAX_LOCAL_BYTES."""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOCAL_BYTES:
            LOG_PATH.write_text("")
    except Exception:
        pass
    with LOG_PATH.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

_sqlite_initialized = False


def init_sqlite() -> None:
    """Create SQLite table and index if they don't exist."""
    global _sqlite_initialized
    if _sqlite_initialized:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            level TEXT,
            logger TEXT,
            message TEXT,
            trace_id TEXT,
            span_id TEXT,
            parent_id TEXT,
            payload TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_trace ON logs(trace_id)")
    conn.commit()
    conn.close()
    _sqlite_initialized = True


def write_sqlite(entries: list[dict[str, Any]]) -> None:
    """Batch insert entries into SQLite."""
    if not DB_PATH:
        return
    conn = sqlite3.connect(DB_PATH)
    rows = [
        (
            e.get("ts"),
            e.get("level"),
            e.get("logger"),
            e.get("message"),
            e.get("trace_id"),
            e.get("span_id"),
            e.get("parent_id"),
            json.dumps(e, ensure_ascii=False),
        )
        for e in entries
    ]
    conn.executemany(
        "INSERT INTO logs (ts, level, logger, message, trace_id, span_id, parent_id, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# MySQL (optional)
# ---------------------------------------------------------------------------


def write_mysql(entries: list[dict[str, Any]]) -> None:
    """Batch insert into MySQL — supports mysql-connector-python and pymysql."""
    if not MYSQL_DSN.get("host"):
        return
    dsn = {k: v for k, v in MYSQL_DSN.items() if v is not None}
    if mysql_connector:
        conn = mysql_connector.connect(**dsn)
    elif pymysql:
        conn = pymysql.connect(**dsn)
    else:
        return
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            ts VARCHAR(64),
            level VARCHAR(16),
            logger VARCHAR(128),
            message TEXT,
            trace_id VARCHAR(128),
            span_id VARCHAR(128),
            parent_id VARCHAR(128),
            payload JSON
        )
        """
    )
    rows = [
        (
            e.get("ts"),
            e.get("level"),
            e.get("logger"),
            e.get("message"),
            e.get("trace_id"),
            e.get("span_id"),
            e.get("parent_id"),
            json.dumps(e, ensure_ascii=False),
        )
        for e in entries
    ]
    cur.executemany(
        "INSERT INTO logs (ts, level, logger, message, trace_id, span_id, parent_id, payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        rows,
    )
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# PostgreSQL (optional)
# ---------------------------------------------------------------------------


def write_pg(entries: list[dict[str, Any]]) -> None:
    """Batch insert into PostgreSQL — requires psycopg."""
    if not psycopg:
        return
    if not PG_DSN.get("host"):
        return
    with psycopg.connect(**PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id BIGSERIAL PRIMARY KEY,
                    ts TEXT,
                    level TEXT,
                    logger TEXT,
                    message TEXT,
                    trace_id TEXT,
                    span_id TEXT,
                    parent_id TEXT,
                    payload JSONB
                );
                """
            )
            rows = [
                (
                    e.get("ts"),
                    e.get("level"),
                    e.get("logger"),
                    e.get("message"),
                    e.get("trace_id"),
                    e.get("span_id"),
                    e.get("parent_id"),
                    json.dumps(e, ensure_ascii=False),
                )
                for e in entries
            ]
            cur.executemany(
                "INSERT INTO logs (ts, level, logger, message, trace_id, span_id, parent_id, payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                rows,
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Elasticsearch (optional, uses requests)
# ---------------------------------------------------------------------------


def write_es(entries: list[dict[str, Any]]) -> None:
    """Bulk insert into Elasticsearch via _bulk API."""
    if not ES_ENDPOINT:
        return
    try:
        lines: list[str] = []
        for e in entries:
            doc = dict(e)
            # Map 'ts' to '@timestamp' for data stream compatibility
            if "ts" in doc and "@timestamp" not in doc:
                doc["@timestamp"] = doc["ts"]
            lines.append(f'{{"create":{{}}}}\n{json.dumps(doc, ensure_ascii=False)}\n')
        resp = requests.post(
            f"{ES_ENDPOINT.rstrip('/')}/{ES_INDEX}/_bulk",
            data="".join(lines),
            headers={"Content-Type": "application/x-ndjson"},
            auth=ES_AUTH,
            verify=ES_VERIFY_SSL,
            timeout=5,
        )
        data = resp.json()
        if data.get("errors"):
            for item in data.get("items", []):
                op = item.get("create") or item.get("index") or {}
                if op.get("error"):
                    logger.warning("ES write error: %s", op["error"].get("reason", op["error"]))
                    break
    except Exception as exc:
        logger.warning("ES write failed: %s", exc)


# ---------------------------------------------------------------------------
# Backend dispatch
# ---------------------------------------------------------------------------


def write_backend(entries: list[dict[str, Any]]) -> None:
    """Dispatch to the configured storage backend."""
    backend = STORE_BACKEND
    if backend in {"local", "sqlite"}:
        write_sqlite(entries)
    if backend == "mysql":
        write_mysql(entries)
    if backend == "pg":
        write_pg(entries)
    if backend == "es":
        write_es(entries)


# ---------------------------------------------------------------------------
# Forwarding
# ---------------------------------------------------------------------------


def forward_entries(entries: list[dict[str, Any]]) -> None:
    """POST entries to all configured forward URLs (best-effort)."""
    if not FORWARD_URLS:
        return
    for url in FORWARD_URLS:
        try:
            requests.post(f"{url.rstrip('/')}/ingest", json=entries, timeout=2)
        except Exception:
            continue
