"""Unit tests for core.py — trace context, JsonFormatter, configure()."""
from __future__ import annotations

import json
import logging
import os

import pytest

from log_center_sdk.core import (
    JsonFormatter,
    TraceContextFilter,
    clear_trace_context,
    configure,
    get_logger,
    request_id_var,
    set_trace_context,
    span_id_var,
    trace_id_var,
)


# ---------------------------------------------------------------------------
# Trace context
# ---------------------------------------------------------------------------


class TestTraceContext:
    def test_default_none(self):
        assert trace_id_var.get() is None
        assert span_id_var.get() is None
        assert request_id_var.get() is None

    def test_set_and_get(self):
        set_trace_context(trace_id="t-1", span_id="s-1", request_id="r-1")
        assert trace_id_var.get() == "t-1"
        assert span_id_var.get() == "s-1"
        assert request_id_var.get() == "r-1"

    def test_partial_set(self):
        set_trace_context(trace_id="t-2")
        assert trace_id_var.get() == "t-2"
        assert span_id_var.get() is None

    def test_clear(self):
        set_trace_context(trace_id="t-3", span_id="s-3")
        clear_trace_context()
        assert trace_id_var.get() is None
        assert span_id_var.get() is None


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    def _make_record(self, msg="test", level=logging.INFO, **extra):
        record = logging.LogRecord(
            name="test.logger", level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_basic_json(self):
        fmt = JsonFormatter()
        record = self._make_record("hello world")
        output = json.loads(fmt.format(record))
        assert output["message"] == "hello world"
        assert output["level"] == "INFO"
        assert output["logger"] == "test.logger"
        assert "ts" in output

    def test_extras_merged(self):
        fmt = JsonFormatter()
        record = self._make_record("evt", event="my_event", duration_ms=42.5)
        output = json.loads(fmt.format(record))
        assert output["event"] == "my_event"
        assert output["duration_ms"] == 42.5

    def test_trace_context_included(self):
        fmt = JsonFormatter()
        record = self._make_record("evt")
        record.trace_id = "t-100"
        record.request_id = "r-200"
        output = json.loads(fmt.format(record))
        assert output["trace_id"] == "t-100"
        assert output["request_id"] == "r-200"

    def test_exc_info(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            record = self._make_record("failed")
            record.exc_info = sys.exc_info()
            output = json.loads(fmt.format(record))
            assert "ValueError" in output["exc_info"]


# ---------------------------------------------------------------------------
# TraceContextFilter
# ---------------------------------------------------------------------------


class TestTraceContextFilter:
    def test_injects_context(self):
        set_trace_context(trace_id="t-f1", span_id="s-f1")
        filt = TraceContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert filt.filter(record) is True
        assert record.trace_id == "t-f1"
        assert record.span_id == "s-f1"
        assert not hasattr(record, "request_id")

    def test_no_context_no_attrs(self):
        filt = TraceContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        filt.filter(record)
        assert not hasattr(record, "trace_id")


# ---------------------------------------------------------------------------
# configure()
# ---------------------------------------------------------------------------


class TestConfigure:
    def test_idempotent(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOG_FILE_PATH", str(tmp_path / "test.log"))
        monkeypatch.setenv("LOG_FILE_ENABLE", "true")
        monkeypatch.delenv("LOG_CENTER_ENABLE", raising=False)

        configure(_force=True)
        handlers_count = len(logging.getLogger().handlers)
        configure()  # second call — should be no-op
        assert len(logging.getLogger().handlers) == handlers_count

    def test_force_reinit(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOG_FILE_PATH", str(tmp_path / "test.log"))
        monkeypatch.setenv("LOG_FILE_ENABLE", "true")
        monkeypatch.delenv("LOG_CENTER_ENABLE", raising=False)

        configure(_force=True)
        first_count = len(logging.getLogger().handlers)
        configure(_force=True)
        assert len(logging.getLogger().handlers) == first_count

    def test_json_output_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOG_FILE_PATH", str(tmp_path / "test.log"))
        monkeypatch.setenv("LOG_FILE_ENABLE", "true")
        monkeypatch.delenv("LOG_JSON", raising=False)
        monkeypatch.delenv("LOG_CENTER_ENABLE", raising=False)

        configure(_force=True)
        root = logging.getLogger()
        # First handler is console — should be JsonFormatter
        assert isinstance(root.handlers[0].formatter, JsonFormatter)


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("my.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "my.module"

    def test_level_override(self):
        logger = get_logger("my.module2", level="DEBUG")
        assert logger.level == logging.DEBUG
