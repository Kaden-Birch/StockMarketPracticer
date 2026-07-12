"""M2 trading depth: trailing stops, percent sizing, batch, rebalance, DCA."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


def run_cycle(client):
    from aiptp.watcher import run_watch_cycle

    app = client.app
    run_watch_cycle(app.state.session_factory, app.state.market, app.state.bus)


def test_trailing_stop_ratchets_and_fills(client, fake_provider, portfolio_id):
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "TRAILING_STOP",
              "quantity": "10", "trail_percent": "5"},
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "PENDING"
    assert Decimal(order["watermark"]) == 200  # initialized at placement price

    # price climbs: watermark ratchets, no fill
    fake_provider.set_price("AAPL", "220")
    run_cycle(client)
    orders = client.get(f"/api/v1/portfolios/{portfolio_id}/orders").json()
    trailing = next(o for o in orders if o["type"] == "TRAILING_STOP")
    assert trailing["status"] == "PENDING"
    assert Decimal(trailing["watermark"]) == 220

    # small dip within the 5% trail: still pending
    fake_provider.set_price("AAPL", "212")
    run_cycle(client)
    trailing = next(
        o for o in client.get(f"/api/v1/portfolios/{portfolio_id}/orders").json()
        if o["type"] == "TRAILING_STOP"
    )
    assert trailing["status"] == "PENDING"
    assert Decimal(trailing["watermark"]) == 220  # never ratchets down

    # drop through 220 * 0.95 = 209: fills
    fake_provider.set_price("AAPL", "205")
    run_cycle(client)
    trailing = next(
        o for o in client.get(f"/api/v1/portfolios/{portfolio_id}/orders").json()
        if o["type"] == "TRAILING_STOP"
    )
    assert trailing["status"] == "FILLED"
    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    assert portfolio["holdings"] == []
    # 10000 - 2000 + 2050
    assert portfolio["cash_balance"] == "10050.00"


def test_trailing_stop_validation(client, portfolio_id):
    r = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "TRAILING_STOP", "quantity": "1"},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "TRAILING_STOP",
              "quantity": "1", "trail_amount": "5", "trail_percent": "5"},
    )
    assert r.status_code == 422


def test_percent_of_cash_buy(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
              "percent": "50", "percent_of": "CASH"},
    )
    assert resp.status_code == 201, resp.text
    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    assert portfolio["cash_balance"] == "5000.00"  # 50% of 10000 spent


def test_percent_of_position_sell(client, portfolio_id):
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "MARKET",
              "percent": "25", "percent_of": "POSITION"},
    )
    assert resp.status_code == 201, resp.text
    holding = client.get(f"/api/v1/portfolios/{portfolio_id}").json()["holdings"][0]
    assert Decimal(holding["quantity"]) == Decimal("7.5")


def test_batch_orders_partial_failure(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders/batch",
        json={"orders": [
            {"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "5"},
            {"symbol": "MSFT", "side": "BUY", "type": "MARKET", "quantity": "5"},
            {"symbol": "NVDA", "side": "SELL", "type": "MARKET", "quantity": "5"},
        ]},
    )
    assert resp.status_code == 201
    results = resp.json()["results"]
    assert [r["status"] for r in results[:2]] == ["FILLED", "FILLED"]
    assert results[2]["status"] == "ERROR"
    assert "Insufficient shares" in results[2]["error"]
    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    assert len(portfolio["holdings"]) == 2  # first two fills survived


def test_rebalance_preview_and_execute(client, fake_provider, portfolio_id):
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "40"},
    )  # 8000 in AAPL, 2000 cash
    preview = client.post(
        f"/api/v1/portfolios/{portfolio_id}/rebalance",
        json={"targets": {"AAPL": 50, "MSFT": 30}, "execute": False},
    ).json()
    trades = preview["plan"]["trades"]
    sides = {t["symbol"]: t["side"] for t in trades}
    assert sides == {"AAPL": "SELL", "MSFT": "BUY"}
    assert preview["executed"] is None

    done = client.post(
        f"/api/v1/portfolios/{portfolio_id}/rebalance",
        json={"targets": {"AAPL": 50, "MSFT": 30}, "execute": True},
    ).json()
    assert all(r["status"] == "FILLED" for r in done["executed"])
    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    weights = {
        h["symbol"]: Decimal(h["market_value"]) / Decimal(portfolio["total_value"]) * 100
        for h in portfolio["holdings"]
    }
    assert abs(weights["AAPL"] - 50) < 1
    assert abs(weights["MSFT"] - 30) < 1


def test_rebalance_rejects_over_100(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/rebalance",
        json={"targets": {"AAPL": 80, "MSFT": 30}, "execute": False},
    )
    assert resp.status_code == 422


def test_recurring_plan_executes_when_due(client, fake_provider, portfolio_id):
    from aiptp.trading.recurring import run_recurring_cycle

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/plans",
        json={"symbol": "NVDA", "amount": "300", "cadence": "WEEKLY", "start_at": past},
    )
    assert resp.status_code == 201, resp.text

    app = client.app
    run_recurring_cycle(app.state.session_factory, app.state.market, app.state.bus)

    plan = client.get(f"/api/v1/portfolios/{portfolio_id}/plans").json()[0]
    assert plan["run_count"] == 1
    next_run = datetime.fromisoformat(plan["next_run_at"])
    if next_run.tzinfo is None:  # SQLite drops tz info
        next_run = next_run.replace(tzinfo=timezone.utc)
    assert next_run > datetime.now(timezone.utc)

    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    assert txns[0]["symbol"] == "NVDA"
    assert txns[0]["origin"] == "AUTOMATION"
    # 300 / 150 = 2 shares
    assert Decimal(txns[0]["quantity"]) == 2

    # running again immediately does nothing (not due)
    run_recurring_cycle(app.state.session_factory, app.state.market, app.state.bus)
    assert client.get(f"/api/v1/portfolios/{portfolio_id}/plans").json()[0]["run_count"] == 1
