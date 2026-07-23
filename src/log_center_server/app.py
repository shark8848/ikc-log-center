"""FastAPI application for log ingestion, health, search, and management.

Provides endpoints:
- POST /ingest — accept single or array of JSON log objects
- GET /health — liveness probe
- GET /search — query logs by trace_id, level, message_substr
- GET /api/tokens — list API tokens
- POST /api/tokens — generate a new API token
- DELETE /api/tokens/{prefix} — revoke a token
- GET /api/stats — dashboard statistics

All ingestion paths (HTTP, gRPC, Celery) share ``process_entries()``.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse

from .storage import (
    forward_entries,
    init_sqlite,
    normalize_entries,
    write_backend,
    write_file,
    FORWARD_URLS,
)
from .query import query_logs
from .auth import AUTH_ENABLED, init_token_store, verify_token, generate_token, add_token, list_tokens, revoke_token

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CORS_ORIGINS = [o.strip() for o in os.getenv("LOG_CENTER_CORS_ORIGINS", "*").split(",") if o.strip()]

# Paths that never require authentication
_AUTH_EXEMPT_PATHS = frozenset({"/health", "/openapi.json", "/docs", "/redoc"})

logger = logging.getLogger("log_center")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure storage tables and token store exist on startup."""
    init_sqlite()
    init_token_store()
    yield


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="log-center", version="v1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Bearer token authentication (OpenAI-style).

    Skipped entirely when ``LOG_CENTER_AUTH_ENABLED`` is false/unset.
    """
    if AUTH_ENABLED and request.url.path not in _AUTH_EXEMPT_PATHS:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer ") or not verify_token(auth_header[7:].strip()):
            return JSONResponse(
                status_code=401,
                content={"status": "error", "reason": "unauthorized"},
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Shared pipeline
# ---------------------------------------------------------------------------


def process_entries(entries: list[dict[str, Any]], trace_id_hint: str | None = None) -> dict[str, Any]:
    """Core ingestion pipeline shared by HTTP, gRPC, and Celery entry points."""
    entries = normalize_entries(entries, trace_id_hint=trace_id_hint)
    if not entries:
        return {"status": "ok", "stored": 0}
    write_file(entries)
    init_sqlite()
    write_backend(entries)
    forward_entries(entries)
    return {"status": "ok", "stored": len(entries), "forwarded": len(FORWARD_URLS)}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/ingest", tags=["log-center"])
async def ingest(request: Request) -> dict[str, Any]:
    """Accept single log object or array of log objects."""
    try:
        payload = await request.json()
    except Exception:
        logger.warning("invalid json on /ingest")
        return {"status": "error", "reason": "invalid json"}

    entries: list[dict[str, Any]]
    if isinstance(payload, list):
        entries = [e for e in payload if isinstance(e, dict)]
    elif isinstance(payload, dict):
        entries = [payload]
    else:
        return {"status": "error", "reason": "payload must be object or list"}

    if not entries:
        return {"status": "ok", "stored": 0}

    # Inject source IP from client request
    client_ip = request.client.host if request.client else None
    if client_ip:
        for e in entries:
            if not e.get("source_ip"):
                e["source_ip"] = client_ip

    trace_id_hint = request.headers.get("x-trace-id")
    return process_entries(entries, trace_id_hint=trace_id_hint)


@app.get("/health", tags=["log-center"])
async def health() -> dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/search", tags=["log-center"])
async def search(
    trace_id: str | None = None,
    level: str | None = None,
    message_substr: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Query logs by trace_id, level, message_substr, with limit 1–500.

    Automatically dispatches to the configured storage backend.
    """
    limit = max(1, min(limit, 500))
    rows = query_logs(
        trace_id=trace_id or "",
        level=level or "",
        message_substr=message_substr or "",
        limit=limit,
    )
    return {"status": "ok", "count": len(rows), "items": rows}


@app.get("/api/trace/{trace_id}", tags=["log-center"])
async def api_trace_chain(trace_id: str) -> dict[str, Any]:
    """Return all logs for a given trace_id in chronological order (trace chain)."""
    rows = query_logs(trace_id=trace_id.strip(), limit=500)
    # Sort by timestamp ascending for chain visualization
    rows.sort(key=lambda r: r.get("ts") or "")
    return {"status": "ok", "trace_id": trace_id, "count": len(rows), "items": rows}


# ---------------------------------------------------------------------------
# Token management API
# ---------------------------------------------------------------------------


@app.get("/api/tokens", tags=["management"])
async def api_list_tokens() -> dict[str, Any]:
    """List all API tokens (metadata only)."""
    tokens = list_tokens()
    return {"status": "ok", "tokens": tokens}


@app.post("/api/tokens", tags=["management"])
async def api_create_token(request: Request) -> dict[str, Any]:
    """Generate a new API token. Returns plaintext only once."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    description = body.get("description", "") if isinstance(body, dict) else ""
    plain, info = generate_token(description=description)
    add_token(info)
    return {"status": "ok", "token": plain, "prefix": info["prefix"], "description": description}


@app.delete("/api/tokens/{prefix}", tags=["management"])
async def api_revoke_token(prefix: str) -> dict[str, Any]:
    """Revoke a token by its prefix."""
    ok = revoke_token(prefix)
    if ok:
        return {"status": "ok", "revoked": prefix}
    return JSONResponse(status_code=404, content={"status": "error", "reason": "token not found"})


# ---------------------------------------------------------------------------
# Stats API (dashboard)
# ---------------------------------------------------------------------------


@app.get("/api/stats", tags=["management"])
async def api_stats(granularity: str = "hour") -> dict[str, Any]:
    """Return log statistics for the dashboard.

    granularity: minute | hour | day | month
    """
    from .query import get_stats
    if granularity not in ("minute", "hour", "day", "month"):
        granularity = "hour"
    stats = get_stats(granularity=granularity)
    return {"status": "ok", **stats}


@app.get("/api/nodes", tags=["management"])
async def api_nodes() -> dict[str, Any]:
    """Return connected service nodes for topology view."""
    from .query import get_nodes
    nodes = get_nodes()
    return {"status": "ok", "nodes": nodes}


# ---------------------------------------------------------------------------
# Static file serving (production SPA)
# ---------------------------------------------------------------------------

_WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

if _WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_WEB_DIST / "assets"), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Serve index.html for all non-API routes (SPA fallback)."""
        file_path = _WEB_DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_WEB_DIST / "index.html")
