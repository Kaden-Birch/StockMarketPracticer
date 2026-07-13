"""M6.11: modular architecture — module manager, lifecycle, error
isolation, dependency cascades, experience presets, event bus, and the
AI/notification provider abstractions."""

import pytest
from fastapi.testclient import TestClient

from aiptp.config import Settings
from aiptp.core.events import EventBus
from aiptp.core.modules import (
    AppContext,
    Manifest,
    Module,
    ModuleManager,
    ModuleState,
)
from aiptp.main import create_app
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService


# ---- event bus ----

def test_internal_events_deliver_and_isolate_failures():
    bus = EventBus()
    seen = []
    bus.subscribe_internal("thing", lambda et, p, s: seen.append((et, p)), owner="a")
    bus.subscribe_internal("thing", lambda et, p, s: 1 / 0, owner="broken")  # must not raise
    tail = []
    bus.subscribe_internal("*", lambda et, p, s: tail.append(et), owner="wild")
    bus.publish("thing", {"x": 1})
    assert seen == [("thing", {"x": 1})]  # good handler ran
    assert tail == ["thing"]  # wildcard ran despite the broken sibling


# ---- module manager lifecycle & isolation ----

def _ctx(tmp_path):
    cfg = Settings(db_url=f"sqlite:///{tmp_path/'m.db'}", data_dir=tmp_path,
                   market_providers="fake")
    from aiptp.storage.db import Base, make_engine, make_session_factory

    engine = make_engine(cfg.resolved_db_url())
    Base.metadata.create_all(engine)
    sf = make_session_factory(engine)
    return AppContext(app=None, session_factory=sf, market=None, bus=EventBus(),
                      settings=cfg, model_manager=None, scheduler_jobs=[])


def _mod(mid, deps=None, boom=False):
    class M(Module):
        manifest = Manifest(id=mid, name=mid, version="1.0.0", dependencies=deps or [])

        def start(self, ctx):
            if boom:
                raise RuntimeError("kaboom")

    return M()


def test_failed_module_is_isolated(tmp_path):
    mgr = ModuleManager(_ctx(tmp_path))
    mgr.register_all([_mod("ok"), _mod("bad", boom=True)])
    assert mgr.is_running("ok")
    assert mgr.states["bad"] == ModuleState.FAILED
    assert "kaboom" in mgr.errors["bad"]


def test_dependency_cascade_disables_dependents(tmp_path):
    ctx = _ctx(tmp_path)
    # disable "base" via settings, then a dependent must auto-disable
    from aiptp.core.modules import module_setting_key
    from aiptp.storage.models import AppSetting

    with ctx.session_factory() as s:
        s.add(AppSetting(key=module_setting_key("base"), value="off"))
        s.commit()
    mgr = ModuleManager(ctx)
    mgr.register_all([_mod("base"), _mod("dependent", deps=["base"])])
    assert mgr.states["base"] == ModuleState.DISABLED
    assert mgr.states["dependent"] == ModuleState.DISABLED
    assert "base" in mgr.disabled_reasons["dependent"]


def test_dependency_cycle_detected(tmp_path):
    mgr = ModuleManager(_ctx(tmp_path))
    with pytest.raises(ValueError):
        mgr.register_all([_mod("a", deps=["b"]), _mod("b", deps=["a"])])


# ---- app-level: modules registered, routers gated ----

@pytest.fixture
def client(tmp_path):
    cfg = Settings(db_url=f"sqlite:///{tmp_path/'app.db'}", data_dir=tmp_path,
                   market_providers="fake")
    market = MarketDataService([FakeProvider({"AAPL": "200", "SPY": "500"})],
                               quote_ttl=0, history_ttl=0)
    app = create_app(cfg, market=market)
    with TestClient(app) as c:
        yield c


def test_modules_endpoint_lists_migrated_modules(client):
    body = client.get("/api/v1/modules").json()
    ids = {m["id"] for m in body["modules"]}
    assert {"notifications", "automation", "gamification", "ai_mentor", "reporting"} <= ids
    for m in body["modules"]:
        assert m["state"] == "RUNNING"
        assert "ui" in m and "permissions" in m
    assert {p["id"] for p in body["presets"]} == {"LEARNING", "ACADEMY", "PROFESSIONAL"}


def test_ui_contributions_present(client):
    body = client.get("/api/v1/modules").json()
    gam = next(m for m in body["modules"] if m["id"] == "gamification")
    kinds = {c["kind"] for c in gam["ui"]}
    assert "nav_item" in kinds  # contributes the Profile nav item


def test_disabling_module_persists_and_reports_pending(client):
    resp = client.put("/api/v1/modules/gamification", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["applies"] == "after restart"
    body = client.get("/api/v1/modules").json()
    gam = next(m for m in body["modules"] if m["id"] == "gamification")
    assert gam["pending_change"] and "off" in gam["pending_change"]
    assert client.put("/api/v1/modules/nope", json={"enabled": False}).status_code == 404


def test_disabled_module_gates_routes_on_next_boot(tmp_path):
    from aiptp.core.modules import module_setting_key
    from aiptp.storage.db import make_engine, make_session_factory, Base
    from aiptp.storage.models import AppSetting

    cfg = Settings(db_url=f"sqlite:///{tmp_path/'g.db'}", data_dir=tmp_path,
                   market_providers="fake")
    engine = make_engine(cfg.resolved_db_url())
    Base.metadata.create_all(engine)
    sf = make_session_factory(engine)
    with sf() as s:
        s.add(AppSetting(key=module_setting_key("gamification"), value="off"))
        s.commit()
    market = MarketDataService([FakeProvider({"AAPL": "200"})], quote_ttl=0)
    with TestClient(create_app(cfg, market=market)) as c:
        # disabled-at-boot module: its routes aren't mounted -> real 404 JSON
        # (not the SPA HTML fallback, and not a core crash)
        r = c.get("/api/v1/gamify/profile")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")
        # core trading still works — module disable never breaks core
        assert c.post("/api/v1/portfolios",
                      json={"name": "x", "starting_balance": "1000"}).status_code == 201
        mods = {m["id"]: m for m in c.get("/api/v1/modules").json()["modules"]}
        assert mods["gamification"]["state"] == "DISABLED"


# ---- experience presets gate portfolio-scoped modules ----

def test_learning_preset_disables_gamification_per_portfolio(client):
    pid = client.post("/api/v1/portfolios",
                      json={"name": "Learn", "starting_balance": "10000",
                            "preset": "LEARNING"}).json()["id"]
    # report card is gamification-scoped -> blocked by the Learning preset
    assert client.get(f"/api/v1/portfolios/{pid}/report-card").status_code == 409
    # but the coach ships with AI Mentor, so it stays available
    client.post(f"/api/v1/portfolios/{pid}/orders",
                json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "5"})
    assert client.get(f"/api/v1/portfolios/{pid}/coach").status_code == 200

    # an Academy portfolio keeps gamification
    aid = client.post("/api/v1/portfolios",
                      json={"name": "Acad", "starting_balance": "10000",
                            "preset": "ACADEMY"}).json()["id"]
    assert client.get(f"/api/v1/portfolios/{aid}/report-card").status_code == 200


def test_learning_preset_earns_no_xp(client):
    pid = client.post("/api/v1/portfolios",
                      json={"name": "L", "starting_balance": "5000",
                            "preset": "LEARNING"}).json()["id"]
    client.post("/api/v1/gamify/events",
                json={"kind": "analytics_reviewed", "portfolio_id": pid})
    # portfolio-scoped event under Learning preset -> no XP
    assert client.get("/api/v1/gamify/profile").json()["xp_by_category"]["portfolio"] == 0


# ---- provider abstractions ----

def test_openai_compatible_runtime_shape():
    from aiptp.ai.runtime import OpenAICompatibleRuntime

    rt = OpenAICompatibleRuntime("http://localhost:11434", "")
    rt.load("llama3", None)
    assert rt.model_id == "llama3"
    assert rt.base_url == "http://localhost:11434"


def test_notification_channels_config_roundtrip(client):
    ch = client.get("/api/v1/notifications/channels").json()
    assert ch["webhook"]["configured"] is False
    assert "discord" in ch["available"]
    client.put("/api/v1/notifications/channels/webhook",
               json={"url": "https://example.com/hook", "format": "discord"})
    ch = client.get("/api/v1/notifications/channels").json()
    assert ch["webhook"]["configured"] is True
    assert ch["webhook"]["format"] == "discord"
