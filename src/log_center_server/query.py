"""ORM models and query helpers for log_center search.

Supports all storage backends: SQLite, PostgreSQL, MySQL (via SQLAlchemy),
and Elasticsearch (via REST API).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Column, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import Session, declarative_base

from .storage import (
    DB_PATH,
    ES_ENDPOINT,
    ES_INDEX,
    ES_AUTH,
    ES_VERIFY_SSL,
    MYSQL_DSN,
    PG_DSN,
    STORE_BACKEND,
)

# ---------------------------------------------------------------------------
# Dynamic DB URL for SQLAlchemy-based backends
# ---------------------------------------------------------------------------

if STORE_BACKEND == "pg" and PG_DSN.get("host"):
    _pg = PG_DSN
    _cred = f"{_pg.get('user', '')}:{_pg.get('password', '')}" if _pg.get("user") else ""
    DB_URL = f"postgresql+psycopg://{_cred}@{_pg['host']}:{_pg.get('port', 5432)}/{_pg.get('dbname', '')}"
elif STORE_BACKEND == "mysql" and MYSQL_DSN.get("host"):
    _my = MYSQL_DSN
    _cred = f"{_my.get('user', '')}:{_my.get('password', '')}" if _my.get("user") else ""
    # Prefer mysqlconnector, fall back to pymysql
    try:
        import mysql.connector  # noqa: F401
        _mysql_driver = "mysqlconnector"
    except ImportError:
        _mysql_driver = "pymysql"
    DB_URL = f"mysql+{_mysql_driver}://{_cred}@{_my['host']}:{_my.get('port', 3306)}/{_my.get('database', '')}"
else:
    DB_URL = f"sqlite+pysqlite:///{DB_PATH}"

Base = declarative_base()


# ---------------------------------------------------------------------------
# SQLAlchemy ORM model
# ---------------------------------------------------------------------------


class LogEntry(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    ts = Column(String(64))
    level = Column(String(16))
    logger = Column(String(128))
    message = Column(Text)
    trace_id = Column(String(128))
    span_id = Column(String(128))
    parent_id = Column(String(128))
    source_ip = Column(String(64))
    payload = Column(Text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_payload(raw: Any) -> Any:
    """Parse stored payload JSON; fall back to raw when parsing fails."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        if "payload" in raw:
            return raw.get("payload")
        return raw
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "payload" in parsed:
            return parsed.get("payload")
        return parsed
    except Exception:
        return raw


def _payload_only(entry: Any) -> dict[str, Any]:
    """Return structured payload alongside outer metadata fields."""
    payload = _parse_payload(entry.payload)
    return {
        "ts": entry.ts,
        "level": entry.level,
        "logger": entry.logger,
        "message": entry.message,
        "trace_id": entry.trace_id,
        "span_id": entry.span_id,
        "parent_id": entry.parent_id,
        "payload": payload,
    }


def _hit_to_dict(hit: dict[str, Any]) -> dict[str, Any]:
    """Convert an Elasticsearch hit to the standard dict format.

    Returns all ``_source`` fields so that extras like ``exc_info``,
    ``user``, ``ip``, etc. are preserved.
    """
    s = hit.get("_source", {})
    # Ensure canonical keys always present (even if None)
    result: dict[str, Any] = {
        "ts": s.get("ts"),
        "level": s.get("level"),
        "logger": s.get("logger"),
        "message": s.get("message"),
        "trace_id": s.get("trace_id"),
        "span_id": s.get("span_id"),
        "parent_id": s.get("parent_id"),
        "payload": s.get("payload"),
    }
    # Merge remaining source fields (exc_info, extra attrs, …)
    for k, v in s.items():
        if k not in result and k != "@timestamp":
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# SQL query (SQLite / PostgreSQL / MySQL via SQLAlchemy)
# ---------------------------------------------------------------------------


def _query_sql(
    trace_id: str = "",
    level: str = "",
    message_substr: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query logs from SQL backends using SQLAlchemy ORM."""
    engine = create_engine(DB_URL, echo=False, future=True)
    Base.metadata.create_all(engine)

    stmt = select(LogEntry).order_by(LogEntry.id.desc()).limit(limit)
    conditions = []
    if trace_id:
        conditions.append(LogEntry.trace_id == trace_id.strip())
    if level:
        conditions.append(LogEntry.level == level.strip())
    if message_substr:
        conditions.append(func.lower(LogEntry.message).like(f"%{message_substr.lower()}%"))
    if conditions:
        stmt = stmt.where(*conditions)

    with Session(engine, future=True) as session:
        rows = session.execute(stmt).scalars().all()
    return [_payload_only(r) for r in rows]


# ---------------------------------------------------------------------------
# Elasticsearch query (via REST API)
# ---------------------------------------------------------------------------


def _query_es(
    trace_id: str = "",
    level: str = "",
    message_substr: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query logs from Elasticsearch via REST API."""
    import requests

    must: list[dict[str, Any]] = []
    if trace_id:
        must.append({"term": {"trace_id.keyword": trace_id.strip()}})
    if level:
        must.append({"term": {"level.keyword": level.strip()}})
    if message_substr:
        must.append({"wildcard": {"message.keyword": {"value": f"*{message_substr}*", "case_insensitive": True}}})

    body: dict[str, Any] = {"size": limit, "sort": [{"_score": "desc"}]}
    if must:
        body["query"] = {"bool": {"must": must}}
    else:
        body["query"] = {"match_all": {}}

    try:
        resp = requests.post(
            f"{ES_ENDPOINT.rstrip('/')}/{ES_INDEX}/_search",
            json=body,
            headers={"Content-Type": "application/json"},
            auth=ES_AUTH,
            verify=ES_VERIFY_SSL,
            timeout=5,
        )
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        return [_hit_to_dict(h) for h in hits]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Public API — dispatches to the correct backend
# ---------------------------------------------------------------------------


def query_logs(
    trace_id: str = "",
    level: str = "",
    message_substr: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query log entries with optional filters.

    Automatically dispatches to the configured storage backend.
    Supports: SQLite, PostgreSQL, MySQL (SQLAlchemy) and Elasticsearch (REST).
    """
    limit = max(1, min(int(limit or 100), 500))

    if STORE_BACKEND == "es" and ES_ENDPOINT:
        return _query_es(trace_id, level, message_substr, limit)

    return _query_sql(trace_id, level, message_substr, limit)


# ---------------------------------------------------------------------------
# Stats (dashboard)
# ---------------------------------------------------------------------------


# Granularity config: (ts_substr_length, es_interval, max_buckets)
_GRANULARITY = {
    "minute": (16, "1m", 60),
    "hour": (13, "1h", 24),
    "day": (10, "1d", 31),
    "month": (7, "1M", 12),
}


def _stats_sql(granularity: str = "hour") -> dict[str, Any]:
    """Compute stats from SQL backends."""
    ts_len, _, max_buckets = _GRANULARITY.get(granularity, _GRANULARITY["hour"])
    engine = create_engine(DB_URL, echo=False, future=True)
    Base.metadata.create_all(engine)

    with Session(engine, future=True) as session:
        total = session.execute(select(func.count(LogEntry.id))).scalar() or 0
        level_rows = session.execute(
            select(LogEntry.level, func.count(LogEntry.id)).group_by(LogEntry.level)
        ).all()
        # Trend grouped by granularity (based on ts string prefix)
        recent_rows = session.execute(
            select(func.substr(LogEntry.ts, 1, ts_len), func.count(LogEntry.id))
            .where(LogEntry.ts.isnot(None))
            .group_by(func.substr(LogEntry.ts, 1, ts_len))
            .order_by(func.substr(LogEntry.ts, 1, ts_len).desc())
            .limit(max_buckets)
        ).all()

    levels = {row[0] or "UNKNOWN": row[1] for row in level_rows}
    trend = [{"time": row[0], "count": row[1]} for row in reversed(recent_rows)]
    return {"total": total, "levels": levels, "trend": trend}


def _stats_es(granularity: str = "hour") -> dict[str, Any]:
    """Compute stats from Elasticsearch."""
    import requests

    _, es_interval, max_buckets = _GRANULARITY.get(granularity, _GRANULARITY["hour"])

    try:
        # Total count
        count_resp = requests.get(
            f"{ES_ENDPOINT.rstrip('/')}/{ES_INDEX}/_count",
            auth=ES_AUTH, verify=ES_VERIFY_SSL, timeout=5,
        )
        total = count_resp.json().get("count", 0)

        # Level aggregation + trend
        agg_body = {
            "size": 0,
            "aggs": {
                "by_level": {"terms": {"field": "level.keyword", "size": 10}},
                "trend": {
                    "date_histogram": {
                        "field": "@timestamp",
                        "fixed_interval": es_interval,
                        "order": {"_key": "desc"},
                    }
                },
            },
        }
        agg_resp = requests.post(
            f"{ES_ENDPOINT.rstrip('/')}/{ES_INDEX}/_search",
            json=agg_body,
            headers={"Content-Type": "application/json"},
            auth=ES_AUTH, verify=ES_VERIFY_SSL, timeout=5,
        )
        data = agg_resp.json()
        aggs = data.get("aggregations", {})
        levels = {b["key"]: b["doc_count"] for b in aggs.get("by_level", {}).get("buckets", [])}
        trend = [
            {"time": b["key_as_string"], "count": b["doc_count"]}
            for b in reversed(aggs.get("trend", {}).get("buckets", [])[-max_buckets:])
        ]
        return {"total": total, "levels": levels, "trend": trend}
    except Exception:
        return {"total": 0, "levels": {}, "trend": []}


def get_stats(granularity: str = "hour") -> dict[str, Any]:
    """Return dashboard statistics, dispatching by backend.

    granularity: 'minute' | 'hour' | 'day' | 'month'
    """
    if STORE_BACKEND == "es" and ES_ENDPOINT:
        return _stats_es(granularity)
    return _stats_sql(granularity)


# ---------------------------------------------------------------------------
# Topology nodes (connected services)
# ---------------------------------------------------------------------------


def _nodes_sql() -> list[dict[str, Any]]:
    """Get distinct logger nodes with stats from SQL backends, grouped by IP."""
    engine = create_engine(DB_URL, echo=False, future=True)
    Base.metadata.create_all(engine)

    with Session(engine, future=True) as session:
        rows = session.execute(
            select(
                LogEntry.source_ip,
                LogEntry.logger,
                func.count(LogEntry.id).label("log_count"),
                func.sum(
                    func.cast(LogEntry.level.in_(["ERROR", "CRITICAL"]), Integer)
                ).label("error_count"),
                func.max(LogEntry.ts).label("last_active"),
            )
            .where(LogEntry.logger.isnot(None))
            .group_by(LogEntry.source_ip, LogEntry.logger)
            .order_by(LogEntry.source_ip, func.count(LogEntry.id).desc())
        ).all()

    # Build hierarchical structure: [{ip, apps: [{name, log_count, ...}]}]
    ip_map: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ip = row[0] or "unknown"
        app_info = {
            "name": row[1] or "unknown",
            "log_count": row[2],
            "error_count": row[3] or 0,
            "last_active": row[4],
        }
        ip_map.setdefault(ip, []).append(app_info)

    return [
        {"ip": ip, "apps": apps, "log_count": sum(a["log_count"] for a in apps), "error_count": sum(a["error_count"] for a in apps)}
        for ip, apps in sorted(ip_map.items(), key=lambda x: sum(a["log_count"] for a in x[1]), reverse=True)
    ]


def _nodes_es() -> list[dict[str, Any]]:
    """Get distinct logger nodes from Elasticsearch, grouped by IP."""
    import requests

    try:
        body = {
            "size": 0,
            "aggs": {
                "by_ip": {
                    "terms": {"field": "source_ip.keyword", "size": 100, "missing": "unknown"},
                    "aggs": {
                        "by_logger": {
                            "terms": {"field": "logger.keyword", "size": 50},
                            "aggs": {
                                "errors": {
                                    "filter": {"terms": {"level.keyword": ["ERROR", "CRITICAL"]}}
                                },
                                "last_active": {"max": {"field": "@timestamp"}},
                            },
                        }
                    },
                }
            },
        }
        resp = requests.post(
            f"{ES_ENDPOINT.rstrip('/')}/{ES_INDEX}/_search",
            json=body,
            headers={"Content-Type": "application/json"},
            auth=ES_AUTH,
            verify=ES_VERIFY_SSL,
            timeout=5,
        )
        ip_buckets = resp.json().get("aggregations", {}).get("by_ip", {}).get("buckets", [])
        result = []
        for ip_b in ip_buckets:
            apps = [
                {
                    "name": lb["key"],
                    "log_count": lb["doc_count"],
                    "error_count": lb["errors"]["doc_count"],
                    "last_active": lb["last_active"]["value_as_string"],
                }
                for lb in ip_b["by_logger"]["buckets"]
            ]
            result.append({
                "ip": ip_b["key"],
                "apps": apps,
                "log_count": ip_b["doc_count"],
                "error_count": sum(a["error_count"] for a in apps),
            })
        return result
    except Exception:
        return []


def get_nodes() -> list[dict[str, Any]]:
    """Return connected service nodes for topology view."""
    if STORE_BACKEND == "es" and ES_ENDPOINT:
        return _nodes_es()
    return _nodes_sql()
