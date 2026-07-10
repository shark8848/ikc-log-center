"""Token-based authentication: generation, storage, and verification.

Token storage follows ``LOG_CENTER_STORE`` backend:
- SQLite / PostgreSQL / MySQL → ``api_tokens`` table
- Elasticsearch → dedicated index ``log-center-tokens`` (refresh=true on writes)

Tokens are stored as SHA-256 hashes; plaintext is only shown once at generation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .storage import (
    DB_PATH,
    ES_AUTH,
    ES_ENDPOINT,
    ES_VERIFY_SSL,
    MYSQL_DSN,
    PG_DSN,
    STORE_BACKEND,
)

logger = logging.getLogger("log_center.auth")

AUTH_ENABLED = os.getenv("LOG_CENTER_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")

ES_TOKEN_INDEX = "log_center_tokens"

# ---------------------------------------------------------------------------
# In-memory cache for fast verify (loaded lazily)
# ---------------------------------------------------------------------------

_cache: set[str] | None = None


def invalidate_cache() -> None:
    """Force reload of active token hashes on next verify."""
    global _cache
    _cache = None


def _load_cache() -> set[str]:
    global _cache
    if _cache is None:
        if STORE_BACKEND == "es" and ES_ENDPOINT:
            _cache = _load_hashes_es()
        else:
            _cache = _load_hashes_sql()
    return _cache


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def hash_token(plain: str) -> str:
    """SHA-256 hash of a token string."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def generate_token(description: str = "") -> tuple[str, dict[str, Any]]:
    """Generate a new ``sk-lc-<48 hex>`` token.

    Returns ``(plaintext, info_dict)``.  The plaintext is shown only once.
    """
    raw = secrets.token_hex(24)  # 48 hex chars
    plain = f"sk-lc-{raw}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    info: dict[str, Any] = {
        "token_hash": hash_token(plain),
        "prefix": plain[:10],
        "description": description,
        "created_at": now,
        "active": True,
    }
    return plain, info


# ---------------------------------------------------------------------------
# Public API — dispatches by backend
# ---------------------------------------------------------------------------


def init_token_store() -> None:
    """Create token table / index if not exists (idempotent)."""
    if STORE_BACKEND == "es" and ES_ENDPOINT:
        _init_es()
    else:
        _init_sql()


def add_token(info: dict[str, Any]) -> None:
    """Persist a new token to the backend."""
    if STORE_BACKEND == "es" and ES_ENDPOINT:
        _add_es(info)
    else:
        _add_sql(info)
    invalidate_cache()


def verify_token(plain: str) -> bool:
    """Return True if *plain* is a valid, active token."""
    if not plain:
        return False
    h = hash_token(plain)
    return h in _load_cache()


def revoke_token(prefix: str) -> bool:
    """Disable token(s) matching *prefix*.  Returns True if any were revoked."""
    if STORE_BACKEND == "es" and ES_ENDPOINT:
        ok = _revoke_es(prefix)
    else:
        ok = _revoke_sql(prefix)
    if ok:
        invalidate_cache()
    return ok


def list_tokens() -> list[dict[str, Any]]:
    """Return all tokens (metadata only, no hashes exposed)."""
    if STORE_BACKEND == "es" and ES_ENDPOINT:
        return _list_es()
    return _list_sql()


# ===================================================================
# SQL backends (SQLite / PostgreSQL / MySQL)
# ===================================================================

_SQL_DDL = {
    "sqlite": (
        "CREATE TABLE IF NOT EXISTS api_tokens ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  token_hash TEXT NOT NULL UNIQUE,"
        "  prefix TEXT NOT NULL,"
        "  description TEXT,"
        "  created_at TEXT NOT NULL,"
        "  active INTEGER NOT NULL DEFAULT 1"
        ")"
    ),
    "pg": (
        "CREATE TABLE IF NOT EXISTS api_tokens ("
        "  id BIGSERIAL PRIMARY KEY,"
        "  token_hash TEXT NOT NULL UNIQUE,"
        "  prefix TEXT NOT NULL,"
        "  description TEXT,"
        "  created_at TEXT NOT NULL,"
        "  active BOOLEAN NOT NULL DEFAULT TRUE"
        ")"
    ),
    "mysql": (
        "CREATE TABLE IF NOT EXISTS api_tokens ("
        "  id BIGINT PRIMARY KEY AUTO_INCREMENT,"
        "  token_hash VARCHAR(64) NOT NULL UNIQUE,"
        "  prefix VARCHAR(16) NOT NULL,"
        "  description TEXT,"
        "  created_at VARCHAR(32) NOT NULL,"
        "  active TINYINT(1) NOT NULL DEFAULT 1"
        ")"
    ),
}


def _get_sql_backend() -> str:
    """Return the SQL backend name: 'sqlite', 'pg', or 'mysql'."""
    b = STORE_BACKEND
    if b in {"local", "sqlite"}:
        return "sqlite"
    if b == "pg":
        return "pg"
    if b == "mysql":
        return "mysql"
    return "sqlite"  # fallback


def _connect_sql():
    """Return a connection object for the current SQL backend."""
    backend = _get_sql_backend()
    if backend == "pg":
        import psycopg
        return psycopg.connect(**{k: v for k, v in PG_DSN.items() if v is not None})
    if backend == "mysql":
        dsn = {k: v for k, v in MYSQL_DSN.items() if v is not None}
        try:
            import mysql.connector as mc
            return mc.connect(**dsn)
        except ImportError:
            import pymysql
            return pymysql.connect(**dsn)
    # sqlite
    return sqlite3.connect(str(DB_PATH))


def _init_sql() -> None:
    backend = _get_sql_backend()
    ddl = _SQL_DDL.get(backend, _SQL_DDL["sqlite"])
    conn = _connect_sql()
    try:
        if backend == "sqlite":
            conn.execute(ddl)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tokens_hash ON api_tokens(token_hash)")
            conn.commit()
        elif backend == "pg":
            with conn.cursor() as cur:
                cur.execute(ddl)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_hash ON api_tokens(token_hash)")
            conn.commit()
        else:  # mysql
            cur = conn.cursor()
            cur.execute(ddl)
            try:
                cur.execute("CREATE INDEX idx_tokens_hash ON api_tokens(token_hash)")
            except Exception:
                pass  # index may already exist
            conn.commit()
            cur.close()
    finally:
        conn.close()


def _add_sql(info: dict[str, Any]) -> None:
    conn = _connect_sql()
    backend = _get_sql_backend()
    sql = "INSERT INTO api_tokens (token_hash, prefix, description, created_at, active) VALUES (%s,%s,%s,%s,%s)"
    if backend == "sqlite":
        sql = sql.replace("%s", "?")
    active_val = True if backend == "pg" else 1
    vals = (info["token_hash"], info["prefix"], info.get("description", ""), info["created_at"], active_val)
    try:
        if backend == "sqlite":
            conn.execute(sql, vals)
            conn.commit()
        elif backend == "pg":
            with conn.cursor() as cur:
                cur.execute(sql, vals)
            conn.commit()
        else:
            cur = conn.cursor()
            cur.execute(sql, vals)
            conn.commit()
            cur.close()
    finally:
        conn.close()


def _verify_sql(token_hash: str) -> bool:
    conn = _connect_sql()
    backend = _get_sql_backend()
    if backend == "pg":
        sql = "SELECT 1 FROM api_tokens WHERE token_hash = %s AND active = TRUE LIMIT 1"
    else:
        sql = "SELECT 1 FROM api_tokens WHERE token_hash = %s AND active = 1 LIMIT 1"
    if backend == "sqlite":
        sql = sql.replace("%s", "?")
    try:
        if backend == "sqlite":
            row = conn.execute(sql, (token_hash,)).fetchone()
        elif backend == "pg":
            with conn.cursor() as cur:
                cur.execute(sql, (token_hash,))
                row = cur.fetchone()
        else:
            cur = conn.cursor()
            cur.execute(sql, (token_hash,))
            row = cur.fetchone()
            cur.close()
        return row is not None
    finally:
        conn.close()


def _revoke_sql(prefix: str) -> bool:
    conn = _connect_sql()
    backend = _get_sql_backend()
    if backend == "pg":
        sql = "UPDATE api_tokens SET active = FALSE WHERE prefix = %s AND active = TRUE"
    else:
        sql = "UPDATE api_tokens SET active = 0 WHERE prefix = %s AND active = 1"
    if backend == "sqlite":
        sql = sql.replace("%s", "?")
    try:
        if backend == "sqlite":
            cur = conn.execute(sql, (prefix,))
            conn.commit()
            changed = cur.rowcount
        elif backend == "pg":
            with conn.cursor() as cur:
                cur.execute(sql, (prefix,))
                changed = cur.rowcount
            conn.commit()
        else:
            cur = conn.cursor()
            cur.execute(sql, (prefix,))
            changed = cur.rowcount
            conn.commit()
            cur.close()
        return changed > 0
    finally:
        conn.close()


def _list_sql() -> list[dict[str, Any]]:
    conn = _connect_sql()
    backend = _get_sql_backend()
    sql = "SELECT prefix, description, created_at, active FROM api_tokens ORDER BY created_at DESC"
    try:
        if backend == "sqlite":
            rows = conn.execute(sql).fetchall()
            cols = ["prefix", "description", "created_at", "active"]
        elif backend == "pg":
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
            cols = ["prefix", "description", "created_at", "active"]
        else:
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            cols = ["prefix", "description", "created_at", "active"]
        result = []
        for r in rows:
            d = dict(zip(cols, r))
            # Normalize active to bool
            d["active"] = bool(d["active"])
            result.append(d)
        return result
    finally:
        conn.close()


def _load_hashes_sql() -> set[str]:
    """Load active token hashes for the verify cache."""
    conn = _connect_sql()
    backend = _get_sql_backend()
    if backend == "pg":
        sql = "SELECT token_hash FROM api_tokens WHERE active = TRUE"
    else:
        sql = "SELECT token_hash FROM api_tokens WHERE active = 1"
    try:
        if backend == "sqlite":
            rows = conn.execute(sql).fetchall()
        elif backend == "pg":
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        else:
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
        return {r[0] for r in rows}
    finally:
        conn.close()


# ===================================================================
# Elasticsearch backend
# ===================================================================

def _es_url(path: str) -> str:
    return f"{ES_ENDPOINT.rstrip('/')}/{ES_TOKEN_INDEX}/{path}"


def _es_request(method: str, path: str, **kwargs):
    import requests
    kwargs.setdefault("auth", ES_AUTH)
    kwargs.setdefault("verify", ES_VERIFY_SSL)
    kwargs.setdefault("timeout", 5)
    kwargs.setdefault("headers", {"Content-Type": "application/json"})
    resp = requests.request(method, _es_url(path), **kwargs)
    return resp


def _init_es() -> None:
    """Create the token index with explicit mapping if it doesn't exist."""
    import requests
    base = f"{ES_ENDPOINT.rstrip('/')}/{ES_TOKEN_INDEX}"
    resp = requests.head(base, auth=ES_AUTH, verify=ES_VERIFY_SSL, timeout=5)
    if resp.status_code == 200:
        return
    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "1s"},
        "mappings": {
            "properties": {
                "token_hash": {"type": "keyword"},
                "prefix": {"type": "keyword"},
                "description": {"type": "text"},
                "created_at": {"type": "date", "format": "strict_date_time"},
                "active": {"type": "boolean"},
            }
        },
    }
    requests.put(base, json=mapping, auth=ES_AUTH, verify=ES_VERIFY_SSL,
                 headers={"Content-Type": "application/json"}, timeout=5)


def _add_es(info: dict[str, Any]) -> None:
    _es_request("POST", "_doc?refresh=true", json=info)


def _verify_es(token_hash: str) -> bool:
    body = {"query": {"bool": {"must": [
        {"term": {"token_hash": token_hash}},
        {"term": {"active": True}},
    ]}}}
    resp = _es_request("POST", "_search", json=body)
    data = resp.json()
    return data.get("hits", {}).get("total", {}).get("value", 0) > 0


def _revoke_es(prefix: str) -> bool:
    """Find docs with matching prefix and set active=false."""
    search = {"query": {"term": {"prefix": prefix}}, "size": 100}
    resp = _es_request("POST", "_search", json=search)
    hits = resp.json().get("hits", {}).get("hits", [])
    if not hits:
        return False
    for h in hits:
        _es_request("POST", f"_update/{h['_id']}?refresh=true",
                    json={"doc": {"active": False}})
    return True


def _list_es() -> list[dict[str, Any]]:
    body = {"query": {"match_all": {}}, "size": 200, "sort": [{"created_at": "desc"}]}
    resp = _es_request("POST", "_search", json=body)
    hits = resp.json().get("hits", {}).get("hits", [])
    result = []
    for h in hits:
        s = h.get("_source", {})
        result.append({
            "prefix": s.get("prefix", ""),
            "description": s.get("description", ""),
            "created_at": s.get("created_at", ""),
            "active": s.get("active", True),
        })
    return result


def _load_hashes_es() -> set[str]:
    """Load active token hashes for the verify cache."""
    body = {"query": {"term": {"active": True}}, "_source": ["token_hash"], "size": 200}
    resp = _es_request("POST", "_search", json=body)
    hits = resp.json().get("hits", {}).get("hits", [])
    return {h["_source"]["token_hash"] for h in hits if h.get("_source", {}).get("token_hash")}


# ===================================================================
# Backend info (for CLI display)
# ===================================================================


def backend_description() -> str:
    """Human-readable description of the current token storage backend."""
    b = STORE_BACKEND
    if b in {"local", "sqlite"}:
        return f"sqlite ({DB_PATH})"
    if b == "pg":
        h, p, db = PG_DSN.get("host", ""), PG_DSN.get("port", 5432), PG_DSN.get("dbname", "")
        return f"pg ({h}:{p}/{db})"
    if b == "mysql":
        h, p, db = MYSQL_DSN.get("host", ""), MYSQL_DSN.get("port", 3306), MYSQL_DSN.get("database", "")
        return f"mysql ({h}:{p}/{db})"
    if b == "es" and ES_ENDPOINT:
        return f"es ({ES_ENDPOINT}/{ES_TOKEN_INDEX})"
    return f"sqlite ({DB_PATH})"
