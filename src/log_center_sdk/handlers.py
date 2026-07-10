"""Async batch delivery handlers for log_center: HTTP, gRPC, and Celery.

All handlers extend ``_BaseAsyncBatchHandler`` which provides:
- Thread-safe in-memory queue
- Background worker thread that drains and flushes in batches
- Best-effort delivery (failures are silently dropped)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from queue import Empty, Queue
from typing import Any, Optional

import requests

from .core import _int_env

# Optional dependencies — imported lazily to keep the base install lightweight.
try:
    import grpc
except ImportError:
    grpc = None  # type: ignore[assignment]

try:
    from celery import Celery
except ImportError:
    Celery = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class _BaseAsyncBatchHandler(logging.Handler):
    """Common batching logic: queue + background worker thread."""

    def __init__(self, queue_size: int = 1000) -> None:
        super().__init__()
        self._queue: Queue[dict[str, Any]] = Queue(maxsize=queue_size)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatted = self.format(record)
            payload = formatted if isinstance(formatted, dict) else json.loads(formatted)
            self._queue.put_nowait(payload)
        except Exception:
            pass  # best-effort: never let logging break the application

    def _drain_batch(self, max_items: int) -> list[dict[str, Any]]:
        items = [self._queue.get(timeout=1.0)]
        try:
            while len(items) < max_items:
                items.append(self._queue.get_nowait())
        except Empty:
            pass
        return items

    def _worker(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class HttpLogHandler(_BaseAsyncBatchHandler):
    """Async HTTP log handler — POSTs JSON batches to ``{endpoint}/ingest``."""

    def __init__(self, endpoint: str, timeout: float = 2.0, queue_size: int = 1000,
                 batch_size: int = 50, token: str = "") -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.batch_size = batch_size
        self.token = token
        super().__init__(queue_size=queue_size)

    def _worker(self) -> None:
        session = requests.Session()
        if self.token:
            session.headers["Authorization"] = f"Bearer {self.token}"
        while True:
            try:
                batch = self._drain_batch(max_items=self.batch_size)
            except Empty:
                continue
            try:
                session.post(f"{self.endpoint}/ingest", json=batch, timeout=self.timeout)
            except Exception:
                continue


# ---------------------------------------------------------------------------
# gRPC handler
# ---------------------------------------------------------------------------

_GRPC_SERVICE = "logcenter.LogService"
_GRPC_METHOD = "Ingest"


class GrpcLogHandler(_BaseAsyncBatchHandler):
    """Async gRPC log handler — sends JSON bytes via ``logcenter.LogService/Ingest``.

    No protobuf compilation required.  The log_center server uses a generic
    JSON bytes handler that accepts the same payload format as the HTTP endpoint.
    """

    def __init__(
        self,
        addr: str,
        timeout: float = 2.0,
        insecure: bool = True,
        queue_size: int = 1000,
        batch_size: int = 50,
        token: str = "",
    ) -> None:
        if grpc is None:
            raise RuntimeError("grpcio not installed — pip install log-center-sdk[grpc]")
        self.addr = addr
        self.timeout = timeout
        self.insecure = insecure
        self.batch_size = batch_size
        self.token = token
        super().__init__(queue_size=queue_size)

    def _worker(self) -> None:
        if self.insecure:
            channel = grpc.insecure_channel(self.addr)
        else:
            channel = grpc.secure_channel(self.addr, grpc.ssl_channel_credentials())

        stub_fn = channel.unary_unary(
            f"/{_GRPC_SERVICE}/{_GRPC_METHOD}",
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )

        while True:
            try:
                batch = self._drain_batch(max_items=self.batch_size)
            except Empty:
                continue
            try:
                payload = json.dumps(batch, ensure_ascii=False).encode("utf-8")
                metadata = []
                if self.token:
                    metadata.append(("authorization", f"Bearer {self.token}"))
                stub_fn(payload, timeout=self.timeout, metadata=metadata or None)
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Celery handler
# ---------------------------------------------------------------------------


class CeleryLogHandler(_BaseAsyncBatchHandler):
    """Async Celery log handler — sends batches via ``send_task``."""

    def __init__(
        self,
        broker_url: str,
        backend_url: Optional[str] = None,
        task_name: str = "log_center.ingest",
        queue_size: int = 1000,
        batch_size: int = 50,
    ) -> None:
        if Celery is None:
            raise RuntimeError("celery not installed — pip install log-center-sdk[celery]")
        self.task_name = task_name
        self.batch_size = batch_size
        self._celery = Celery("log-center-logger", broker=broker_url, backend=backend_url)
        super().__init__(queue_size=queue_size)

    def _worker(self) -> None:
        while True:
            try:
                batch = self._drain_batch(max_items=self.batch_size)
            except Empty:
                continue
            try:
                self._celery.send_task(self.task_name, args=[batch])
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_handlers_from_env() -> list[logging.Handler]:
    """Build remote log-center handlers based on ``LOG_CENTER_DELIVERY`` env var.

    Supported delivery modes (comma-separated for multi-channel):
    - ``api``    → :class:`HttpLogHandler`
    - ``grpc``   → :class:`GrpcLogHandler`
    - ``celery`` → :class:`CeleryLogHandler`
    - ``both``   → ``api`` + ``celery`` (backward compatibility)
    """
    delivery = (os.getenv("LOG_CENTER_DELIVERY") or "api").lower()
    modes = {m.strip() for m in delivery.split(",") if m.strip()}

    # Backward compatibility: "both" → api + celery
    if "both" in modes:
        modes.update({"api", "celery"})
        modes.discard("both")

    handlers: list[logging.Handler] = []
    timeout = float(os.getenv("LOG_CENTER_TIMEOUT", "2"))
    queue_size = _int_env("LOG_CENTER_QUEUE", 1000)
    batch_size = _int_env("LOG_CENTER_BATCH", 50)
    token = os.getenv("LOG_CENTER_TOKEN", "")

    # HTTP
    if "api" in modes:
        url = os.getenv("LOG_CENTER_URL")
        if url:
            try:
                handlers.append(HttpLogHandler(
                    endpoint=url, timeout=timeout, queue_size=queue_size,
                    batch_size=batch_size, token=token,
                ))
            except Exception:
                pass

    # gRPC
    if "grpc" in modes:
        addr = os.getenv("LOG_CENTER_GRPC_ADDR")
        if not addr:
            port = os.getenv("LOG_CENTER_GRPC_PORT", "9316")
            host = os.getenv("LOG_CENTER_GRPC_HOST", "localhost")
            addr = f"{host}:{port}"
        insecure = os.getenv("LOG_CENTER_GRPC_INSECURE", "true").lower() in {"1", "true", "yes"}
        if grpc is not None:
            try:
                handlers.append(GrpcLogHandler(
                    addr=addr, timeout=timeout, insecure=insecure,
                    queue_size=queue_size, batch_size=batch_size, token=token,
                ))
            except Exception:
                pass

    # Celery
    if "celery" in modes:
        if Celery is not None:
            broker = os.getenv("LOG_CENTER_CELERY_BROKER", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
            backend = os.getenv("LOG_CENTER_CELERY_BACKEND", os.getenv("CELERY_RESULT_BACKEND", None))
            task_name = os.getenv("LOG_CENTER_CELERY_TASK", "log_center.ingest")
            try:
                handlers.append(CeleryLogHandler(
                    broker_url=broker, backend_url=backend, task_name=task_name,
                    queue_size=queue_size, batch_size=batch_size,
                ))
            except Exception:
                pass

    return handlers
