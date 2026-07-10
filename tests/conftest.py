"""Shared test fixtures."""
from __future__ import annotations

import logging

import pytest

from log_center_sdk.core import clear_trace_context


class LogCapture(logging.Handler):
    """Capture log records for assertion."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def last(self) -> logging.LogRecord:
        assert self.records, "No log records captured"
        return self.records[-1]

    def clear(self) -> None:
        self.records.clear()


@pytest.fixture()
def capture():
    handler = LogCapture()
    logger = logging.getLogger("log_center_sdk.instrumentation")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler
    logger.removeHandler(handler)


@pytest.fixture(autouse=True)
def _clean_trace():
    clear_trace_context()
    yield
    clear_trace_context()
