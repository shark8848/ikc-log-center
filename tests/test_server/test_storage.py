"""Tests for storage backends: normalize, file, sqlite, dispatch, forward."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


class TestNormalizeEntries:
    def test_filters_non_dict(self):
        from log_center_server.storage import normalize_entries

        result = normalize_entries([{"a": 1}, "bad", 42, {"b": 2}])
        assert len(result) == 2
        assert result[0] == {"a": 1}
        assert result[1] == {"b": 2}

    def test_injects_trace_id_hint(self):
        from log_center_server.storage import normalize_entries

        entries = [{"message": "hello"}]
        result = normalize_entries(entries, trace_id_hint="abc123")
        assert result[0]["trace_id"] == "abc123"

    def test_does_not_override_existing_trace_id(self):
        from log_center_server.storage import normalize_entries

        entries = [{"message": "hello", "trace_id": "existing"}]
        result = normalize_entries(entries, trace_id_hint="new")
        assert result[0]["trace_id"] == "existing"

    def test_empty_list(self):
        from log_center_server.storage import normalize_entries

        assert normalize_entries([]) == []


class TestWriteFile:
    def test_appends_jsonl(self, tmp_path, monkeypatch):
        log_file = tmp_path / "test.log"
        monkeypatch.setenv("LOG_CENTER_FILE", str(log_file))

        # Re-import to pick up the env change
        import importlib
        import log_center_server.storage as storage_mod
        importlib.reload(storage_mod)

        entries = [{"ts": "2025-01-01", "level": "INFO", "message": "test1"}]
        storage_mod.write_file(entries)

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["message"] == "test1"

    def test_truncates_at_cap(self, tmp_path, monkeypatch):
        log_file = tmp_path / "test.log"
        monkeypatch.setenv("LOG_CENTER_FILE", str(log_file))
        monkeypatch.setenv("LOG_CENTER_MAX_LOCAL_MB", "0.001")  # ~1KB

        import importlib
        import log_center_server.storage as storage_mod
        importlib.reload(storage_mod)

        # Write enough data to exceed 1KB
        big_entries = [{"data": "x" * 2000}]
        storage_mod.write_file(big_entries)
        assert log_file.stat().st_size > 0

        # Write again — should trigger truncation then append
        small_entries = [{"ts": "after"}]
        storage_mod.write_file(small_entries)
        content = log_file.read_text().strip()
        lines = content.split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["ts"] == "after"


class TestSqlite:
    def test_init_creates_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("LOG_CENTER_DB_PATH", str(db_path))

        import importlib
        import log_center_server.storage as storage_mod
        importlib.reload(storage_mod)

        storage_mod.init_sqlite()
        assert db_path.exists()

        conn = sqlite3.connect(db_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert ("logs",) in tables
        conn.close()

    def test_write_sqlite_inserts_rows(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("LOG_CENTER_DB_PATH", str(db_path))

        import importlib
        import log_center_server.storage as storage_mod
        importlib.reload(storage_mod)

        storage_mod.init_sqlite()
        entries = [
            {"ts": "2025-01-01", "level": "INFO", "logger": "test", "message": "hello", "trace_id": "t1"},
            {"ts": "2025-01-02", "level": "ERROR", "logger": "test", "message": "err", "trace_id": "t2"},
        ]
        storage_mod.write_sqlite(entries)

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT * FROM logs").fetchall()
        assert len(rows) == 2
        conn.close()


class TestWriteBackend:
    def test_dispatches_local(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("LOG_CENTER_DB_PATH", str(db_path))
        monkeypatch.setenv("LOG_CENTER_STORE", "local")

        import importlib
        import log_center_server.storage as storage_mod
        importlib.reload(storage_mod)

        storage_mod.init_sqlite()
        storage_mod.write_backend([{"ts": "now", "level": "INFO", "message": "test"}])

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT * FROM logs").fetchall()
        assert len(rows) == 1
        conn.close()


class TestForwardEntries:
    def test_no_urls_noop(self):
        from log_center_server.storage import forward_entries
        # Should not raise when FORWARD_URLS is empty
        forward_entries([{"test": True}])

    def test_posts_to_urls(self, monkeypatch):
        monkeypatch.setenv("LOG_CENTER_FORWARD_URLS", "http://a:9315,http://b:9315")

        import importlib
        import log_center_server.storage as storage_mod
        importlib.reload(storage_mod)

        posted = []

        def mock_post(url, json=None, timeout=None):
            posted.append((url, json))
            class R:
                status_code = 200
            return R()

        with patch.object(storage_mod.requests, "post", side_effect=mock_post):
            storage_mod.forward_entries([{"msg": "hello"}])

        assert len(posted) == 2
        assert posted[0][0] == "http://a:9315/ingest"
        assert posted[1][0] == "http://b:9315/ingest"
