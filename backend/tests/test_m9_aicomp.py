"""M9: AI competitors — profiles, difficulty, transparency, adaptivity,
tournaments, post-game analysis, historical opponents."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from aiptp.aicomp.profiles import DIFFICULTIES, PROFILES, effective_traits
from aiptp.config import Settings
from aiptp.main import create_app
from aiptp.marketdata.base import Bar
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService

ALL_SYMBOLS = sorted({s for p in PROFILES.values() for s in p.universe})


def _trending_bars(price: float, daily_move: float, days: int = 130) -> list[Bar]:
    """Deterministic real-shaped bars ending near `price`."""
    now = int(datetime.now(timezone.utc).timestamp())
    bars = []
    p = price / ((1 + daily_move) ** days)
    for d in range(days):
        p *= 1 + daily_move
        ts = now - (days - d) * 86400
        bars.append(Bar(ts=ts, open=p, high=p * 1.01, low=p * 0.99,
                        close=p, volume=1000))
    return bars


@pytest.fixture
def ai_client(tmp_path):
    """Fake market where NVDA trends hard up, XOM drifts down, others flat —
    so momentum/growth/value methods produce distinct, assertable picks."""
    prices = {s: "100" for s in ALL_SYMBOLS}
    fake = FakeProvider(prices)
    for s in ALL_SYMBOLS:
        fake.history_bars[s] = _trending_bars(100, 0.0)
    fake.history_bars["NVDA"] = _trending_bars(100, 0.004)   # strong uptrend
    fake.history_bars["MSFT"] = _trending_bars(100, 0.002)   # mild uptrend
    fake.history_bars["XOM"] = _trending_bars(100, -0.003)   # downtrend: far below high
    cfg = Settings(db_url=f"sqlite:///{tmp_path / 'ai.db'}", data_dir=tmp_path,
                   market_providers="fake")
    market = MarketDataService([fake], quote_ttl=0, history_ttl=0)
    with TestClient(create_app(cfg, market=market)) as c:
        yield c


def _make_competition(c: TestClient) -> str:
    return c.post("/api/v1/competitions",
                  json={"name": "AI Arena", "starting_balance": "100000"}
                  ).json()["id"]


def test_profiles_catalog(ai_client):
    profiles = {p["id"]: p for p in ai_client.get("/api/v1/ai-players/profiles").json()}
    assert set(profiles) == {"conservative", "growth", "value", "dividend",
                             "technical", "quant", "market_timer", "beginner",
                             "index"}
    for p in profiles.values():
        assert set(p["traits"]) == {"risk_tolerance", "patience", "confidence",
                                    "conviction", "adaptability"}
        assert p["difficulties"] == list(DIFFICULTIES)


def test_difficulty_scales_personality():
    growth = PROFILES["growth"]
    beginner = effective_traits(growth, "beginner")
    expert = effective_traits(growth, "expert")
    assert beginner["patience"] < expert["patience"]
    assert expert["conviction"] <= 1.0


def test_ai_player_invests_with_full_transparency(ai_client):
    c = ai_client
    cid = _make_competition(c)
    r = c.post(f"/api/v1/competitions/{cid}/ai-players",
               json={"profile": "technical", "difficulty": "expert"})
    assert r.status_code == 201
    player = r.json()
    # the momentum method must pick the strongest trender
    symbols = {h["symbol"] for h in player["holdings"]}
    assert "NVDA" in symbols
    assert "XOM" not in symbols

    log = c.get(f"/api/v1/ai-players/{player['id']}/decisions").json()
    assert log["decisions"], "every action must be recorded"
    for d in log["decisions"]:
        assert d["reason"]
        assert d["confidence"] >= 0
        assert d["expected_outcome"]
        assert "selection" in d["data_used"] or d["action"] == "HOLD"
    buys = [d for d in log["decisions"] if d["action"] == "BUY"]
    assert all(d["executed_order_id"] for d in buys)

    # AI trades are permanently marked
    txns = c.get(f"/api/v1/portfolios/{player['portfolio_id']}/transactions").json()
    assert txns and all(t["origin"] == "AI_AUTO" for t in txns)

    # bad inputs
    assert c.post(f"/api/v1/competitions/{cid}/ai-players",
                  json={"profile": "nope"}).status_code == 422
    assert c.post(f"/api/v1/competitions/{cid}/ai-players",
                  json={"profile": "growth", "difficulty": "impossible"}
                  ).status_code == 422


def test_value_profile_buys_the_beaten_down(ai_client):
    c = ai_client
    cid = _make_competition(c)
    player = c.post(f"/api/v1/competitions/{cid}/ai-players",
                    json={"profile": "value", "difficulty": "expert"}).json()
    symbols = {h["symbol"] for h in player["holdings"]}
    assert "XOM" in symbols  # deepest below its 52-week high


def test_market_timer_goes_risk_on_in_uptrend(ai_client):
    c = ai_client
    cid = _make_competition(c)
    player = c.post(f"/api/v1/competitions/{cid}/ai-players",
                    json={"profile": "market_timer", "difficulty": "expert"}).json()
    # flat SPY: price == trend -> risk-ON holds SPY
    assert {h["symbol"] for h in player["holdings"]} == {"SPY"}
    log = c.get(f"/api/v1/ai-players/{player['id']}/decisions").json()
    assert any("risk-ON" in d["data_used"].get("selection", "")
               for d in log["decisions"] if d["data_used"])


def test_beginner_ai_explains_its_mistakes(ai_client):
    c = ai_client
    cid = _make_competition(c)
    player = c.post(f"/api/v1/competitions/{cid}/ai-players",
                    json={"profile": "beginner", "difficulty": "beginner"}).json()
    log = c.get(f"/api/v1/ai-players/{player['id']}/decisions").json()
    reasons = " ".join(d["reason"] for d in log["decisions"])
    assert "mistake" in reasons.lower()  # educational: it says so (9.2/9.3)


def test_adaptive_ai_borrows_from_the_leader(ai_client):
    c = ai_client
    cid = _make_competition(c)
    # human leader: join and put everything in NVDA, then rig NVDA up 20%
    pid = c.post(f"/api/v1/competitions/{cid}/join", json={}).json()["portfolio_id"]
    c.post(f"/api/v1/portfolios/{pid}/orders",
           json={"symbol": "NVDA", "side": "BUY", "type": "MARKET",
                 "notional": "90000"})
    player = c.post(f"/api/v1/competitions/{cid}/ai-players",
                    json={"profile": "dividend", "difficulty": "expert",
                          "adaptive": True}).json()
    fake = c.app.state.market.providers[0]
    fake.set_price("NVDA", "120")  # human portfolio now way ahead
    c.post(f"/api/v1/ai-players/{player['id']}/cycle")
    log = c.get(f"/api/v1/ai-players/{player['id']}/decisions").json()
    adapted = [d for d in log["decisions"]
               if d["data_used"].get("adaptive", {}).get("borrowed_idea")]
    assert adapted, "trailing adaptive AI should borrow the leader's top holding"
    assert adapted[0]["data_used"]["adaptive"]["borrowed_idea"] == "NVDA"


def test_tournaments(ai_client):
    c = ai_client
    templates = {t["id"] for t in c.get("/api/v1/tournaments").json()}
    assert templates == {"beat_the_market", "growth_vs_value", "human_vs_ai"}
    t = c.post("/api/v1/tournaments", json={"template": "human_vs_ai"}).json()
    assert t["ai_players"] == 8
    standings = c.get(f"/api/v1/competitions/{t['competition_id']}/standings"
                      ).json()["standings"]
    assert len(standings) == 9  # 8 AI + you
    assert sum(1 for r in standings if r["is_ai"]) == 8
    assert c.post("/api/v1/tournaments", json={"template": "nope"}
                  ).status_code == 422


def test_post_game_analysis(ai_client):
    c = ai_client
    t = c.post("/api/v1/tournaments", json={"template": "beat_the_market"}).json()
    # do nothing: 100% cash while the index AI is invested
    a = c.get(f"/api/v1/competitions/{t['competition_id']}/analysis").json()
    assert len(a["standings"]) == 2
    assert any("cash" in f.lower() for f in a["findings"])
    me = next(r for r in a["standings"] if r["is_you"])
    assert me["cash_pct"] == 100.0


def test_ai_portfolios_stay_off_the_dashboard(ai_client):
    c = ai_client
    cid = _make_competition(c)
    c.post(f"/api/v1/competitions/{cid}/ai-players", json={"profile": "index"})
    names = [p["name"] for p in c.get("/api/v1/portfolios").json()]
    assert not any("🤖" in n for n in names)


def test_ai_cycle_scheduler_function(ai_client):
    from aiptp.aicomp.engine import run_ai_cycle

    c = ai_client
    cid = _make_competition(c)
    c.post(f"/api/v1/competitions/{cid}/ai-players",
           json={"profile": "technical", "difficulty": "expert"})
    # impatient technical trader: last_cycle_at just set, so the very next
    # cycle within the patience window is skipped
    acted = run_ai_cycle(c.app.state.session_factory, c.app.state.market)
    assert acted == 0


def test_ai_competitors_depend_on_multiplayer(client):
    r = client.put("/api/v1/modules/multiplayer", json={"enabled": False})
    assert r.status_code == 200
    assert "ai_competitors" in r.json()["dependents_affected"]
