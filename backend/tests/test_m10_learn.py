"""M10: knowledge base, quizzes, paths, tracking, contextual suggestions,
simulators, glossary backing."""

from aiptp.knowledge.content import CATEGORIES, CONCEPTS, PATHS


def test_dictionary_content_integrity():
    assert len(CONCEPTS) >= 30
    for c in CONCEPTS.values():
        # 10.2: all three explanation levels, always
        assert c.beginner and c.intermediate and c.advanced, c.id
        assert c.category in CATEGORIES, c.id
        for r in c.related:
            assert r in CONCEPTS, f"{c.id} references unknown concept {r}"
        for q in c.quiz:
            assert 0 <= q.answer < len(q.options), c.id
    # 10.6: every category is populated
    populated = {c.category for c in CONCEPTS.values()}
    assert populated == set(CATEGORIES)
    # 10.12: paths reference real concepts
    for p in PATHS.values():
        for cid in p.concepts:
            assert cid in CONCEPTS, f"path {p.id} -> unknown {cid}"
    assert set(PATHS) == {"beginner_investor", "intermediate_investor",
                          "advanced_investor"}


def test_search_and_categories(client):
    r = client.get("/api/v1/learn/concepts?q=diversif").json()
    assert any(c["id"] == "diversification" for c in r["concepts"])
    r = client.get("/api/v1/learn/concepts?category=technical").json()
    assert {c["id"] for c in r["concepts"]} >= {"rsi", "macd", "moving_average"}
    assert client.get("/api/v1/learn/concepts?category=bogus").status_code == 422


def test_concept_view_tracks_and_awards_xp(client):
    view = client.get("/api/v1/learn/concepts/pe_ratio").json()
    assert view["beginner"] and view["intermediate"] and view["advanced"]
    assert view["viewed_count"] == 1
    prof = client.get("/api/v1/gamify/profile").json()
    assert prof["xp_by_category"]["education"] >= 5  # concept_viewed XP
    # second view increments but doesn't double-award first-view XP
    view = client.get("/api/v1/learn/concepts/pe_ratio").json()
    assert view["viewed_count"] == 2
    progress = client.get("/api/v1/learn/progress").json()
    assert progress["concepts_viewed"] == 1
    assert progress["categories"]["metrics"]["viewed"] == 1


def test_quiz_scoring_and_pass_tracking(client):
    quiz = client.get("/api/v1/learn/concepts/compound_growth").json()["quiz"]
    assert len(quiz) == 2 and "options" in quiz[0]
    # wrong answers -> fail with explanations
    r = client.post("/api/v1/learn/concepts/compound_growth/quiz",
                    json={"answers": [0, 0]}).json()
    assert r["score"] == 0 and not r["passed"]
    assert all(x["why"] for x in r["results"])
    # correct -> pass
    r = client.post("/api/v1/learn/concepts/compound_growth/quiz",
                    json={"answers": [1, 2]}).json()
    assert r["score"] == 100 and r["passed"]
    progress = client.get("/api/v1/learn/progress").json()
    assert progress["quizzes_passed"] == 1
    # wrong count rejected; conceptless quiz 404
    assert client.post("/api/v1/learn/concepts/compound_growth/quiz",
                       json={"answers": [1]}).status_code == 422
    assert client.post("/api/v1/learn/concepts/bond/quiz",
                       json={"answers": [0]}).status_code == 404


def test_learning_path_completion(client):
    path = next(p for p in client.get("/api/v1/learn/paths").json()
                if p["id"] == "beginner_investor")
    assert path["done"] == 0
    for step in path["steps"]:
        client.get(f"/api/v1/learn/concepts/{step['concept_id']}")
        if step["has_quiz"]:
            concept = CONCEPTS[step["concept_id"]]
            answers = [q.answer for q in concept.quiz]
            client.post(f"/api/v1/learn/concepts/{step['concept_id']}/quiz",
                        json={"answers": answers})
    path = next(p for p in client.get("/api/v1/learn/paths").json()
                if p["id"] == "beginner_investor")
    assert path["completed"] is True
    progress = client.get("/api/v1/learn/progress").json()
    assert "beginner_investor" in progress["paths_completed"]
    earned = {a["id"]: a["earned"] for a in progress["achievements"]}
    assert earned["first_concept"] and earned["fundamentals"]
    # 10.8 in the real achievements engine too (profile carries the catalog)
    client.post("/api/v1/gamify/evaluate")
    prof = client.get("/api/v1/gamify/profile").json()
    granted = {a["id"] for a in prof["achievements"] if a.get("earned_at")}
    assert {"first_concept", "fundamentals"} <= granted


def test_contextual_suggestions_grounded(client, portfolio_id):
    # concentrated single-position portfolio -> concentration_risk suggestion
    client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                      "notional": "9000"})
    sugg = client.get("/api/v1/learn/suggestions").json()
    ids = {s["concept_id"] for s in sugg}
    assert "concentration_risk" in ids
    hit = next(s for s in sugg if s["concept_id"] == "concentration_risk")
    assert "AAPL" in hit["why"]  # evidence, not generic advice


def test_simulators(client):
    r = client.post("/api/v1/learn/simulate/compound_growth",
                    json={"params": {"principal": 1000, "monthly": 100,
                                     "annual_rate_pct": 7, "years": 10}}).json()
    assert r["points"][-1]["value"] > r["points"][-1]["contributed"]
    assert "assumption" in r

    r = client.post("/api/v1/learn/simulate/diversification",
                    json={"params": {"single_volatility_pct": 40,
                                     "correlation": 0.3}}).json()
    vols = [p["portfolio_volatility_pct"] for p in r["points"]]
    assert vols[0] == 40.0
    assert vols[-1] < vols[0]
    assert vols[-1] >= r["systematic_floor_pct"]  # market risk never leaves

    r = client.post("/api/v1/learn/simulate/risk_allocation",
                    json={"params": {"stocks_pct": 100, "bonds_pct": 0,
                                     "cash_pct": 0}}).json()
    last = r["points"][-1]
    assert last["pessimistic"] < last["expected"] < last["optimistic"]
    assert client.post("/api/v1/learn/simulate/unknown", json={}).status_code == 404


def test_crash_simulator_uses_real_scenario_path(tmp_path):
    """The crash sim replays a real benchmark window (fake bars in tests)."""
    from fastapi.testclient import TestClient

    from aiptp.config import Settings
    from aiptp.main import create_app
    from aiptp.marketdata.base import Bar
    from aiptp.marketdata.fake import FakeProvider
    from aiptp.marketdata.service import MarketDataService
    from aiptp.scenario.catalog import SCENARIOS

    scenario = SCENARIOS["gfc_2008"]
    fake = FakeProvider({"SPY": "100"})
    # a crash path: 100 -> 60 -> 110 inside the real window
    start = scenario.start_ts + 86400
    closes = [100, 90, 75, 60, 70, 85, 100, 110]
    fake.history_bars["SPY"] = [
        Bar(ts=start + i * 86400, open=c, high=c, low=c, close=c, volume=0)
        for i, c in enumerate(closes)
    ]
    cfg = Settings(db_url=f"sqlite:///{tmp_path / 'c.db'}", data_dir=tmp_path,
                   market_providers="fake")
    market = MarketDataService([fake], quote_ttl=0, history_ttl=0)
    with TestClient(create_app(cfg, market=market)) as c:
        r = c.post("/api/v1/learn/simulate/market_crash",
                   json={"params": {"scenario_id": "gfc_2008",
                                    "starting_value": 10000}}).json()
        assert r["source"] == "real historical closes"
        assert r["max_drawdown_pct"] == -40.0  # 100 -> 60
        assert r["worst_value"] == 6000.0
        assert r["end_value"] == 11000.0
        assert r["recovered"] is True


def test_ask_ai_gated_without_model(client):
    assert client.post("/api/v1/learn/concepts/beta/ask",
                       json={"mode": "simple"}).status_code == 409
    # compare requires other_concept even before the model gate? model gate
    # fires first — that's fine, the 409 message points at the levels above.


def test_mentor_gap_feeds_suggestions(client, portfolio_id):
    """10.9: mentor knowledge gaps surface as learning suggestions."""
    client.post("/api/v1/mentor/refresh")  # no education XP -> valuation gap
    sugg = client.get("/api/v1/learn/suggestions").json()
    assert any(s["concept_id"] == "pe_ratio" for s in sugg)
