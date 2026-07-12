"""Pending orders fill through the watch cycle when prices move."""

from decimal import Decimal


def run_cycle(client, fake_provider):
    app = client.app
    from aiptp.watcher import run_watch_cycle

    run_watch_cycle(app.state.session_factory, app.state.market, app.state.bus)


def test_limit_buy_fills_when_price_drops(client, fake_provider, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "LIMIT",
              "quantity": "10", "limit_price": "180"},
    )
    order_id = resp.json()["id"]
    assert resp.json()["status"] == "PENDING"

    run_cycle(client, fake_provider)  # price still 200 — nothing happens
    orders = client.get(f"/api/v1/portfolios/{portfolio_id}/orders").json()
    assert orders[0]["status"] == "PENDING"

    fake_provider.set_price("AAPL", "175")
    run_cycle(client, fake_provider)

    orders = {o["id"]: o for o in client.get(f"/api/v1/portfolios/{portfolio_id}/orders").json()}
    assert orders[order_id]["status"] == "FILLED"

    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    # filled at 175 (market better than 180 limit): 10000 - 1750
    assert portfolio["cash_balance"] == "8250.00"


def test_stop_sell_protects_position(client, fake_provider, portfolio_id):
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "STOP",
              "quantity": "10", "stop_price": "190"},
    )
    assert resp.json()["status"] == "PENDING"

    fake_provider.set_price("AAPL", "185")
    run_cycle(client, fake_provider)

    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    assert portfolio["holdings"] == []
    # bought 10@200 (=8000 cash), stop-sold 10@185 (+1850)
    assert portfolio["cash_balance"] == "9850.00"

    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    assert Decimal(txns[0]["realized_pnl"]) == Decimal("-150.00")


def test_pending_buy_rejected_if_cash_spent_elsewhere(client, fake_provider, portfolio_id):
    # commit almost all cash to a pending limit buy, then spend it manually
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "MSFT", "side": "BUY", "type": "LIMIT",
              "quantity": "24", "limit_price": "390"},
    )
    pending_id = resp.json()["id"]
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "45"},
    )  # 9000 spent, 1000 left

    fake_provider.set_price("MSFT", "385")
    run_cycle(client, fake_provider)

    orders = {o["id"]: o for o in client.get(f"/api/v1/portfolios/{portfolio_id}/orders").json()}
    assert orders[pending_id]["status"] == "REJECTED"
    assert "Insufficient cash" in orders[pending_id]["reject_reason"]
