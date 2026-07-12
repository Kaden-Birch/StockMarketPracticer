from decimal import Decimal


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_portfolio_lifecycle(client):
    resp = client.post(
        "/api/v1/portfolios",
        json={"name": "Growth", "starting_balance": "5000", "cost_basis_method": "LIFO"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["cash_balance"] == "5000"
    assert data["cost_basis_method"] == "LIFO"
    pid = data["id"]

    resp = client.patch(f"/api/v1/portfolios/{pid}", json={"name": "Growth II"})
    assert resp.json()["name"] == "Growth II"

    assert len(client.get("/api/v1/portfolios").json()) == 1
    assert client.delete(f"/api/v1/portfolios/{pid}").status_code == 204
    assert client.get(f"/api/v1/portfolios/{pid}").status_code == 404


def test_market_buy_and_sell_flow(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "FILLED"

    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    assert portfolio["cash_balance"] == "8000.00"  # 10000 - 10*200
    holding = portfolio["holdings"][0]
    assert holding["symbol"] == "AAPL"
    assert Decimal(holding["quantity"]) == 10
    assert holding["market_value"] == "2000.00"

    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "MARKET", "quantity": "4"},
    )
    assert resp.status_code == 201

    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    assert len(txns) == 2
    sell = txns[0]
    assert sell["side"] == "SELL"
    assert Decimal(sell["realized_pnl"]) == 0  # flat price in fake provider
    assert sell["origin"] == "MANUAL"


def test_notional_market_buy(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "NVDA", "side": "BUY", "type": "MARKET", "notional": "1000"},
    )
    assert resp.status_code == 201
    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    holding = portfolio["holdings"][0]
    # 1000 / 150 = 6.666666 (rounded down to 6 dp)
    assert holding["quantity"] == "6.666666"


def test_insufficient_cash_rejected(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "MSFT", "side": "BUY", "type": "MARKET", "quantity": "100"},
    )
    assert resp.status_code == 422
    assert "Insufficient cash" in resp.json()["detail"]


def test_oversell_rejected(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "MARKET", "quantity": "1"},
    )
    assert resp.status_code == 422
    assert "Insufficient shares" in resp.json()["detail"]


def test_unknown_symbol_404(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "NOPE", "side": "BUY", "type": "MARKET", "quantity": "1"},
    )
    assert resp.status_code == 404


def test_limit_order_pends_then_cancel(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "LIMIT",
              "quantity": "5", "limit_price": "150"},
    )
    assert resp.status_code == 201
    order = resp.json()
    assert order["status"] == "PENDING"  # price is 200, limit 150 not marketable

    resp = client.delete(f"/api/v1/portfolios/{portfolio_id}/orders/{order['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_marketable_limit_fills_immediately_at_market(client, portfolio_id):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "LIMIT",
              "quantity": "5", "limit_price": "250"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "FILLED"
    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    assert Decimal(txns[0]["price"]) == 200  # market, not the worse limit


def test_quotes_and_history_endpoints(client):
    quotes = client.get("/api/v1/marketdata/quotes", params={"symbols": "aapl,msft"}).json()
    assert quotes["AAPL"]["price"] == "200"
    assert quotes["AAPL"]["provider"] == "fake"

    hist = client.get("/api/v1/marketdata/history/AAPL", params={"range": "1M"}).json()
    assert hist["symbol"] == "AAPL"
    assert len(hist["bars"]) == 30

    assert client.get(
        "/api/v1/marketdata/history/AAPL", params={"range": "bogus"}
    ).status_code == 422
