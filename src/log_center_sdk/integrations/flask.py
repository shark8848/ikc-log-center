"""Flask integration — automatic trace context extraction from HTTP headers.

Usage::

    from flask import Flask
    from log_center_sdk.integrations.flask import init_trace_hooks

    app = Flask(__name__)
    init_trace_hooks(app)

Extracts ``X-Trace-Id``, ``X-Span-Id``, ``X-Request-Id`` from incoming
requests and binds them to contextvars.
"""
from __future__ import annotations

import uuid

from ..core import clear_trace_context, request_id_var, set_trace_context

# Header names (Flask uses lowercase header keys via request.headers)
_TRACE_HEADER = "X-Trace-Id"
_SPAN_HEADER = "X-Span-Id"
_REQUEST_HEADER = "X-Request-Id"


def init_trace_hooks(app: object) -> None:
    """Register ``before_request`` / ``after_request`` hooks on a Flask *app*.

    Parameters
    ----------
    app:
        A ``flask.Flask`` instance.
    """
    try:
        from flask import request as flask_request
    except ImportError:
        raise RuntimeError("flask not installed — pip install log-center-sdk[flask]")

    @app.before_request  # type: ignore[attr-defined]
    def _before() -> None:
        trace_id = flask_request.headers.get(_TRACE_HEADER)
        span_id = flask_request.headers.get(_SPAN_HEADER)
        request_id = flask_request.headers.get(_REQUEST_HEADER) or str(uuid.uuid4())
        set_trace_context(trace_id=trace_id, span_id=span_id, request_id=request_id)

    @app.after_request  # type: ignore[attr-defined]
    def _after(response):
        trace_id = flask_request.headers.get(_TRACE_HEADER)
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        request_id = request_id_var.get()
        if request_id:
            response.headers["X-Request-Id"] = request_id
        clear_trace_context()
        return response
