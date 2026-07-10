"""FastAPI integration — automatic trace context extraction from HTTP headers.

Usage::

    from fastapi import FastAPI
    from log_center_sdk.integrations.fastapi import TraceMiddleware

    app = FastAPI()
    app.add_middleware(TraceMiddleware)

Extracts ``X-Trace-Id``, ``X-Span-Id``, ``X-Request-Id`` from incoming
requests and binds them to contextvars.  Generates a UUID request_id when
the header is absent.
"""
from __future__ import annotations

import uuid
from typing import Callable

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    _HAS_STARLETTE = True
except ImportError:
    _HAS_STARLETTE = False

from ..core import clear_trace_context, set_trace_context

# Header names (case-insensitive via Starlette's Headers object)
_TRACE_HEADER = "x-trace-id"
_SPAN_HEADER = "x-span-id"
_REQUEST_HEADER = "x-request-id"


if _HAS_STARLETTE:

    class TraceMiddleware(BaseHTTPMiddleware):
        """ASGI middleware that propagates trace headers into contextvars."""

        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            trace_id = request.headers.get(_TRACE_HEADER)
            span_id = request.headers.get(_SPAN_HEADER)
            request_id = request.headers.get(_REQUEST_HEADER) or str(uuid.uuid4())

            set_trace_context(
                trace_id=trace_id,
                span_id=span_id,
                request_id=request_id,
            )
            try:
                response = await call_next(request)
                # Echo trace headers back for client correlation
                if trace_id:
                    response.headers["X-Trace-Id"] = trace_id
                response.headers["X-Request-Id"] = request_id
                return response
            finally:
                clear_trace_context()

else:
    # Graceful degradation when starlette is not installed
    class TraceMiddleware:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "starlette not installed — pip install log-center-sdk[fastapi]"
            )
