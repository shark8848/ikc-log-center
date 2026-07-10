"""Unit tests for @instrumented decorator."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import pytest

from log_center_sdk.core import clear_trace_context, set_trace_context
from log_center_sdk.instrumentation import _safe_value, instrumented


# ---------------------------------------------------------------------------
# _safe_value
# ---------------------------------------------------------------------------


class TestSafeValue:
    def test_primitives(self):
        assert _safe_value("hello") == "hello"
        assert _safe_value(42) == 42
        assert _safe_value(3.14) == 3.14
        assert _safe_value(True) is True
        assert _safe_value(None) is None

    def test_list_truncated(self):
        class Obj:
            pass

        result = _safe_value([1, "two", Obj(), 4])
        assert result == [1, "two", "Obj", 4]

    def test_list_capped(self):
        assert len(_safe_value(list(range(20)))) == 10

    def test_dict_recursive(self):
        result = _safe_value({"a": 1, "b": [1, 2], "c": object()})
        assert result["a"] == 1
        assert result["b"] == [1, 2]
        assert isinstance(result["c"], str)

    def test_repr_truncated(self):
        class Long:
            def __repr__(self):
                return "x" * 500

        assert len(_safe_value(Long())) == 200


# ---------------------------------------------------------------------------
# Sync functions
# ---------------------------------------------------------------------------


class TestInstrumentedSync:
    def test_basic(self, capture):
        @instrumented("test_event")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(1, 2) == 3
        rec = capture.last()
        assert rec.levelno == logging.INFO
        assert "completed" in rec.getMessage()
        assert rec.event == "test_event"
        assert rec.status == "ok"
        assert rec.call_args == {"a": 1, "b": 2}

    def test_preserves_name(self, capture):
        @instrumented("evt")
        def my_func():
            pass

        assert my_func.__name__ == "my_func"

    def test_log_args_whitelist(self, capture):
        @instrumented("evt", log_args={"model"})
        def call(prompt: str, model: str, temperature: float):
            pass

        call("hello", "gpt-4", 0.7)
        assert capture.last().call_args == {"model": "gpt-4"}

    def test_redact_args(self, capture):
        @instrumented("evt", redact_args={"api_key"})
        def call(prompt: str, api_key: str):
            pass

        call("hello", "sk-secret")
        rec = capture.last()
        assert rec.call_args["prompt"] == "hello"
        assert rec.call_args["api_key"] == "***"

    def test_combined_filter(self, capture):
        @instrumented("evt", log_args={"model", "api_key"}, redact_args={"api_key"})
        def call(prompt: str, model: str, api_key: str):
            pass

        call("hi", "gpt-4", "sk-123")
        rec = capture.last()
        assert "prompt" not in rec.call_args
        assert rec.call_args["model"] == "gpt-4"
        assert rec.call_args["api_key"] == "***"

    def test_exception_reraised(self, capture):
        @instrumented("evt")
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fail()

        rec = capture.last()
        assert rec.levelno == logging.ERROR
        assert rec.status == "error"
        assert rec.error_type == "ValueError"
        assert rec.error_message == "boom"

    def test_log_result(self, capture):
        @instrumented("evt", log_result=True)
        def make_list():
            return [1, 2, 3]

        assert make_list() == [1, 2, 3]
        rec = capture.last()
        assert rec.result_type == "list"
        assert rec.result_len == 3

    def test_log_result_none(self, capture):
        @instrumented("evt", log_result=True)
        def noop():
            return None

        noop()
        assert not hasattr(capture.last(), "result_type")

    def test_log_result_no_len(self, capture):
        @instrumented("evt", log_result=True)
        def scalar():
            return 42

        scalar()
        rec = capture.last()
        assert rec.result_type == "int"
        assert not hasattr(rec, "result_len")

    def test_component(self, capture):
        @instrumented("evt", component="docling")
        def fn():
            pass

        fn()
        assert capture.last().component == "docling"

    def test_slow_threshold(self, capture):
        @instrumented("evt", slow_threshold_ms=10)
        def slow():
            time.sleep(0.05)

        slow()
        rec = capture.last()
        assert rec.levelno == logging.WARNING
        assert "slow" in rec.getMessage()

    def test_fast_stays_info(self, capture):
        @instrumented("evt", slow_threshold_ms=5000)
        def fast():
            return 1

        fast()
        assert capture.last().levelno == logging.INFO

    def test_trace_context(self, capture):
        set_trace_context(trace_id="t-100", request_id="r-200")

        @instrumented("evt")
        def fn():
            pass

        fn()
        rec = capture.last()
        assert rec.trace_id == "t-100"
        assert rec.request_id == "r-200"
        assert not hasattr(rec, "span_id")

    def test_unserialisable_arg(self, capture):
        class Widget:
            def __repr__(self):
                return "Widget(id=5)"

        @instrumented("evt")
        def fn(w: Widget):
            pass

        fn(Widget())
        assert capture.last().call_args["w"] == "Widget(id=5)"

    def test_kwargs(self, capture):
        @instrumented("evt")
        def fn(a: int, b: int = 10):
            pass

        fn(1, b=20)
        assert capture.last().call_args == {"a": 1, "b": 20}

    def test_defaults(self, capture):
        @instrumented("evt")
        def fn(a: int, b: int = 99):
            pass

        fn(1)
        assert capture.last().call_args == {"a": 1, "b": 99}


# ---------------------------------------------------------------------------
# Async functions
# ---------------------------------------------------------------------------


class TestInstrumentedAsync:
    @pytest.mark.asyncio
    async def test_basic(self, capture):
        @instrumented("async_evt")
        async def fetch(url: str) -> str:
            return f"ok:{url}"

        assert await fetch("http://example.com") == "ok:http://example.com"
        rec = capture.last()
        assert rec.status == "ok"
        assert rec.event == "async_evt"
        assert rec.call_args == {"url": "http://example.com"}

    @pytest.mark.asyncio
    async def test_exception(self, capture):
        @instrumented("evt")
        async def fail():
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            await fail()

        rec = capture.last()
        assert rec.levelno == logging.ERROR
        assert rec.error_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_slow(self, capture):
        @instrumented("evt", slow_threshold_ms=10)
        async def slow():
            await asyncio.sleep(0.05)

        await slow()
        assert capture.last().levelno == logging.WARNING

    @pytest.mark.asyncio
    async def test_preserves_name(self, capture):
        @instrumented("evt")
        async def my_async():
            pass

        assert my_async.__name__ == "my_async"

    @pytest.mark.asyncio
    async def test_trace(self, capture):
        set_trace_context(trace_id="at-1", span_id="as-1")

        @instrumented("evt")
        async def fn():
            pass

        await fn()
        rec = capture.last()
        assert rec.trace_id == "at-1"
        assert rec.span_id == "as-1"

    @pytest.mark.asyncio
    async def test_log_result(self, capture):
        @instrumented("evt", log_result=True)
        async def make_dict():
            return {"a": 1, "b": 2}

        await make_dict()
        rec = capture.last()
        assert rec.result_type == "dict"
        assert rec.result_len == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_args(self, capture):
        @instrumented("evt")
        def noop():
            return "done"

        assert noop() == "done"
        rec = capture.last()
        assert not hasattr(rec, "call_args") or rec.call_args == {}

    def test_none_value(self, capture):
        @instrumented("evt")
        def fn(x: Any = None):
            pass

        fn()
        assert capture.last().call_args == {"x": None}

    def test_empty_whitelist(self, capture):
        @instrumented("evt", log_args=set())
        def fn(a: int, b: int):
            pass

        fn(1, 2)
        rec = capture.last()
        assert not hasattr(rec, "call_args") or rec.call_args == {}

    def test_custom_levels(self, capture):
        @instrumented("evt", level=logging.DEBUG, error_level=logging.CRITICAL)
        def fn(ok: bool):
            if not ok:
                raise ValueError("fail")

        fn(True)
        assert capture.last().levelno == logging.DEBUG

        with pytest.raises(ValueError):
            fn(False)
        assert capture.last().levelno == logging.CRITICAL

    def test_multiple_calls(self, capture):
        @instrumented("evt")
        def fn(n: int):
            return n

        fn(1)
        fn(2)
        fn(3)
        assert len(capture.records) == 3
