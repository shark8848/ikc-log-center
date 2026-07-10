"""Server test fixtures — isolate all storage to tmp_path."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_server(tmp_path, monkeypatch):
    """Point all server storage at tmp_path to avoid polluting real paths."""
    monkeypatch.setenv("LOG_CENTER_FILE", str(tmp_path / "test.log"))
    monkeypatch.setenv("LOG_CENTER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LOG_CENTER_STORE", "local")
    monkeypatch.delenv("LOG_CENTER_FORWARD_URLS", raising=False)
    monkeypatch.delenv("LOG_CENTER_CELERY_ENABLE", raising=False)
    monkeypatch.delenv("LOG_CENTER_ES_ENDPOINT", raising=False)
    monkeypatch.delenv("LOG_CENTER_MYSQL_HOST", raising=False)
    monkeypatch.delenv("LOG_CENTER_PG_HOST", raising=False)
