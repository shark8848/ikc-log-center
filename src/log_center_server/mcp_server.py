"""MCP (Model Context Protocol) server exposing log search capabilities.

Provides tools for AI clients (Claude Desktop, Cursor, Qoder, etc.) to
search logs and retrieve statistics from the log-center storage backend.

Transport modes:
  - stdio (default): launched as a subprocess by the AI client
  - streamable-http: standalone HTTP service (--transport http)
  - sse: Server-Sent Events mode (--transport sse)

Usage:
    python -m log_center_server.mcp_server [--transport stdio|http|sse] [--host HOST] [--port PORT]

Environment variables (same as log-center server):
    LOG_CENTER_STORE, LOG_CENTER_DB_PATH, LOG_CENTER_PG_*, LOG_CENTER_MYSQL_*, LOG_CENTER_ES_*
    LOG_CENTER_MCP_TOKEN       Bearer token for MCP access (required when auth enabled)
    LOG_CENTER_AUTH_ENABLED    Enable token verification: true|false (default: false)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("log_center.mcp")

mcp = FastMCP(
    "log-center",
    instructions="Log Center MCP service — search and analyze application logs",
)

_VALID_GRANULARITIES = ("minute", "hour", "day", "month")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_logs(
    trace_id: str = "",
    level: str = "",
    message_substr: str = "",
    limit: int = 50,
) -> str:
    """Search log entries with optional filters.

    Args:
        trace_id: Filter by exact trace ID (distributed tracing correlation).
        level: Filter by log level (e.g. DEBUG, INFO, WARNING, ERROR, CRITICAL).
        message_substr: Case-insensitive substring match on log message.
        limit: Maximum number of results to return (1-500, default 50).

    Returns:
        JSON with matched count and log items (ts, level, logger, message, trace_id, payload...).
    """
    from .query import query_logs

    limit = max(1, min(int(limit or 50), 500))
    items = query_logs(
        trace_id=trace_id.strip(),
        level=level.strip().upper() if level else "",
        message_substr=message_substr.strip(),
        limit=limit,
    )
    return json.dumps(
        {"count": len(items), "items": items},
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def get_log_stats(granularity: str = "hour") -> str:
    """Get log statistics: total count, per-level breakdown, and time trend.

    Args:
        granularity: Trend time granularity — one of: minute, hour, day, month.

    Returns:
        JSON with total log count, levels distribution, and trend time series.
    """
    from .query import get_stats

    if granularity not in _VALID_GRANULARITIES:
        granularity = "hour"
    stats = get_stats(granularity=granularity)
    return json.dumps(stats, ensure_ascii=False, default=str)


@mcp.tool()
def list_log_levels() -> str:
    """List all distinct log levels present in the storage with their counts.

    Returns:
        JSON mapping of level name to count (e.g. {"INFO": 80, "ERROR": 28}).
    """
    from .query import get_stats

    stats = get_stats(granularity="day")
    levels: dict[str, Any] = stats.get("levels", {})
    return json.dumps(
        {"levels": levels, "total": stats.get("total", 0)},
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def get_trace_chain(trace_id: str) -> str:
    """Get the full trace chain for a given trace ID — all related logs in chronological order.

    Use this to understand the complete call chain / request lifecycle across services.
    Returns all log entries sharing the same trace_id, sorted by timestamp ascending,
    making it easy to follow the request flow from start to finish.

    Args:
        trace_id: The trace ID to look up (e.g. "trace-7511-199").

    Returns:
        JSON with trace_id, count, and items (chronologically ordered log entries).
    """
    from .query import query_logs

    items = query_logs(trace_id=trace_id.strip(), limit=500)
    items.sort(key=lambda r: r.get("ts") or "")
    return json.dumps(
        {"trace_id": trace_id, "count": len(items), "items": items},
        ensure_ascii=False,
        default=str,
    )


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def _verify_mcp_token(token: str) -> bool:
    """Verify a Bearer token against the log-center auth backend."""
    from .auth import verify_token
    return verify_token(token)


def _check_startup_token() -> None:
    """For stdio mode: verify LOG_CENTER_MCP_TOKEN at startup.

    If LOG_CENTER_AUTH_ENABLED is true, the env var must contain a valid token.
    """
    auth_enabled = os.getenv("LOG_CENTER_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
    if not auth_enabled:
        return
    token = os.getenv("LOG_CENTER_MCP_TOKEN", "").strip()
    if not token:
        print("ERROR: LOG_CENTER_AUTH_ENABLED=true but LOG_CENTER_MCP_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    if not _verify_mcp_token(token):
        print("ERROR: LOG_CENTER_MCP_TOKEN is invalid or revoked", file=sys.stderr)
        sys.exit(1)
    logger.info("MCP stdio token verified successfully")


def _add_auth_middleware(app):  # noqa: ANN001
    """Wrap a Starlette app with Bearer token auth middleware for HTTP/SSE."""
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    auth_enabled = os.getenv("LOG_CENTER_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
    if not auth_enabled:
        return app

    class TokenAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):  # noqa: ANN001
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer ") or not _verify_mcp_token(auth_header[7:].strip()):
                return JSONResponse(
                    status_code=401,
                    content={"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: invalid or missing token"}, "id": None},
                )
            return await call_next(request)

    app.add_middleware(TokenAuthMiddleware)
    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for the log-center MCP server."""
    parser = argparse.ArgumentParser(
        prog="log-center-mcp",
        description="Log Center MCP server — exposes log search tools to AI clients",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport mode: stdio (default, for local AI clients), http (streamable HTTP), sse",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("LOG_CENTER_MCP_HOST", "127.0.0.1"),
        help="Bind host for http/sse transport (default: 127.0.0.1, env: LOG_CENTER_MCP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("LOG_CENTER_MCP_PORT", "9318")),
        help="Bind port for http/sse transport (default: 9318, env: LOG_CENTER_MCP_PORT)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        _check_startup_token()
        mcp.run(transport="stdio")
    elif args.transport == "http":
        import uvicorn

        mcp.settings.host = args.host
        mcp.settings.port = args.port
        app = _add_auth_middleware(mcp.streamable_http_app())
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    elif args.transport == "sse":
        import uvicorn

        mcp.settings.host = args.host
        mcp.settings.port = args.port
        app = _add_auth_middleware(mcp.sse_app())
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
