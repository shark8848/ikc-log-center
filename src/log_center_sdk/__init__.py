"""Log Center SDK — decorator-based instrumentation with HTTP/gRPC/Celery delivery."""
from __future__ import annotations

from .core import (
    clear_trace_context,
    configure,
    get_logger,
    set_trace_context,
)
from .instrumentation import instrumented

__all__ = [
    "configure",
    "get_logger",
    "set_trace_context",
    "clear_trace_context",
    "instrumented",
    "build_handlers_from_env",
]


def __getattr__(name: str):
    """Lazy import for optional components."""
    if name == "patch_celery_app":
        from .celery_hooks import patch_celery_app
        return patch_celery_app
    if name == "build_handlers_from_env":
        from .handlers import build_handlers_from_env
        return build_handlers_from_env
    raise AttributeError(f"module 'log_center_sdk' has no attribute {name!r}")
