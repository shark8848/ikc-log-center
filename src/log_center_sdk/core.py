"""Core logging infrastructure: JSON formatting, trace context, configuration.

Extracted from sitech.ikc.logging into a self-contained module with zero
heavy dependencies (only stdlib + requests via handlers.py).
"""
from __future__ import annotations

import contextvars
import gzip
import json
import logging
import os
import shutil
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Trace context (contextvars — async-safe, fork-safe)
# ---------------------------------------------------------------------------

trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)
span_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("span_id", default=None)
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)


def set_trace_context(
    *,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """Bind trace identifiers into the current async context."""
    if trace_id is not None:
        trace_id_var.set(trace_id)
    if span_id is not None:
        span_id_var.set(span_id)
    if request_id is not None:
        request_id_var.set(request_id)


def clear_trace_context() -> None:
    """Reset all trace contextvars to None."""
    trace_id_var.set(None)
    span_id_var.set(None)
    request_id_var.set(None)


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

_STANDARD_RECORD_KEYS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
})


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter.

    Standard LogRecord fields are mapped to canonical keys; any extra fields
    attached via ``logger.info(..., extra={...})`` are merged into the JSON
    payload (with unsafe values falling back to ``repr()``).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Trace context (injected by TraceContextFilter)
        for key in ("trace_id", "span_id", "request_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        # Merge extras
        extras: dict[str, Any] = {}
        for key, val in record.__dict__.items():
            if key.startswith("_") or key in _STANDARD_RECORD_KEYS:
                continue
            if key in payload:
                continue
            try:
                json.dumps(val)
                extras[key] = val
            except Exception:
                extras[key] = str(val)
        if extras:
            payload.update(extras)

        return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Trace context filter
# ---------------------------------------------------------------------------


class TraceContextFilter(logging.Filter):
    """Inject trace contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        tid = trace_id_var.get()
        sid = span_id_var.get()
        rid = request_id_var.get()
        if tid:
            record.trace_id = tid
        if sid:
            record.span_id = sid
        if rid:
            record.request_id = rid
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    if "${" in raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _normalize(name: Optional[str]) -> str:
    return (name or "").replace("-", "_").upper()


def _cleanup_expired_log_backups(log_file_path: str, retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    base = os.path.abspath(log_file_path)
    prefix = f"{base}."
    cutoff = time.time() - retention_days * 86400
    removed = 0
    directory = os.path.dirname(base) or "."
    if not os.path.isdir(directory):
        return 0
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        abs_path = os.path.abspath(path)
        if abs_path == base or not abs_path.startswith(prefix) or not os.path.isfile(abs_path):
            continue
        try:
            if os.path.getmtime(abs_path) < cutoff:
                os.remove(abs_path)
                removed += 1
        except Exception:
            continue
    return removed


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_initialized = False


def configure(
    *,
    module_name: Optional[str] = None,
    level: Optional[str] = None,
    json_output: Optional[bool] = None,
    log_file: Optional[str] = None,
    attach_remote: Optional[bool] = None,
    _force: bool = False,
) -> None:
    """Initialise base logging: console + rotating file + optional remote handlers.

    Parameters
    ----------
    module_name:
        Used for per-module env overrides (``LOG_CENTER_ENABLE_{MODULE}``)
        and default file naming (``logs/{module_name}.log``).
    level:
        Override ``LOG_LEVEL`` env var.  Default ``INFO``.
    json_output:
        Override ``LOG_JSON`` env var.  Default ``True``.
    log_file:
        Override ``LOG_FILE_PATH`` env var.
    attach_remote:
        Force remote handler attachment.  ``None`` follows env vars.
    _force:
        Reset ``_initialized`` guard (used by Celery fork hooks).
    """
    global _initialized
    if _initialized and not _force:
        return
    _initialized = True

    norm = _normalize(module_name) or None
    log_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()

    if json_output is not None:
        use_json = json_output
    else:
        raw_json = os.getenv("LOG_JSON")
        use_json = True if raw_json is None else _bool_env("LOG_JSON", True)

    # File logging
    module_log_file = os.getenv(f"LOG_FILE_PATH_{norm}") if norm else None
    module_max_mb = os.getenv(f"LOG_FILE_MAX_MB_{norm}") if norm else None
    module_backup = os.getenv(f"LOG_FILE_BACKUP_{norm}") if norm else None
    module_file_enable = os.getenv(f"LOG_FILE_ENABLE_{norm}") if norm else None
    module_compress = os.getenv(f"LOG_FILE_COMPRESS_{norm}") if norm else None
    module_retention_days = os.getenv(f"LOG_FILE_RETENTION_DAYS_{norm}") if norm else None

    file_logging_enabled = True
    raw_file_enable = module_file_enable if module_file_enable is not None else os.getenv("LOG_FILE_ENABLE")
    if raw_file_enable is not None:
        file_logging_enabled = _bool_env("LOG_FILE_ENABLE", True)

    log_file_path = log_file or module_log_file or os.getenv("LOG_FILE_PATH") or f"logs/{module_name or 'app'}.log"
    max_mb = float(module_max_mb or os.getenv("LOG_FILE_MAX_MB", "500"))
    backup_count = int(module_backup or os.getenv("LOG_FILE_BACKUP", "3"))
    if module_compress is not None:
        compress_logs = module_compress.strip().lower() in {"1", "true", "yes", "on"}
    else:
        compress_logs = _bool_env("LOG_FILE_COMPRESS", True)
    if module_retention_days is not None:
        try:
            retention_days = int(module_retention_days)
        except (TypeError, ValueError):
            retention_days = 14
    else:
        retention_days = _int_env("LOG_FILE_RETENTION_DAYS", 14)
    max_bytes = int(max(1, max_mb) * 1024 * 1024)

    formatter = JsonFormatter() if use_json else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    trace_filter = TraceContextFilter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(trace_filter)

    root = logging.getLogger()
    root.setLevel(log_level)
    handlers: list[logging.Handler] = [console_handler]

    if file_logging_enabled:
        os.makedirs(os.path.dirname(log_file_path) or ".", exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        if compress_logs:
            file_handler.namer = lambda name: f"{name}.gz"

            def _gzip_rotator(source: str, dest: str) -> None:
                with open(source, "rb") as src, gzip.open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.remove(source)

            file_handler.rotator = _gzip_rotator

        original_do_rollover = file_handler.doRollover

        def _do_rollover_with_cleanup() -> None:
            original_do_rollover()
            _cleanup_expired_log_backups(log_file_path, retention_days)

        file_handler.doRollover = _do_rollover_with_cleanup
        file_handler.setFormatter(formatter)
        file_handler.addFilter(trace_filter)
        handlers.append(file_handler)

    # Replace root handlers (not append) to avoid duplicates on re-init
    root.handlers = handlers

    if file_logging_enabled:
        removed = _cleanup_expired_log_backups(log_file_path, retention_days)
        if removed > 0:
            logging.getLogger(__name__).info(
                "log cleanup removed expired backups",
                extra={"removed": removed, "retention_days": retention_days},
            )

    # Remote handlers
    default_remote = _bool_env("LOG_CENTER_ENABLE", False)
    module_remote = _bool_env(f"LOG_CENTER_ENABLE_{norm}", default_remote) if norm else default_remote
    should_attach = attach_remote if attach_remote is not None else module_remote

    if should_attach:
        from .handlers import build_handlers_from_env

        for handler in build_handlers_from_env():
            handler.setFormatter(JsonFormatter())
            handler.addFilter(trace_filter)
            root.addHandler(handler)


def get_logger(name: str, *, level: Optional[str] = None) -> logging.Logger:
    """Return a logger, optionally overriding its level."""
    logger = logging.getLogger(name)
    if level:
        logger.setLevel(level.upper())
    return logger
