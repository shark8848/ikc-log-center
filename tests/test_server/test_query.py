"""Tests for SQLAlchemy ORM and query_logs()."""
from __future__ import annotations

import importlib
import json
import os
import sqlite3

import pytest


def _seed_db(db_path, rows):
    """Directly insert rows into SQLite for query testing."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, level TEXT, logger TEXT, message TEXT,
            trace_id TEXT, span_id TEXT, parent_id TEXT, payload TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_trace ON logs(trace_id)")
    for r in rows:
        conn.execute(
            "INSERT INTO logs (ts, level, logger, message, trace_id, span_id, parent_id, payload) VALUES (?,?,?,?,?,?,?,?)",
            r,
        )
    conn.commit()
    conn.close()


class TestQueryLogs:
    def test_empty_db(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("LOG_CENTER_DB_PATH", db_path)

        import log_center_server.query as query_mod
        importlib.reload(query_mod)

        result = query_mod.query_logs()
        assert result == []

    def test_query_all(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("LOG_CENTER_DB_PATH", db_path)

        rows = [
            ("2025-01-01", "INFO", "test", "hello", "t1", None, None, json.dumps({"message": "hello"})),
            ("2025-01-02", "ERROR", "test", "fail", "t2", None, None, json.dumps({"message": "fail"})),
        ]
        _seed_db(db_path, rows)

        import log_center_server.query as query_mod
        importlib.reload(query_mod)

        result = query_mod.query_logs()
        assert len(result) == 2

    def test_query_by_trace_id(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("LOG_CENTER_DB_PATH", db_path)

        rows = [
            ("2025-01-01", "INFO", "test", "a", "trace-A", None, None, "{}"),
            ("2025-01-02", "INFO", "test", "b", "trace-B", None, None, "{}"),
            ("2025-01-03", "INFO", "test", "c", "trace-A", None, None, "{}"),
        ]
        _seed_db(db_path, rows)

        import log_center_server.query as query_mod
        importlib.reload(query_mod)

        result = query_mod.query_logs(trace_id="trace-A")
        assert len(result) == 2
        assert all(r["trace_id"] == "trace-A" for r in result)

    def test_query_by_level(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("LOG_CENTER_DB_PATH", db_path)

        rows = [
            ("2025-01-01", "INFO", "test", "a", "t1", None, None, "{}"),
            ("2025-01-02", "ERROR", "test", "b", "t2", None, None, "{}"),
        ]
        _seed_db(db_path, rows)

        import log_center_server.query as query_mod
        importlib.reload(query_mod)

        result = query_mod.query_logs(level="ERROR")
        assert len(result) == 1
        assert result[0]["level"] == "ERROR"

    def test_query_message_substr(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("LOG_CENTER_DB_PATH", db_path)

        rows = [
            ("2025-01-01", "INFO", "test", "user login success", "t1", None, None, "{}"),
            ("2025-01-02", "INFO", "test", "data export failed", "t2", None, None, "{}"),
        ]
        _seed_db(db_path, rows)

        import log_center_server.query as query_mod
        importlib.reload(query_mod)

        result = query_mod.query_logs(message_substr="login")
        assert len(result) == 1
        assert "login" in result[0]["message"]

    def test_query_limit_clamped(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("LOG_CENTER_DB_PATH", db_path)

        rows = [("2025-01-01", "INFO", "test", f"msg-{i}", f"t{i}", None, None, "{}") for i in range(10)]
        _seed_db(db_path, rows)

        import log_center_server.query as query_mod
        importlib.reload(query_mod)

        result = query_mod.query_logs(limit=5)
        assert len(result) == 5
