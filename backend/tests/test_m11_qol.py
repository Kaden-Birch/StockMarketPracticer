"""M11 quality-of-life: company profile/news/AI-summary endpoints, fire-once
rules, Games grouping, net-worth history (with inflation assumption and
created-at cutoff), FULL chart preset, and Future mode."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiptp.marketdata.base import Bar
from aiptp.storage.models import Portfolio


def run_cycle(client):
    from aiptp.watcher import run_watch_cycle

    app = client.app
    run_watch_cycle(app.state.session_factory, app.state.market, app.state.bus)


def set_daily_bars(fake_provider, symbol, days=300, start=100.0, drift=0.1):
    """Enough varied real-looking daily history for future-mode calibration."""
    now = int(datetime.now(timezone.utc).timestamp())
    bars = []
    price = start
    for i in range(days):
        price += drift if i % 3 else -drift / 2
        bars.append(Bar(ts=now - 86400 * (days - i), open=price, high=price,
                        low=price, close=price, volume=1000))
    fake_provider.history_bars[symbol.upper()] = bars


# ---- company profile / news / AI summary (note 4) ----

def test_company_profile_and_news(client, fake_provider):
    fake_provider.news["AAPL"] = [
        {"title": "Apple ships thing", "publisher": "Testwire",
         "link": "https://example.com/a", "published_at": 1700000000},
    ]
    profile = client.get("/api/v1/marketdata/profile/aapl")
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["symbol"] == "AAPL"
    assert body["sector"] and body["summary"]

    news = client.get("/api/v1/marketdata/news/AAPL")
    assert news.status_code == 200
    assert news.json()[0]["title"] == "Apple ships thing"

    assert client.get("/api/v1/marketdata/profile/NOPE").status_code == 404


def test_ai_summary_requires_model(client):
    resp = client.post("/api/v1/marketdata/summary/AAPL")
    assert resp.status_code == 409
    assert "model" in resp.json()["detail"].lower()


# ---- FULL chart preset (note 6) ----

def test_full_history_preset(client):
    resp = client.get("/api/v1/marketdata/history/AAPL", params={"range": "FULL"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["range"] == "FULL"
    assert len(body["bars"]) > 0


# ---- fire-once automation rules (note 8) ----

def test_fire_once_rule_disables_itself(client, fake_provider, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/rules",
        json={
            "name": "One shot",
            "trigger": {"price": {"symbol": "AAPL", "op": "<", "value": 190}},
            "action_type": "BUY",
            "action_params": {"symbol": "AAPL", "notional": "1000"},
            "cooldown_seconds": 0,
            "fire_once": True,
        },
    )
    assert resp.status_code == 201, resp.text
    rule = resp.json()
    assert rule["fire_once"] is True

    fake_provider.set_price("AAPL", "185")
    run_cycle(client)
    rules = client.get(f"/api/v1/portfolios/{portfolio_id}/rules").json()
    assert rules[0]["fire_count"] == 1
    assert rules[0]["enabled"] is False  # paused itself after the first fire

    # price swings out and back below the trigger: a normal rule would
    # edge-trigger again, a one-shot stays quiet
    fake_provider.set_price("AAPL", "200")
    run_cycle(client)
    fake_provider.set_price("AAPL", "180")
    run_cycle(client)
    rules = client.get(f"/api/v1/portfolios/{portfolio_id}/rules").json()
    assert rules[0]["fire_count"] == 1


# ---- Games: isolated portfolio groups (note 10) ----

def test_games_group_and_filter_portfolios(client):
    game = client.post("/api/v1/games", json={"name": "World A"})
    assert game.status_code == 201, game.text
    gid = game.json()["id"]

    in_game = client.post("/api/v1/portfolios",
                          json={"name": "In game", "starting_balance": "5000",
                                "game_id": gid}).json()
    loose = client.post("/api/v1/portfolios",
                        json={"name": "Loose", "starting_balance": "5000"}).json()
    assert in_game["game_id"] == gid
    assert loose["game_id"] is None

    games = client.get("/api/v1/games").json()
    by_name = {g["name"]: g for g in games}
    assert by_name["World A"]["portfolios"] == 1
    assert by_name["Ungrouped"]["portfolios"] == 1

    only_game = client.get("/api/v1/portfolios", params={"game": gid}).json()
    assert [p["id"] for p in only_game] == [in_game["id"]]
    only_loose = client.get("/api/v1/portfolios", params={"game": "none"}).json()
    assert [p["id"] for p in only_loose] == [loose["id"]]
    everything = client.get("/api/v1/portfolios").json()
    assert len(everything) == 2

    # deleting a game frees its portfolios instead of destroying them
    assert client.delete(f"/api/v1/games/{gid}").status_code == 204
    freed = client.get(f"/api/v1/portfolios/{in_game['id']}").json()
    assert freed["game_id"] is None


# ---- net-worth history + inflation assumption (note 9) ----

def test_networth_history_with_inflation(client, fake_provider, portfolio_id):
    fake_provider.set_price("SPY", "500")  # benchmark drives the date grid
    # backdate the portfolio so it overlaps the price history
    with client.app.state.session_factory() as s:
        p = s.get(Portfolio, portfolio_id)
        created = p.created_at - timedelta(days=10)
        p.created_at = created
        s.commit()

    resp = client.get("/api/v1/networth",
                      params={"range": "1M", "inflation_pct": 3.0})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["portfolios"] == 1
    assert body["points"], "expected history points after backdating"
    # a portfolio contributes nothing before it existed
    assert body["points"][0]["date"] >= created.date().isoformat()
    last = body["points"][-1]
    assert last["value"] == 10000.0  # untouched cash
    assert "real_value" in last and last["real_value"] <= last["value"]
    assert "3.0" in body["note"] and "assumption" in body["note"]

    plain = client.get("/api/v1/networth", params={"range": "1M"}).json()
    assert "real_value" not in plain["points"][-1]


# ---- Future mode (note 11) ----

def _start_future(client, fake_provider, seed="testseed"):
    set_daily_bars(fake_provider, "AAPL")
    set_daily_bars(fake_provider, "MSFT", start=300.0, drift=0.2)
    resp = client.post("/api/v1/future/sessions",
                       json={"symbols": ["aapl", "MSFT"],
                             "starting_cash": "50000", "seed": seed})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_future_session_labeled_and_deterministic(client, fake_provider):
    view = _start_future(client, fake_provider)
    assert view["simulated"] is True
    assert "SIMULATED" in view["disclaimer"]
    assert view["step"] == 0
    for q in view["quotes"].values():
        assert q["simulated"] is True

    advanced = client.post(f"/api/v1/future/sessions/{view['id']}/advance",
                           json={"days": 260}).json()
    assert advanced["step"] == 260
    assert advanced["years_elapsed"] == 1.0
    assert len(advanced["value_points"]) > 10
    assert advanced["virtual_date"] > view["virtual_date"]

    # same seed + same calibration => the identical future, replayed
    twin = _start_future(client, fake_provider)
    twin_adv = client.post(f"/api/v1/future/sessions/{twin['id']}/advance",
                           json={"days": 260}).json()
    assert twin_adv["quotes"]["AAPL"]["price"] == advanced["quotes"]["AAPL"]["price"]


def test_future_trading_and_isolation(client, fake_provider):
    view = _start_future(client, fake_provider)
    sid = view["id"]

    trade = client.post(f"/api/v1/future/sessions/{sid}/trade",
                        json={"symbol": "AAPL", "side": "BUY",
                              "notional": "10000"})
    assert trade.status_code == 201, trade.text
    assert trade.json()["simulated"] is True
    assert trade.json()["status"] == "FILLED"

    after = client.get(f"/api/v1/future/sessions/{sid}").json()
    assert after["holdings"] and after["holdings"][0]["symbol"] == "AAPL"
    assert Decimal(after["cash"]) < Decimal("50000")

    # both quantity and notional (or neither) is rejected
    bad = client.post(f"/api/v1/future/sessions/{sid}/trade",
                      json={"symbol": "AAPL", "side": "BUY"})
    assert bad.status_code == 422
    # symbols outside the game's universe are rejected
    outside = client.post(f"/api/v1/future/sessions/{sid}/trade",
                          json={"symbol": "NVDA", "side": "BUY",
                                "notional": "100"})
    assert outside.status_code == 422

    # the future portfolio never leaks into live portfolio listings
    live = client.get("/api/v1/portfolios").json()
    assert view["portfolio_id"] not in [p["id"] for p in live]

    # abandoning removes the session and its portfolio
    assert client.delete(f"/api/v1/future/sessions/{sid}").status_code == 204
    assert client.get(f"/api/v1/future/sessions/{sid}").status_code == 404
    assert client.get(f"/api/v1/portfolios/{view['portfolio_id']}").status_code == 404
