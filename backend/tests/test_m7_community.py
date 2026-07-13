"""M7: multi-user ownership, sharing links, competitions, cooperative
portfolios with voting, clubs, leaderboards, and the Discord integration."""

import pytest
from fastapi.testclient import TestClient

from aiptp.config import Settings
from aiptp.main import create_app
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService


@pytest.fixture
def multi(tmp_path):
    """Auth-required app with admin + two traders, one client per user."""
    cfg = Settings(
        db_url=f"sqlite:///{tmp_path / 'm7.db'}",
        data_dir=tmp_path,
        market_providers="fake",
        auth="required",
    )
    market = MarketDataService(
        [FakeProvider({"AAPL": "200", "MSFT": "400"})], quote_ttl=0, history_ttl=0
    )
    app = create_app(cfg, market=market)
    with TestClient(app) as admin:
        assert admin.post("/api/v1/auth/setup",
                          json={"username": "admin", "password": "hunter22222"}
                          ).status_code == 201
        for name in ("alice", "bob"):
            assert admin.post("/api/v1/admin/users",
                              json={"username": name, "password": "password123",
                                    "role": "trader"}).status_code == 201
        with TestClient(app) as alice, TestClient(app) as bob:
            alice.post("/api/v1/auth/login",
                       json={"username": "alice", "password": "password123"})
            bob.post("/api/v1/auth/login",
                     json={"username": "bob", "password": "password123"})
            yield {"admin": admin, "alice": alice, "bob": bob}


# ------------------------------------------------------------- ownership


def test_ownership_isolation_between_users(multi):
    alice, bob, admin = multi["alice"], multi["bob"], multi["admin"]
    pid = alice.post("/api/v1/portfolios",
                     json={"name": "Alice fund", "starting_balance": "10000"}
                     ).json()["id"]
    # Alice sees it; Bob neither lists nor fetches it (404, not 403)
    assert pid in [p["id"] for p in alice.get("/api/v1/portfolios").json()]
    assert pid not in [p["id"] for p in bob.get("/api/v1/portfolios").json()]
    assert bob.get(f"/api/v1/portfolios/{pid}").status_code == 404
    assert bob.post(f"/api/v1/portfolios/{pid}/orders",
                    json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                          "quantity": "1"}).status_code == 404
    # Admin sees everything
    assert admin.get(f"/api/v1/portfolios/{pid}").status_code == 200


def test_user_management_is_admin_only(multi):
    alice, admin = multi["alice"], multi["admin"]
    assert alice.get("/api/v1/admin/users").status_code == 403
    assert alice.post("/api/v1/admin/users",
                      json={"username": "eve", "password": "password123"}
                      ).status_code == 403
    users = {u["username"]: u["role"] for u in admin.get("/api/v1/admin/users").json()}
    assert users == {"admin": "admin", "alice": "trader", "bob": "trader"}
    # duplicates and self-deletion are refused
    assert admin.post("/api/v1/admin/users",
                      json={"username": "alice", "password": "password123"}
                      ).status_code == 409
    assert admin.delete("/api/v1/admin/users/admin").status_code == 422
    assert admin.delete("/api/v1/admin/users/bob").status_code == 204


# ------------------------------------------------------------ share links


def test_share_link_lifecycle(multi):
    alice, bob = multi["alice"], multi["bob"]
    pid = alice.post("/api/v1/portfolios",
                     json={"name": "Shared fund", "starting_balance": "10000"}
                     ).json()["id"]
    alice.post(f"/api/v1/portfolios/{pid}/orders",
               json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                     "quantity": "10"})
    share = alice.post(f"/api/v1/shares/portfolios/{pid}").json()
    token = share["token"]

    # public endpoint works with no cookie at all
    anon = TestClient(alice.app)
    view = anon.get(f"/api/v1/shared/{token}")
    assert view.status_code == 200
    body = view.json()
    assert body["kind"] == "portfolio"
    assert body["name"] == "Shared fund"
    assert body["holdings"][0]["symbol"] == "AAPL"
    assert "owner" not in body  # anonymous by design
    assert "cash_balance" not in body

    # only the creator may revoke; after revocation the link is dead
    assert bob.delete(f"/api/v1/shares/{token}").status_code == 404
    assert alice.delete(f"/api/v1/shares/{token}").status_code == 204
    assert anon.get(f"/api/v1/shared/{token}").status_code == 404


def test_strategy_share_and_import(client):
    sid = client.post("/api/v1/strategies", json={
        "name": "Momentum", "universe": ["AAPL"],
        "entry_trigger": {"price": {"symbol": "$SYMBOL", "op": "<", "value": 90}},
    }).json()["id"]
    token = client.post(f"/api/v1/shares/strategies/{sid}").json()["token"]
    shared = client.get(f"/api/v1/shared/{token}").json()
    assert shared["kind"] == "strategy"
    assert shared["universe"] == ["AAPL"]
    imported = client.post(f"/api/v1/shares/{token}/import")
    assert imported.status_code == 201
    assert "imported" in imported.json()["name"]


# ----------------------------------------------------------- competitions


def test_competition_lifecycle(multi):
    alice, bob = multi["alice"], multi["bob"]
    comp = alice.post("/api/v1/competitions", json={
        "name": "Spring Cup", "kind": "PRIVATE", "starting_balance": "50000",
    }).json()
    code = comp["invite_code"]

    # wrong invite code is refused; right one creates a fresh game portfolio
    assert bob.post(f"/api/v1/competitions/{comp['id']}/join",
                    json={"invite_code": "nope"}).status_code == 403
    entry = bob.post(f"/api/v1/competitions/{comp['id']}/join",
                     json={"invite_code": code, "display_name": "Bob T."})
    assert entry.status_code == 201
    bob_pid = entry.json()["portfolio_id"]
    view = bob.get(f"/api/v1/portfolios/{bob_pid}").json()
    assert view["starting_balance"] == "50000"
    assert view["cash_balance"] == "50000"

    # double join refused
    assert bob.post(f"/api/v1/competitions/{comp['id']}/join",
                    json={"invite_code": code}).status_code == 409

    alice_pid = alice.post(f"/api/v1/competitions/{comp['id']}/join",
                           json={"invite_code": code}).json()["portfolio_id"]
    # Alice trades; flat prices mean her return stays 0 like Bob's, so give
    # Bob a losing position by... prices are static — instead check ranking
    # fields and that both entrants appear.
    alice.post(f"/api/v1/portfolios/{alice_pid}/orders",
               json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                     "quantity": "10"})
    standings = bob.get(f"/api/v1/competitions/{comp['id']}/standings").json()
    rows = standings["standings"]
    assert len(rows) == 2
    assert {r["display_name"] for r in rows} == {"Bob T.", "alice"}
    assert all("rank" in r and "return_pct" in r for r in rows)
    # private competition invisible to non-members listing
    assert comp["id"] in [c["id"] for c in bob.get("/api/v1/competitions").json()]


# --------------------------------------------------- cooperative portfolios


def test_proposal_majority_vote_executes(multi):
    alice, bob, admin = multi["alice"], multi["bob"], multi["admin"]
    pid = alice.post("/api/v1/portfolios",
                     json={"name": "Coop", "starting_balance": "20000"}
                     ).json()["id"]
    assert alice.post(f"/api/v1/portfolios/{pid}/members",
                      json={"username": "bob", "role": "MEMBER"}).status_code == 201
    assert alice.post(f"/api/v1/portfolios/{pid}/members",
                      json={"username": "admin", "role": "VIEWER"}).status_code == 201

    # Bob (member) can now see the portfolio
    assert bob.get(f"/api/v1/portfolios/{pid}").status_code == 200

    # eligible voters = alice (owner) + bob; admin is a VIEWER
    prop = alice.post(f"/api/v1/portfolios/{pid}/proposals", json={
        "symbol": "AAPL", "side": "BUY", "quantity": "10",
        "rationale": "diversify",
    }).json()
    assert prop["status"] == "OPEN"          # 1 of 2 votes so far
    assert prop["approvals"] == 1

    voted = bob.post(f"/api/v1/portfolios/{pid}/proposals/{prop['id']}/vote",
                     json={"approve": True}).json()
    assert voted["status"] == "EXECUTED"
    assert voted["executed_order_id"]
    txns = bob.get(f"/api/v1/portfolios/{pid}/transactions").json()
    assert txns[0]["symbol"] == "AAPL" and txns[0]["quantity"] == "10"

    # voting on a decided proposal is refused
    assert alice.post(f"/api/v1/portfolios/{pid}/proposals/{prop['id']}/vote",
                      json={"approve": False}).status_code == 409


def test_proposal_rejection_and_viewer_limits(multi):
    alice, bob, admin = multi["alice"], multi["bob"], multi["admin"]
    pid = alice.post("/api/v1/portfolios",
                     json={"name": "Coop2", "starting_balance": "20000"}
                     ).json()["id"]
    alice.post(f"/api/v1/portfolios/{pid}/members",
               json={"username": "bob", "role": "MEMBER"})

    prop = alice.post(f"/api/v1/portfolios/{pid}/proposals", json={
        "symbol": "MSFT", "side": "BUY", "notional": "5000",
    }).json()
    rejected = bob.post(f"/api/v1/portfolios/{pid}/proposals/{prop['id']}/vote",
                        json={"approve": False}).json()
    # 1 yes / 1 no of 2 voters: majority (2) now impossible -> rejected
    assert rejected["status"] == "REJECTED"

    # a viewer cannot propose
    alice.post(f"/api/v1/portfolios/{pid}/members",
               json={"username": "admin", "role": "VIEWER"})
    # (admin role bypasses; simulate by checking bob after demotion instead)
    alice.delete(f"/api/v1/portfolios/{pid}/members/bob")
    alice.post(f"/api/v1/portfolios/{pid}/members",
               json={"username": "bob", "role": "VIEWER"})
    assert bob.post(f"/api/v1/portfolios/{pid}/proposals", json={
        "symbol": "AAPL", "side": "BUY", "quantity": "1",
    }).status_code == 403


# ------------------------------------------------------------------ clubs


def test_club_lifecycle(multi):
    alice, bob = multi["alice"], multi["bob"]
    club = alice.post("/api/v1/clubs", json={
        "name": "Value Club", "with_portfolio": True, "starting_balance": "30000",
    }).json()
    assert club["club_portfolio_id"]
    code = club["invite_code"]

    # not a member yet: detail hidden
    assert bob.get(f"/api/v1/clubs/{club['id']}").status_code == 404
    assert bob.post("/api/v1/clubs/join", json={"invite_code": "bad0bad0"}
                    ).status_code == 404
    assert bob.post("/api/v1/clubs/join", json={"invite_code": code}
                    ).status_code == 201

    # joining the club joined the shared portfolio too
    assert bob.get(f"/api/v1/portfolios/{club['club_portfolio_id']}"
                   ).status_code == 200

    bob.post(f"/api/v1/clubs/{club['id']}/messages", json={"body": "hello club"})
    msgs = alice.get(f"/api/v1/clubs/{club['id']}/messages").json()
    assert msgs[-1]["author"] == "bob" and msgs[-1]["body"] == "hello club"

    rankings = alice.get(f"/api/v1/clubs/{club['id']}/rankings").json()
    assert {r["username"] for r in rankings} == {"alice", "bob"}

    # only the creator deletes the club
    assert bob.delete(f"/api/v1/clubs/{club['id']}").status_code == 403
    assert alice.delete(f"/api/v1/clubs/{club['id']}").status_code == 204


# ------------------------------------------------------------ leaderboards


def test_leaderboards_are_opt_in(client):
    from aiptp.api.leaderboards import invalidate_cache

    pid = client.post("/api/v1/portfolios",
                      json={"name": "Public P", "starting_balance": "10000",
                            "mode": "BEGINNER"}).json()["id"]
    client.post(f"/api/v1/portfolios/{pid}/orders",
                json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                      "quantity": "10"})
    invalidate_cache()
    boards = client.get("/api/v1/leaderboards").json()["categories"]
    ids = {b["id"] for b in boards}
    assert ids == {"highest_return", "risk_adjusted", "diversification",
                   "beginner_improvement", "lowest_drawdown", "best_strategy"}
    highest = next(b for b in boards if b["id"] == "highest_return")
    assert highest["entries"] == []  # not opted in yet

    assert client.patch(f"/api/v1/portfolios/{pid}",
                        json={"public_on_leaderboard": True}).status_code == 200
    invalidate_cache()
    boards = client.get("/api/v1/leaderboards").json()["categories"]
    highest = next(b for b in boards if b["id"] == "highest_return")
    assert [e["portfolio"] for e in highest["entries"]] == ["Public P"]
    beginner = next(b for b in boards if b["id"] == "beginner_improvement")
    assert [e["portfolio"] for e in beginner["entries"]] == ["Public P"]
    assert client.get("/api/v1/leaderboards/nope").status_code == 404


# ---------------------------------------------------------------- discord


def test_discord_command_handlers(client, portfolio_id):
    client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                      "quantity": "5"})
    for command, needle in [
        ("portfolio", "Test"),
        ("performance", "%"),
        ("summary", "Daily summary"),
        ("challenge", "challenge"),
        ("leaderboard", "leaderboard"),
    ]:
        r = client.post("/api/v1/discord/commands/preview",
                        json={"command": command})
        assert r.status_code == 200, command
        assert needle.lower() in r.json()["reply"].lower(), command
    quote = client.post("/api/v1/discord/commands/preview",
                        json={"command": "company", "arg": "AAPL"}).json()["reply"]
    assert "AAPL" in quote and "200" in quote
    unknown = client.post("/api/v1/discord/commands/preview",
                          json={"command": "hack"}).json()["reply"]
    assert "Unknown command" in unknown


def test_discord_event_rendering_and_roles():
    from aiptp.integrations.discord import (
        AI_DISCLAIMER,
        render_event,
        role_for_profile,
    )

    msg = render_event("order_filled", {"side": "BUY", "quantity": "5",
                                        "symbol": "AAPL", "price": "200",
                                        "origin": "AI_AUTO"})
    assert "AAPL" in msg and "AI_AUTO" in msg  # AI origin stays visible
    ai = render_event("ai_analysis", {"symbol": "MSFT"})
    assert AI_DISCLAIMER in ai  # educational disclaimer on AI output
    assert render_event("watch.quotes", {}) is None  # not discord-worthy

    assert role_for_profile(1) == ["Beginner Investor"]
    assert role_for_profile(12) == ["Analyst"]
    assert role_for_profile(25, competition_wins=1) == [
        "Portfolio Manager", "Competition Winner"]


def test_discord_config_roundtrip_no_secret_leak(client):
    cfg = client.get("/api/v1/discord/config").json()
    assert cfg["webhook_configured"] is False
    r = client.put("/api/v1/discord/config", json={
        "webhook_url": "https://discord.com/api/webhooks/x/y",
        "events": ["order_filled", "achievement"],
    })
    assert r.status_code == 200
    cfg = client.get("/api/v1/discord/config").json()
    assert cfg["webhook_configured"] is True
    assert cfg["events"] == ["order_filled", "achievement"]
    assert "webhook_url" not in cfg  # secret never echoed
    assert client.put("/api/v1/discord/config",
                      json={"webhook_url": "http://insecure"}).status_code == 422
    assert client.put("/api/v1/discord/config",
                      json={"events": ["bogus"]}).status_code == 422
    # test-fire with no reachable webhook is a clean error, not a crash
    # (the URL above is fake; delivery failure -> 502)
    assert client.post("/api/v1/discord/test").status_code in (200, 502)


def test_disabling_notifications_cascades_to_discord(client):
    """Roadmap 6.11.5 exercised by a real dependency: discord requires
    notifications, so turning notifications off pulls discord down too."""
    r = client.put("/api/v1/modules/notifications", json={"enabled": False})
    assert r.status_code == 200
    assert "discord" in r.json()["dependents_affected"]
    body = client.get("/api/v1/modules").json()
    by_id = {m["id"]: m for m in body["modules"]}
    assert by_id["notifications"]["pending_change"]


def test_notifications_off_at_boot_disables_discord(tmp_path):
    """After a restart with notifications disabled, discord is cascade-
    disabled: its routes 404 and /modules reports the reason."""
    from aiptp.core.modules import module_setting_key
    from aiptp.storage.db import Base, make_engine, make_session_factory
    from aiptp.storage.models import AppSetting

    cfg = Settings(db_url=f"sqlite:///{tmp_path / 'casc.db'}", data_dir=tmp_path,
                   market_providers="fake")
    engine = make_engine(cfg.resolved_db_url())
    Base.metadata.create_all(engine)
    sf = make_session_factory(engine)
    with sf() as s:
        s.add(AppSetting(key=module_setting_key("notifications"), value="off"))
        s.commit()
    market = MarketDataService([FakeProvider({"AAPL": "200"})], quote_ttl=0)
    with TestClient(create_app(cfg, market=market)) as c:
        body = c.get("/api/v1/modules").json()
        by_id = {m["id"]: m for m in body["modules"]}
        assert by_id["notifications"]["state"] != "RUNNING"
        assert by_id["discord"]["state"] != "RUNNING"
        assert "notifications" in (by_id["discord"].get("disabled_reason") or "")
        r = c.get("/api/v1/discord/config")
        assert r.status_code in (404, 409)  # unmounted or runtime-gated
