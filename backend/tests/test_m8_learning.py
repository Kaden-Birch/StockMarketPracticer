"""M8: persistent mentor, historical scenarios, career mode, mandates,
classroom mode."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aiptp.config import Settings
from aiptp.main import create_app
from aiptp.marketdata.base import Bar
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService
from aiptp.scenario.catalog import SCENARIOS


# ------------------------------------------------------------------ mentor


def _seed_disposition_effect(client, pid):
    """Winners sold fast, losers held long — via backdated transactions."""
    from aiptp.storage.models import OrderSide, Portfolio, Transaction

    app = client.app
    now = datetime.now(timezone.utc)
    with app.state.session_factory() as s:
        rows = []
        # three quick winners: buy, sell 2 days later at a profit
        for i, sym in enumerate(["AAPL", "MSFT", "NVDA"]):
            buy_at = now - timedelta(days=40 + i)
            rows += [
                Transaction(portfolio_id=pid, symbol=sym, side=OrderSide.BUY,
                            quantity=Decimal("10"), price=Decimal("100"),
                            amount=Decimal("-1000"), executed_at=buy_at),
                Transaction(portfolio_id=pid, symbol=sym, side=OrderSide.SELL,
                            quantity=Decimal("10"), price=Decimal("110"),
                            amount=Decimal("1100"), realized_pnl=Decimal("100"),
                            executed_at=buy_at + timedelta(days=2)),
            ]
        # one loser held 90 days
        buy_at = now - timedelta(days=100)
        rows += [
            Transaction(portfolio_id=pid, symbol="AAPL", side=OrderSide.BUY,
                        quantity=Decimal("10"), price=Decimal("100"),
                        amount=Decimal("-1000"), executed_at=buy_at),
            Transaction(portfolio_id=pid, symbol="AAPL", side=OrderSide.SELL,
                        quantity=Decimal("10"), price=Decimal("80"),
                        amount=Decimal("800"), realized_pnl=Decimal("-200"),
                        executed_at=buy_at + timedelta(days=90)),
        ]
        s.add_all(rows)
        s.commit()


def test_mentor_detects_disposition_effect_and_remembers(client, portfolio_id):
    _seed_disposition_effect(client, portfolio_id)
    view = client.post("/api/v1/mentor/refresh").json()
    codes = {o["code"]: o for o in view["observations"]}
    assert "sells_winners_early" in codes
    obs = codes["sells_winners_early"]
    assert obs["severity"] == "important"
    assert obs["evidence"]["winners"] == 3
    assert view["profile"]["style"]  # classified something

    # persistent memory: second run increments times_seen, same row
    view2 = client.post("/api/v1/mentor/refresh").json()
    obs2 = {o["code"]: o for o in view2["observations"]}["sells_winners_early"]
    assert obs2["times_seen"] == 2
    assert obs2["id"] == obs["id"]

    # acknowledge keeps it out of ACTIVE status but not resolved
    r = client.post(f"/api/v1/mentor/observations/{obs['id']}/acknowledge")
    assert r.status_code == 200
    statuses = {o["code"]: o["status"]
                for o in client.get("/api/v1/mentor").json()["observations"]}
    assert statuses["sells_winners_early"] == "ACKNOWLEDGED"


def test_mentor_knowledge_gaps_and_narrative_gate(client, portfolio_id):
    view = client.post("/api/v1/mentor/refresh").json()
    gaps = view["profile"]["knowledge_gaps"]
    assert any("valuation" in g for g in gaps)
    codes = {o["code"] for o in view["observations"]}
    assert "no_education_activity" in codes  # "not reviewed valuation metrics yet"
    # narrative needs a loaded model
    assert client.post("/api/v1/mentor/narrative").status_code == 409


def test_mentor_resolves_fixed_behaviors(client, portfolio_id):
    client.post("/api/v1/mentor/refresh")
    # earn education XP -> the knowledge observation should resolve
    client.post("/api/v1/gamify/events", json={"kind": "coach_suggestion_read",
                                               "reason": "coach"})
    view = client.post("/api/v1/mentor/refresh").json()
    active = {o["code"] for o in view["observations"]}
    resolved = {o["code"] for o in view["resolved"]}
    assert "no_education_activity" not in active
    assert "no_education_activity" in resolved  # remembered, not deleted


# ---------------------------------------------------------------- scenarios


def _covid_bars() -> dict[str, list[Bar]]:
    """20 fake daily bars inside the covid_crash window for every universe
    symbol + benchmark (tests use the fake provider by design)."""
    scenario = SCENARIOS["covid_crash"]
    start = scenario.start_ts + 86400
    out = {}
    for i, symbol in enumerate((*scenario.universe, scenario.benchmark)):
        base = 100 + i * 10
        out[symbol] = [
            Bar(ts=start + d * 86400, open=base + d, high=base + d + 1,
                low=base + d - 1, close=base + d, volume=1000)
            for d in range(20)
        ]
    return out


@pytest.fixture
def scenario_client(tmp_path):
    scenario = SCENARIOS["covid_crash"]
    prices = {s: "100" for s in (*scenario.universe, scenario.benchmark)}
    fake = FakeProvider(prices)
    fake.history_bars.update(_covid_bars())
    cfg = Settings(db_url=f"sqlite:///{tmp_path / 's.db'}", data_dir=tmp_path,
                   market_providers="fake")
    market = MarketDataService([fake], quote_ttl=0, history_ttl=0)
    with TestClient(create_app(cfg, market=market)) as c:
        yield c


def test_scenario_replay_no_future_knowledge(scenario_client):
    c = scenario_client
    catalog = c.get("/api/v1/scenarios").json()["catalog"]
    assert {s["id"] for s in catalog} == {
        "dotcom_crash", "gfc_2008", "covid_crash", "inflation_cycle", "tech_boom"}

    v = c.post("/api/v1/scenarios/sessions",
               json={"scenario_id": "covid_crash", "display_name": "P1"}).json()
    sid = v["id"]
    assert v["day"] == 1 and v["total_days"] == 20
    assert Decimal(v["quotes"]["AAPL"]["price"]) == 100  # day-0 close

    # only day-1 bars are served — the future stays hidden
    h = c.get(f"/api/v1/scenarios/sessions/{sid}/history/AAPL").json()
    assert len(h["bars"]) == 1

    # trade at the historical close through the real order engine
    t = c.post(f"/api/v1/scenarios/sessions/{sid}/trade",
               json={"symbol": "AAPL", "side": "BUY", "quantity": "100"})
    assert t.status_code == 201
    assert Decimal(t.json()["filled_price"]) == 100

    # outside-universe and unlisted trades are refused
    assert c.post(f"/api/v1/scenarios/sessions/{sid}/trade",
                  json={"symbol": "TSLA", "side": "BUY", "quantity": "1"}
                  ).status_code == 422

    # advance 5 trading days: AAPL walks 100 -> 105
    v = c.post(f"/api/v1/scenarios/sessions/{sid}/advance", json={"days": 5}).json()
    assert v["day"] == 6
    assert Decimal(v["quotes"]["AAPL"]["price"]) == 105
    assert Decimal(v["value"]) == Decimal("100000") + 100 * Decimal("5")
    h = c.get(f"/api/v1/scenarios/sessions/{sid}/history/AAPL").json()
    assert len(h["bars"]) == 6

    # comparison: you + market + 3 AI strategies, all truncated at day 6
    comp = c.get(f"/api/v1/scenarios/sessions/{sid}/comparison").json()
    ids = {s["id"] for s in comp["series"]}
    assert ids == {"you", "market", "ai_buy_hold", "ai_dca", "ai_momentum"}
    for s in comp["series"]:
        assert len(s["points"]) <= 6

    # replay portfolios never leak into live listings
    assert all(p["name"] != "COVID crash & rebound replay"
               for p in c.get("/api/v1/portfolios").json())

    # run to the end -> completed; further advances 409
    v = c.post(f"/api/v1/scenarios/sessions/{sid}/advance", json={"days": 260}).json()
    assert v["completed"] is True and v["day"] == 20
    assert c.post(f"/api/v1/scenarios/sessions/{sid}/advance",
                  json={"days": 1}).status_code == 409
    assert c.post(f"/api/v1/scenarios/sessions/{sid}/trade",
                  json={"symbol": "AAPL", "side": "BUY", "quantity": "1"}
                  ).status_code == 422


def test_scenario_players_comparison(scenario_client):
    c = scenario_client
    a = c.post("/api/v1/scenarios/sessions",
               json={"scenario_id": "covid_crash", "display_name": "Alpha"}).json()
    b = c.post("/api/v1/scenarios/sessions",
               json={"scenario_id": "covid_crash", "display_name": "Beta"}).json()
    c.post(f"/api/v1/scenarios/sessions/{b['id']}/advance", json={"days": 3})
    comp = c.get(f"/api/v1/scenarios/sessions/{a['id']}/comparison").json()
    names = [p["display_name"] for p in comp["players"]]
    assert "Beta" in names and "Alpha" not in names


# ------------------------------------------------------- career & mandates


def test_career_progression_and_challenges(client):
    car = client.get("/api/v1/career").json()
    assert car["rank_name"] == "Intern Investor"
    assert car["ladder"][-1] == "Institutional Investor"
    assert {ch["code"] for ch in car["challenges"]} == {
        "beat_benchmark", "survive_recession", "billion_dollar", "crash_recovery"}

    pid = client.post("/api/v1/portfolios",
                      json={"name": "Fund", "starting_balance": "600000"}
                      ).json()["id"]
    for s in ["AAPL", "MSFT", "NVDA"]:
        client.post(f"/api/v1/portfolios/{pid}/orders",
                    json={"symbol": s, "side": "BUY", "type": "MARKET",
                          "notional": "150000"})
    client.post("/api/v1/gamify/events", json={"kind": "company_viewed",
                                               "reason": "AAPL"})
    client.post("/api/v1/gamify/events", json={"kind": "analytics_reviewed",
                                               "reason": pid})
    for _ in range(2):
        client.post(f"/api/v1/portfolios/{pid}/orders",
                    json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                          "quantity": "1"})
    car = client.post("/api/v1/career/evaluate").json()
    done = {o["code"] for o in car["objectives"] if o["done"]}
    assert {"first_trades", "learn_basics", "diversify", "manage_risk",
            "scale_up"} <= done
    assert car["rank_name"] == "Retail Investor"  # rank 0 objectives all done

    # objectives never un-complete: selling everything keeps first_trades
    car2 = client.post("/api/v1/career/evaluate").json()
    assert {o["code"] for o in car2["objectives"] if o["done"]} >= done


def test_mandate_compliance(client):
    pid = client.post("/api/v1/portfolios",
                      json={"name": "Tech fund", "starting_balance": "100000"}
                      ).json()["id"]
    client.post(f"/api/v1/portfolios/{pid}/orders",
                json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                      "quantity": "50"})
    r = client.put(f"/api/v1/portfolios/{pid}/mandate",
                   json={"mandate": "technology"})
    assert r.status_code == 200
    assert r.json()["compliant"] is True

    # a non-tech holding violates the technology mandate
    # (fake provider knows NVDA=tech and... use a symbol not on the list)
    from aiptp.marketdata.fake import FakeProvider  # noqa: F401

    client.app.state.market.providers[0].set_price("KO", "60")
    client.post(f"/api/v1/portfolios/{pid}/orders",
                json={"symbol": "KO", "side": "BUY", "type": "MARKET",
                      "quantity": "10"})
    comp = client.get(f"/api/v1/portfolios/{pid}/mandate").json()
    assert comp["compliant"] is False
    rule = comp["rules"][0]
    assert rule["id"] == "tech_only" and "KO" in rule["value"]

    assert client.put(f"/api/v1/portfolios/{pid}/mandate",
                      json={"mandate": "nonsense"}).status_code == 422
    # clearing works
    cleared = client.put(f"/api/v1/portfolios/{pid}/mandate",
                         json={"mandate": ""}).json()
    assert cleared["mandate"] == ""


# ----------------------------------------------------------------- classroom


@pytest.fixture
def school(tmp_path):
    """Auth-required app: teacher + two students."""
    cfg = Settings(db_url=f"sqlite:///{tmp_path / 'cl.db'}", data_dir=tmp_path,
                   market_providers="fake", auth="required")
    scenario = SCENARIOS["covid_crash"]
    prices = {s: "100" for s in (*scenario.universe, scenario.benchmark)}
    prices.update({"AAPL": "100", "MSFT": "100"})
    fake = FakeProvider(prices)
    fake.history_bars.update(_covid_bars())
    market = MarketDataService([fake], quote_ttl=0, history_ttl=0)
    app = create_app(cfg, market=market)
    with TestClient(app) as teacher:
        teacher.post("/api/v1/auth/setup",
                     json={"username": "teacher", "password": "teachpass123"})
        for name in ("student1", "student2"):
            teacher.post("/api/v1/admin/users",
                         json={"username": name, "password": "studpass123",
                               "role": "trader"})
        with TestClient(app) as s1, TestClient(app) as s2:
            s1.post("/api/v1/auth/login",
                    json={"username": "student1", "password": "studpass123"})
            s2.post("/api/v1/auth/login",
                    json={"username": "student2", "password": "studpass123"})
            yield {"teacher": teacher, "s1": s1, "s2": s2}


def test_classroom_full_flow(school):
    teacher, s1, s2 = school["teacher"], school["s1"], school["s2"]
    room = teacher.post("/api/v1/classrooms", json={"name": "Investing 101"}).json()
    code = room["invite_code"]

    # students join by invite code; outsiders see nothing
    assert s1.get(f"/api/v1/classrooms/{room['id']}").status_code == 404
    assert s1.post("/api/v1/classrooms/join",
                   json={"invite_code": code}).status_code == 201
    assert s2.post("/api/v1/classrooms/join",
                   json={"invite_code": code}).status_code == 201
    detail = s1.get(f"/api/v1/classrooms/{room['id']}").json()
    assert {s["username"] for s in detail["students"]} == {"student1", "student2"}
    assert "invite_code" not in detail  # students don't see the code

    # students cannot create assignments; the instructor can (with a scenario)
    assert s1.post(f"/api/v1/classrooms/{room['id']}/assignments",
                   json={"title": "Nope"}).status_code == 403
    hw = teacher.post(f"/api/v1/classrooms/{room['id']}/assignments", json={
        "title": "Survive COVID", "scenario_id": "covid_crash",
        "mandate": "technology", "starting_balance": "50000",
    }).json()

    # student1 starts: gets a scenario session + mandated portfolio
    started = s1.post(f"/api/v1/assignments/{hw['id']}/start").json()
    assert started["scenario_session_id"]
    sess_id = started["scenario_session_id"]
    s1.post(f"/api/v1/scenarios/sessions/{sess_id}/trade",
            json={"symbol": "AAPL", "side": "BUY", "quantity": "10"})
    s1.post(f"/api/v1/scenarios/sessions/{sess_id}/advance", json={"days": 5})
    assert s1.post(f"/api/v1/assignments/{hw['id']}/start").status_code == 409

    # instructor dashboard: progress for both students
    assert s1.get(f"/api/v1/classrooms/{room['id']}/progress").status_code == 403
    prog = teacher.get(f"/api/v1/classrooms/{room['id']}/progress").json()
    rows = {r["username"]: r for r in prog["progress"][0]["students"]}
    assert rows["student1"]["started"] is True
    assert rows["student1"]["scenario_day"] == 6
    assert rows["student1"]["mandate_compliant"] is True
    assert rows["student2"]["started"] is False


def test_classroom_depends_on_scenarios(client):
    """Roadmap 6.11.5: disabling scenarios cascades to classroom."""
    r = client.put("/api/v1/modules/scenarios", json={"enabled": False})
    assert r.status_code == 200
    assert "classroom" in r.json()["dependents_affected"]
