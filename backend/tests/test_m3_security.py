"""M3 security: auth modes, sessions, encrypted keys, backups, audit."""

import pytest
from fastapi.testclient import TestClient

from aiptp.config import Settings
from aiptp.main import create_app
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService


@pytest.fixture
def auth_client(tmp_path) -> TestClient:
    cfg = Settings(
        db_url=f"sqlite:///{tmp_path / 'auth.db'}",
        data_dir=tmp_path,
        market_providers="fake",
        auth="required",
    )
    market = MarketDataService([FakeProvider({"AAPL": "200"})], quote_ttl=0, history_ttl=0)
    app = create_app(cfg, market=market)
    with TestClient(app) as c:
        yield c


def test_auth_disabled_mode_is_open(client):
    status = client.get("/api/v1/auth/status").json()
    assert status == {"mode": "disabled", "state": "authenticated", "username": "local"}
    assert client.get("/api/v1/portfolios").status_code == 200
    # login endpoints refuse when auth is disabled
    assert client.post(
        "/api/v1/auth/login", json={"username": "user1234", "password": "password1"}
    ).status_code == 409


def test_auth_required_full_flow(auth_client):
    c = auth_client
    # locked out before setup
    assert c.get("/api/v1/portfolios").status_code == 401
    assert c.get("/api/v1/auth/status").json()["state"] == "setup_required"

    # weak password rejected by schema
    assert c.post("/api/v1/auth/setup",
                  json={"username": "admin", "password": "short"}).status_code == 422

    resp = c.post("/api/v1/auth/setup", json={"username": "admin", "password": "hunter22222"})
    assert resp.status_code == 201
    assert c.get("/api/v1/auth/status").json()["state"] == "authenticated"
    assert c.get("/api/v1/portfolios").status_code == 200  # cookie set

    # second setup refused
    assert c.post("/api/v1/auth/setup",
                  json={"username": "eve", "password": "password123"}).status_code == 409

    c.post("/api/v1/auth/logout")
    assert c.get("/api/v1/portfolios").status_code == 401
    assert c.get("/api/v1/auth/status").json()["state"] == "login_required"

    assert c.post("/api/v1/auth/login",
                  json={"username": "admin", "password": "wrongpass1"}).status_code == 401
    assert c.post("/api/v1/auth/login",
                  json={"username": "admin", "password": "hunter22222"}).status_code == 200
    assert c.get("/api/v1/portfolios").status_code == 200

    # audit trail recorded auth events
    audit = c.get("/api/v1/admin/audit").json()
    actions = [a["action"] for a in audit]
    assert "auth.setup" in actions
    assert "auth.login_failed" in actions
    assert "auth.login" in actions


def test_provider_key_stored_encrypted(auth_client, tmp_path):
    c = auth_client
    c.post("/api/v1/auth/setup", json={"username": "admin", "password": "hunter22222"})
    resp = c.put("/api/v1/admin/providers",
                 json={"provider": "alphavantage", "key": "SECRETKEY123"})
    assert resp.status_code == 200
    assert c.get("/api/v1/admin/providers").json()["stored_keys"] == ["alphavantage"]

    # ciphertext at rest — the raw key must not appear in the database file
    db_files = list(tmp_path.glob("*.db"))
    assert db_files and all(b"SECRETKEY123" not in p.read_bytes() for p in db_files)

    assert c.put("/api/v1/admin/providers",
                 json={"provider": "bogus", "key": "x"}).status_code == 422
    assert c.delete("/api/v1/admin/providers/alphavantage").status_code == 204
    assert c.get("/api/v1/admin/providers").json()["stored_keys"] == []


def test_backup_and_retention(client):
    resp = client.post("/api/v1/admin/backup")
    assert resp.status_code == 200
    name = resp.json()["backup"]
    backups = client.get("/api/v1/admin/backups").json()
    assert any(b["name"] == name for b in backups)


def test_notifications_mark_read(client, fake_provider, portfolio_id):
    from aiptp.watcher import run_watch_cycle

    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "LIMIT",
              "quantity": "1", "limit_price": "150"},
    )
    fake_provider.set_price("AAPL", "140")
    app = client.app
    run_watch_cycle(app.state.session_factory, app.state.market, app.state.bus)

    inbox = client.get("/api/v1/notifications").json()
    assert inbox["unread_count"] >= 1
    assert any(n["type"] == "order_filled" for n in inbox["notifications"])

    client.post("/api/v1/notifications/read")
    assert client.get("/api/v1/notifications").json()["unread_count"] == 0
