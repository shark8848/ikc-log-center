"""Celery app and ingest task for async log delivery.

Only instantiated when ``LOG_CENTER_CELERY_ENABLE`` is set to a truthy value.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("log_center.celery")


def _redis_url(db: int) -> str | None:
    base = (os.getenv("REDIS_URI_BASE") or "").strip()
    if not base:
        return None
    return f"{base}/{db}"


CELERY_ENABLE = os.getenv("LOG_CENTER_CELERY_ENABLE", "").strip().lower() in {"1", "true", "yes", "on"}
CELERY_BROKER = os.getenv("LOG_CENTER_CELERY_BROKER") or _redis_url(0) or "redis://localhost:6379/0"
CELERY_BACKEND = os.getenv("LOG_CENTER_CELERY_BACKEND") or _redis_url(1) or "redis://localhost:6379/1"

celery_app = None

if CELERY_ENABLE:
    try:
        from celery import Celery

        celery_app = Celery("log-center", broker=CELERY_BROKER, backend=CELERY_BACKEND)

        @celery_app.task(name="log_center.ingest")
        def ingest_task(entries: list[dict[str, Any]]) -> dict[str, Any]:
            """Celery task: ingest log entries via the shared pipeline."""
            from .app import process_entries

            return process_entries(entries)

    except ImportError:
        logger.warning("Celery enabled via LOG_CENTER_CELERY_ENABLE but celery package not installed")
