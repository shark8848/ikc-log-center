"""Decorator-based function instrumentation for structured log-center telemetry.

Usage::

    from log_center_sdk import instrumented

    @instrumented("document_parse")
    def parse(path, fmt="pdf"):
        ...

    @instrumented("llm_call", log_args={"model"}, redact_args={"api_key"})
    async def call_llm(prompt, model, api_key):
        ...

    @instrumented("es_query", slow_threshold_ms=500)
    def search(query):
        ...

Every invocation emits a structured log record via the SDK's JSON formatter,
which flows through the configured remote handlers (HTTP / gRPC / Celery)
to log_center.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable, Optional, Set

from .core import request_id_var, span_id_var, trace_id_var

_logger = logging.getLogger("log_center_sdk.instrumentation")

# ---------------------------------------------------------------------------
# Safe serialisation helpers
# ---------------------------------------------------------------------------

_SAFE_TYPES = (str, int, float, bool, type(None))
_REPR_LIMIT = 200
_LIST_LIMIT = 10
_DICT_LIMIT = 20


def _safe_value(value: Any) -> Any:
    """Return a JSON-serialisable representation of *value*."""
    if isinstance(value, _SAFE_TYPES):
        return value
    if isinstance(value, (list, tuple)):
        return [item if isinstance(item, _SAFE_TYPES) else type(item).__name__ for item in value[:_LIST_LIMIT]]
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in list(value.items())[:_DICT_LIMIT]}
    try:
        r = repr(value)
    except Exception:
        return "<unreprable>"
    return r[:_REPR_LIMIT] if len(r) > _REPR_LIMIT else r


# ---------------------------------------------------------------------------
# Argument filtering
# ---------------------------------------------------------------------------


def _filter_args(
    bound: inspect.BoundArguments,
    log_args: Optional[Set[str]],
    redact_args: Optional[Set[str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in bound.arguments.items():
        if log_args is not None and name not in log_args:
            continue
        if redact_args and name in redact_args:
            result[name] = "***"
            continue
        result[name] = _safe_value(value)
    return result


# ---------------------------------------------------------------------------
# Trace context extraction
# ---------------------------------------------------------------------------


def _trace_extras() -> dict[str, str]:
    extras: dict[str, str] = {}
    for key, var in (("trace_id", trace_id_var), ("span_id", span_id_var), ("request_id", request_id_var)):
        val = var.get()
        if val is not None:
            extras[key] = val
    return extras


# ---------------------------------------------------------------------------
# Core decorator
# ---------------------------------------------------------------------------


def instrumented(
    name: str,
    *,
    log_args: Optional[Set[str]] = None,
    redact_args: Optional[Set[str]] = None,
    log_result: bool = False,
    component: Optional[str] = None,
    slow_threshold_ms: Optional[float] = None,
    level: int = logging.INFO,
    error_level: int = logging.ERROR,
) -> Callable:
    """Decorator that emits a structured telemetry log record for every call.

    Parameters
    ----------
    name:
        Event name recorded in the ``event`` field (e.g. ``"document_parse"``).
    log_args:
        Whitelist of parameter names to include.  ``None`` means *all*.
    redact_args:
        Blacklist — matched parameters are replaced with ``"***"``.
    log_result:
        When ``True``, record ``result_type`` and ``result_len`` in the log record.
    component:
        Optional component label written to the ``component`` field.
    slow_threshold_ms:
        If the call exceeds this duration the log level is elevated to ``WARNING``.
    level:
        Log level for successful (or slow) calls.  Default ``INFO``.
    error_level:
        Log level for failed calls.  Default ``ERROR``.
    """

    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)

        def _build_extras(
            bound: inspect.BoundArguments,
            duration_ms: float,
            status: str,
            result: Any = None,
            exc: Optional[BaseException] = None,
        ) -> dict[str, Any]:
            extra: dict[str, Any] = {
                "event": name,
                "duration_ms": round(duration_ms, 2),
                "status": status,
            }
            if component:
                extra["component"] = component
            extra.update(_trace_extras())

            filtered = _filter_args(bound, log_args, redact_args)
            if filtered:
                extra["call_args"] = filtered

            if log_result and status == "ok" and result is not None:
                extra["result_type"] = type(result).__name__
                try:
                    extra["result_len"] = len(result)
                except TypeError:
                    pass

            if exc is not None:
                extra["error_type"] = type(exc).__name__
                extra["error_message"] = str(exc)

            return extra

        def _resolve_level(duration_ms: float) -> int:
            if slow_threshold_ms is not None and duration_ms > slow_threshold_ms:
                return logging.WARNING
            return level

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                t0 = time.perf_counter()
                try:
                    result = await fn(*args, **kwargs)
                except BaseException as exc:
                    duration_ms = (time.perf_counter() - t0) * 1000
                    extra = _build_extras(bound, duration_ms, "error", exc=exc)
                    _logger.log(error_level, f"{name} failed: {type(exc).__name__}", extra=extra)
                    raise
                else:
                    duration_ms = (time.perf_counter() - t0) * 1000
                    resolved = _resolve_level(duration_ms)
                    extra = _build_extras(bound, duration_ms, "ok", result=result)
                    label = "slow" if resolved == logging.WARNING else "completed"
                    _logger.log(resolved, f"{name} {label}", extra=extra)
                    return result

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                t0 = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                except BaseException as exc:
                    duration_ms = (time.perf_counter() - t0) * 1000
                    extra = _build_extras(bound, duration_ms, "error", exc=exc)
                    _logger.log(error_level, f"{name} failed: {type(exc).__name__}", extra=extra)
                    raise
                else:
                    duration_ms = (time.perf_counter() - t0) * 1000
                    resolved = _resolve_level(duration_ms)
                    extra = _build_extras(bound, duration_ms, "ok", result=result)
                    label = "slow" if resolved == logging.WARNING else "completed"
                    _logger.log(resolved, f"{name} {label}", extra=extra)
                    return result

            return sync_wrapper

    return decorator
