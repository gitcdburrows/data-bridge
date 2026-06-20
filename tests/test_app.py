"""App-surface tests for the refactored bridge.

Covers the changes from the Bloomberg-only / no-auth refactor: the status
dashboard, the trimmed /health payload, the local-only admin guard, and the
fact that auth and the SQL endpoints are gone. No Bloomberg Terminal is
required — blpapi is stubbed in conftest and the client is patched out.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


class _NoopBloombergClient:
    """Stands in for the blpapi-backed client; never reaches a Terminal."""

    _session = None

    def start(self):
        pass

    def stop(self):
        pass

    def open_service(self, _name):
        from app.bloomberg.client import BloombergError

        raise BloombergError("test stub: bloomberg unavailable")

    def send_request(self, _request):
        from app.bloomberg.client import BloombergError

        raise BloombergError("test stub: bloomberg unavailable")


@pytest.fixture()
def client(monkeypatch):
    from app.bloomberg import client as bb_client
    from app.bloomberg import service as bb_service

    stub = _NoopBloombergClient()
    monkeypatch.setattr(bb_client, "get_client", lambda: stub)
    monkeypatch.setattr(bb_service, "get_client", lambda: stub)

    from app.main import create_app

    with TestClient(create_app()) as tc:
        yield tc


def test_dashboard_served_at_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Bloomberg Data Bridge" in resp.text


def test_health_payload_shape(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "version", "bloomberg_connected", "uptime_seconds"}
    # SQL was removed — no database flag should leak into health.
    assert "database_configured" not in body


def test_no_auth_required_on_endpoints(client):
    # With auth removed, a plain request (no key) reaches the backend
    # instead of being rejected — here it 502s on the stubbed Terminal.
    resp = client.post(
        "/reference",
        json={"securities": ["IBM US Equity"], "fields": ["PX_LAST"]},
    )
    assert resp.status_code == 502


def test_sql_endpoints_removed(client):
    assert client.post("/sql/query", json={"sql": "SELECT 1"}).status_code == 404
    assert client.get("/sql/tables").status_code == 404


def test_admin_restart_without_supervisor(client):
    # In-process (no supervisor attached) restart is a no-op that reports so.
    resp = client.post("/admin/restart")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unsupported"


def test_admin_restart_rejects_remote_origin(client):
    resp = client.post(
        "/admin/restart",
        headers={"Origin": "https://universe.thesimplereport.com"},
    )
    assert resp.status_code == 403


def test_admin_restart_allows_local_origin(client):
    resp = client.post(
        "/admin/restart",
        headers={"Origin": "http://localhost:8000"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Start-on-login (per-user, Windows-only)
# ---------------------------------------------------------------------------


def test_autostart_support_matches_platform():
    from app import autostart

    assert autostart.is_supported() == (os.name == "nt")


@pytest.mark.skipif(os.name == "nt", reason="checks the non-Windows fallback")
def test_autostart_is_noop_off_windows():
    from app import autostart

    assert autostart.is_enabled() is False
    autostart.disable()  # must not raise
    with pytest.raises(RuntimeError):
        autostart.enable()


# ---------------------------------------------------------------------------
# App icon
# ---------------------------------------------------------------------------


def test_render_icon_produces_rgba_image():
    pytest.importorskip("PIL")
    from app.icon import render_icon

    img = render_icon(64)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
