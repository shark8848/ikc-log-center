"""Tests for FastAPI endpoints: /ingest, /health, /search."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a fresh app instance with isolated storage."""
    import importlib
    import log_center_server.storage as storage_mod
    import log_center_server.app as app_mod

    importlib.reload(storage_mod)
    importlib.reload(app_mod)
    return app_mod.app


@pytest.mark.asyncio
class TestHealth:
    async def test_health(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
class TestIngest:
    async def test_ingest_single_entry(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/ingest", json={"ts": "2025-01-01", "level": "INFO", "message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["stored"] == 1

    async def test_ingest_batch(self, app):
        entries = [
            {"ts": "2025-01-01", "level": "INFO", "message": "a"},
            {"ts": "2025-01-02", "level": "WARN", "message": "b"},
            {"ts": "2025-01-03", "level": "ERROR", "message": "c"},
        ]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/ingest", json=entries)
        assert resp.status_code == 200
        assert resp.json()["stored"] == 3

    async def test_ingest_invalid_payload(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/ingest", content="not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_ingest_empty_list(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/ingest", json=[])
        assert resp.status_code == 200
        assert resp.json()["stored"] == 0

    async def test_ingest_string_payload(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/ingest", json="just a string")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        assert "payload must be object or list" in resp.json()["reason"]

    async def test_ingest_trace_id_from_header(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/ingest",
                json={"level": "INFO", "message": "traced"},
                headers={"x-trace-id": "header-trace-123"},
            )
        assert resp.status_code == 200
        assert resp.json()["stored"] == 1


@pytest.mark.asyncio
class TestSearch:
    async def test_search_empty(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Ensure DB is initialized
            await client.get("/health")
            resp = await client.get("/search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_search_after_ingest(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Ingest entries with a specific trace_id
            entries = [
                {"ts": "2025-01-01", "level": "INFO", "message": "a", "trace_id": "search-test-123"},
                {"ts": "2025-01-02", "level": "ERROR", "message": "b", "trace_id": "search-test-123"},
                {"ts": "2025-01-03", "level": "INFO", "message": "c", "trace_id": "other"},
            ]
            await client.post("/ingest", json=entries)

            # Search by trace_id
            resp = await client.get("/search", params={"trace_id": "search-test-123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["count"] == 2

    async def test_search_limit_clamped(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/search", params={"limit": 9999})
        assert resp.status_code == 200
