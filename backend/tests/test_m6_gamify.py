"""M6 gamification: XP/levels/titles, caps, opt-out, achievements,
challenges, report card, coach, game modes."""

from aiptp.gamify.levels import level_from_xp, title_for_level, xp_for_level


def evaluate(client):
    return client.post("/api/v1/gamify/evaluate").json()


def test_level_math_and_titles():
    assert xp_for_level(1) == 0
    assert xp_for_level(2) == 100
    assert level_from_xp(0) == 1
    assert level_from_xp(99) == 1
    assert level_from_xp(100) == 2
    assert level_from_xp(300) == 3
    assert title_for_level(1) == "Beginner Investor"
    assert title_for_level(7) == "Market Student"
    assert title_for_level(45) == "Legendary Investor"


def test_profile_actions_caps_and_levels(client):
    profile = client.get("/api/v1/gamify/profile").json()
    assert profile["progress"]["level"] == 1
    assert profile["gamification_enabled"] is True

    # research action awards XP
    assert client.post("/api/v1/gamify/events",
                       json={"kind": "company_viewed", "reason": "AAPL"}).json()["awarded"]
    profile = client.get("/api/v1/gamify/profile").json()
    assert profile["xp_by_category"]["research"] == 5
    assert profile["recent_xp"][0]["kind"] == "company_viewed"

    # daily cap: company_viewed caps at 5/day
    for i in range(6):
        client.post("/api/v1/gamify/events",
                    json={"kind": "company_viewed", "reason": f"SYM{i}"})
    profile = client.get("/api/v1/gamify/profile").json()
    assert profile["xp_by_category"]["research"] == 25  # capped

    # unknown kind rejected
    assert client.post("/api/v1/gamify/events",
                       json={"kind": "traded_a_lot"}).status_code == 422


def test_profile_update_and_opt_out(client):
    client.patch("/api/v1/gamify/profile",
                 json={"username": "Kaden", "avatar": "🚀"})
    profile = client.get("/api/v1/gamify/profile").json()
    assert profile["username"] == "Kaden" and profile["avatar"] == "🚀"

    # opt out: no more XP, evaluation no-ops
    client.patch("/api/v1/gamify/profile", json={"gamification_enabled": False})
    before = client.get("/api/v1/gamify/profile").json()["xp_by_category"]["research"]
    assert client.post("/api/v1/gamify/events",
                       json={"kind": "companies_compared"}).json()["awarded"] is False
    after = client.get("/api/v1/gamify/profile").json()["xp_by_category"]["research"]
    assert before == after
    client.patch("/api/v1/gamify/profile", json={"gamification_enabled": True})


def test_achievements_first_investment_and_strategy(client, portfolio_id):
    result = evaluate(client)
    profile = client.get("/api/v1/gamify/profile").json()
    earned = {a["id"] for a in profile["achievements"] if a["earned_at"]}
    assert "first_investment" not in earned

    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "5"},
    )
    client.post(
        "/api/v1/strategies",
        json={"name": "S", "universe": ["AAPL"],
              "entry_trigger": {"price": {"symbol": "$SYMBOL", "op": "<", "value": 1}}},
    )
    result = evaluate(client)
    assert result["achievements_granted"] >= 2
    profile = client.get("/api/v1/gamify/profile").json()
    earned = {a["id"] for a in profile["achievements"] if a["earned_at"]}
    assert {"first_investment", "first_strategy"} <= earned
    # idempotent
    assert evaluate(client)["achievements_granted"] == 0

    # game XP flowed to the portfolio (first_investment is portfolio-scoped)
    game = client.get(f"/api/v1/portfolios/{portfolio_id}/game").json()
    assert game["game_xp"] >= 50
    assert game["mode"] == "CLASSIC"
    assert game["game_level"] >= 1

    # achievement notification landed in the inbox
    inbox = client.get("/api/v1/notifications").json()["notifications"]
    assert any(n["type"] == "achievement" for n in inbox)


def test_challenges_assignment_and_completion(client, portfolio_id):
    challenges = client.get("/api/v1/gamify/challenges").json()
    assert len(challenges) >= 4  # 2 daily + 2 weekly + 2 monthly (current)
    types = {c["period_type"] for c in challenges}
    assert types == {"DAILY", "WEEKLY", "MONTHLY"}
    assert all(c["status"] == "ACTIVE" for c in challenges if c["current"])

    # completing the daily "review a company" via a research event
    client.post("/api/v1/gamify/events",
                json={"kind": "company_viewed", "reason": "MSFT"})
    client.post("/api/v1/gamify/events",
                json={"kind": "analytics_reviewed", "portfolio_id": portfolio_id})
    client.post("/api/v1/gamify/events", json={"kind": "coach_suggestion_read"})
    result = evaluate(client)
    challenges = client.get("/api/v1/gamify/challenges").json()
    done = [c for c in challenges if c["status"] == "COMPLETED"]
    assert len(done) >= 1
    profile = client.get("/api/v1/gamify/profile").json()
    assert profile["xp_by_category"]["challenge"] > 0


def test_report_card_and_coach(client, fake_provider, portfolio_id):
    fake_provider.set_price("SPY", "500")
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "notional": "9000"},
    )
    card = client.get(f"/api/v1/portfolios/{portfolio_id}/report-card").json()
    assert set(card["subjects"]) == {
        "diversification", "risk_management", "research", "returns",
        "patience", "strategy_discipline",
    }
    assert card["overall"] in ["F", "D", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]
    for subject in card["subjects"].values():
        assert subject["grade"] and subject["detail"]

    coach = client.get(f"/api/v1/portfolios/{portfolio_id}/coach").json()["observations"]
    # 90% in one stock -> concentration observation
    assert any(o["id"] == "concentration" for o in coach)
    assert all(o["disclaimer"] for o in coach)


def test_beginner_mode_portfolio(client):
    resp = client.post(
        "/api/v1/portfolios",
        json={"name": "Learning game", "starting_balance": "1000", "mode": "BEGINNER"},
    )
    assert resp.status_code == 201
    assert resp.json()["mode"] == "BEGINNER"
    game = client.get(f"/api/v1/portfolios/{resp.json()['id']}/game").json()
    assert game["mode"] == "BEGINNER"
