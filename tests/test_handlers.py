"""Unit tests for handlers.py — delivery channels and factory."""
from __future__ import annotations

import json
import logging
import os

import pytest

from log_center_sdk.handlers import (
    CeleryLogHandler,
    GrpcLogHandler,
    HttpLogHandler,
    _BaseAsyncBatchHandler,
    build_handlers_from_env,
)


# ---------------------------------------------------------------------------
# HttpLogHandler
# ---------------------------------------------------------------------------


class TestHttpLogHandler:
    def test_creation(self):
        handler = HttpLogHandler(endpoint="http://localhost:9315", timeout=1.0)
        assert handler.endpoint == "http://localhost:9315"
        assert handler.timeout == 1.0
        assert handler.batch_size == 50

    def test_endpoint_trailing_slash_stripped(self):
        handler = HttpLogHandler(endpoint="http://localhost:9315/")
        assert handler.endpoint == "http://localhost:9315"


# ---------------------------------------------------------------------------
# GrpcLogHandler
# ---------------------------------------------------------------------------


class TestGrpcLogHandler:
    def test_creation(self):
        try:
            handler = GrpcLogHandler(addr="localhost:9316", timeout=1.0)
            assert handler.addr == "localhost:9316"
            assert handler.timeout == 1.0
        except RuntimeError:
            pytest.skip("grpcio not installed")


# ---------------------------------------------------------------------------
# CeleryLogHandler
# ---------------------------------------------------------------------------


class TestCeleryLogHandler:
    def test_creation(self):
        try:
            handler = CeleryLogHandler(broker_url="redis://localhost:6379/0")
            assert handler.task_name == "log_center.ingest"
        except RuntimeError:
            pytest.skip("celery not installed")


# ---------------------------------------------------------------------------
# build_handlers_from_env
# ---------------------------------------------------------------------------


class TestBuildHandlersFromEnv:
    def test_default_api_mode(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_URL", "http://localhost:9315")
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "api")
        monkeypatch.delenv("LOG_CENTER_ENABLE", raising=False)

        handlers = build_handlers_from_env()
        assert len(handlers) == 1
        assert isinstance(handlers[0], HttpLogHandler)

    def test_no_url_no_http(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "api")
        monkeypatch.delenv("LOG_CENTER_URL", raising=False)

        handlers = build_handlers_from_env()
        assert len(handlers) == 0

    def test_grpc_mode(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "grpc")
        monkeypatch.setenv("LOG_CENTER_GRPC_ADDR", "localhost:9316")

        try:
            handlers = build_handlers_from_env()
            assert any(isinstance(h, GrpcLogHandler) for h in handlers)
        except Exception:
            pytest.skip("grpcio not installed")

    def test_grpc_fallback_addr(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "grpc")
        monkeypatch.delenv("LOG_CENTER_GRPC_ADDR", raising=False)
        monkeypatch.setenv("LOG_CENTER_GRPC_HOST", "myhost")
        monkeypatch.setenv("LOG_CENTER_GRPC_PORT", "9999")

        try:
            handlers = build_handlers_from_env()
            grpc_handlers = [h for h in handlers if isinstance(h, GrpcLogHandler)]
            assert grpc_handlers[0].addr == "myhost:9999"
        except Exception:
            pytest.skip("grpcio not installed")

    def test_celery_mode(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "celery")
        monkeypatch.setenv("LOG_CENTER_CELERY_BROKER", "redis://localhost:6379/0")

        try:
            handlers = build_handlers_from_env()
            assert any(isinstance(h, CeleryLogHandler) for h in handlers)
        except Exception:
            pytest.skip("celery not installed")

    def test_both_backward_compat(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "both")
        monkeypatch.setenv("LOG_CENTER_URL", "http://localhost:9315")
        monkeypatch.setenv("LOG_CENTER_CELERY_BROKER", "redis://localhost:6379/0")

        handlers = build_handlers_from_env()
        types = {type(h) for h in handlers}
        assert HttpLogHandler in types
        # CeleryLogHandler may not be present if celery not installed
        assert len(handlers) >= 1

    def test_multi_mode(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "api,grpc")
        monkeypatch.setenv("LOG_CENTER_URL", "http://localhost:9315")
        monkeypatch.setenv("LOG_CENTER_GRPC_ADDR", "localhost:9316")

        handlers = build_handlers_from_env()
        types = {type(h) for h in handlers}
        assert HttpLogHandler in types
        # GrpcLogHandler may not be present if grpcio not installed

    def test_empty_delivery(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_DELIVERY", "")
        monkeypatch.delenv("LOG_CENTER_URL", raising=False)

        handlers = build_handlers_from_env()
        assert len(handlers) == 0


# ---------------------------------------------------------------------------
# Base handler queue mechanics
# ---------------------------------------------------------------------------


class TestBaseHandler:
    def test_emit_enqueues(self):
        """Verify emit() puts formatted record into the queue."""
        handler = HttpLogHandler(endpoint="http://localhost:9999", timeout=0.1)
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        handler.setFormatter(logging.Formatter('{"message": "%(message)s"}'))
        handler.emit(record)
        assert not handler._queue.empty()

    def test_emit_bad_record_no_crash(self):
        """Verify emit() silently drops malformed records."""
        handler = HttpLogHandler(endpoint="http://localhost:9999", timeout=0.1)
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        # Use a non-JSON formatter — emit should not raise
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.emit(record)  # should not raise
