"""M2 corporate actions, FX, watchlists, analytics, exports, failover."""

import time
from decimal import Decimal

from aiptp.marketdata.base import CorporateAction


def run_corp(client):
    from aiptp.trading.corporate import run_corporate_actions_cycle

    app = client.app
    run_corporate_actions_cycle(app.state.session_factory, app.state.market, app.state.bus)


def test_dividend_credits_cash_for_shares_held_at_ex_date(client, fake_provider, portfolio_id):
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    ex_ts = int(time.time()) + 60  # after the buy
    fake_provider.corporate_actions["AAPL"] = [
        CorporateAction(symbol="AAPL", kind="DIVIDEND", ex_ts=ex_ts, amount=Decimal("0.50"))
    ]
    time.sleep(0.01)
    run_corp(client)

    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    assert portfolio["cash_balance"] == "8005.00"  # 8000 + 10 * 0.50
    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    div = txns[0]
    assert div["kind"] == "DIVIDEND"
    assert div["origin"] == "SYSTEM"
    assert Decimal(div["amount"]) == Decimal("5.00")

    # idempotent: second run applies nothing
    run_corp(client)
    assert client.get(f"/api/v1/portfolios/{portfolio_id}").json()["cash_balance"] == "8005.00"


def test_dividend_skipped_if_bought_after_ex_date(client, fake_provider, portfolio_id):
    ex_ts = int(time.time()) - 86400  # yesterday — before any purchase
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    fake_provider.corporate_actions["AAPL"] = [
        CorporateAction(symbol="AAPL", kind="DIVIDEND", ex_ts=ex_ts, amount=Decimal("1.00"))
    ]
    run_corp(client)
    assert client.get(f"/api/v1/portfolios/{portfolio_id}").json()["cash_balance"] == "8000.00"


def test_split_adjusts_lots_preserving_basis(client, fake_provider, portfolio_id):
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    fake_provider.corporate_actions["AAPL"] = [
        CorporateAction(
            symbol="AAPL", kind="SPLIT", ex_ts=int(time.time()) + 60, ratio=Decimal("4")
        )
    ]
    fake_provider.set_price("AAPL", "50")  # post-split price
    time.sleep(0.01)
    run_corp(client)

    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    holding = portfolio["holdings"][0]
    assert Decimal(holding["quantity"]) == 40
    assert Decimal(holding["cost_basis"]) == 2000  # basis unchanged
    assert holding["avg_cost"] == "50.00"
    assert Decimal(holding["unrealized_pnl"]) == 0
    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    assert txns[0]["kind"] == "SPLIT"
    assert Decimal(txns[0]["quantity"]) == 30  # share delta


def test_dividend_reinvest(client, fake_provider, portfolio_id):
    client.patch(f"/api/v1/portfolios/{portfolio_id}", json={"dividend_reinvest": True})
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    fake_provider.corporate_actions["AAPL"] = [
        CorporateAction(
            symbol="AAPL", kind="DIVIDEND", ex_ts=int(time.time()) + 60, amount=Decimal("20")
        )
    ]
    time.sleep(0.01)
    run_corp(client)
    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    # 200 dividend immediately reinvested at 200/share -> +1 share, cash back to 8000
    assert Decimal(portfolio["holdings"][0]["quantity"]) == 11
    assert portfolio["cash_balance"] == "8000.00"
    origins = [t["origin"] for t in
               client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()]
    assert "DIVIDEND_REINVEST" in origins


def test_foreign_currency_buy_converts_cash(client, fake_provider, portfolio_id):
    fake_provider.set_price("SAP.DE", "100")  # EUR-denominated
    fake_provider.currencies["SAP.DE"] = "EUR"
    fake_provider.fx_rates[("EUR", "USD")] = Decimal("1.10")
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "SAP.DE", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    assert resp.status_code == 201, resp.text
    portfolio = client.get(f"/api/v1/portfolios/{portfolio_id}").json()
    # 10 shares * 100 EUR * 1.10 = 1100 USD
    assert portfolio["cash_balance"] == "8900.00"
    holding = portfolio["holdings"][0]
    assert holding["market_value"] == "1100.00"  # valued through FX too
    txn = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()[0]
    assert txn["quote_currency"] == "EUR"
    assert Decimal(txn["fx_rate"]) == Decimal("1.10")
    assert Decimal(txn["price"]) == 100  # price stays in the security currency


def test_watchlist_crud(client, fake_provider):
    wl = client.post("/api/v1/watchlists", json={"name": "Tech"}).json()
    resp = client.post(f"/api/v1/watchlists/{wl['id']}/items", json={"symbol": "aapl"})
    assert resp.status_code == 201
    view = resp.json()
    assert view["items"][0]["symbol"] == "AAPL"
    assert view["items"][0]["price"] == "200"

    # duplicate rejected
    assert client.post(
        f"/api/v1/watchlists/{wl['id']}/items", json={"symbol": "AAPL"}
    ).status_code == 409
    # unknown symbol rejected
    assert client.post(
        f"/api/v1/watchlists/{wl['id']}/items", json={"symbol": "NOPE"}
    ).status_code == 404

    assert client.delete(f"/api/v1/watchlists/{wl['id']}/items/AAPL").status_code == 204
    assert client.get("/api/v1/watchlists").json()[0]["items"] == []
    assert client.delete(f"/api/v1/watchlists/{wl['id']}").status_code == 204
    assert client.get("/api/v1/watchlists").json() == []


def test_compare_endpoint(client, fake_provider):
    fake_provider.set_price("SPY", "500")
    resp = client.get(
        "/api/v1/marketdata/compare", params={"symbols": "AAPL,MSFT", "range": "1M"}
    )
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert [s["symbol"] for s in series] == ["AAPL", "MSFT"]
    # flat fake history normalizes to 100 throughout
    assert all(p["value"] == 100 for p in series[0]["points"])
    assert client.get(
        "/api/v1/marketdata/compare", params={"symbols": "AAPL"}
    ).status_code == 422


def test_analytics_and_value_history(client, fake_provider, portfolio_id):
    fake_provider.set_price("SPY", "500")
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "SELL", "type": "MARKET", "quantity": "5"},
    )
    history = client.get(f"/api/v1/portfolios/{portfolio_id}/value-history?range=1M").json()
    assert history["benchmark"] == "SPY"
    assert len(history["points"]) > 0
    # flat prices: value stays at starting balance
    assert all(abs(p["value"] - 10000) < 0.01 for p in history["points"])

    analytics = client.get(f"/api/v1/portfolios/{portfolio_id}/analytics?range=1M").json()
    assert analytics["records"]["closed_trades"] == 1
    assert analytics["records"]["win_rate"] == 0.0  # flat-price sell: closed, not a win
    assert analytics["records"]["avg_holding_days"] is not None
    div = analytics["diversification"]
    assert div["score"] is not None
    assert "AAPL" in div["weights"] and "CASH" in div["weights"]


def test_exports(client, fake_provider, portfolio_id):
    fake_provider.set_price("SPY", "500")
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    csv_resp = client.get(f"/api/v1/portfolios/{portfolio_id}/export?format=csv")
    assert csv_resp.status_code == 200
    assert "attachment" in csv_resp.headers["content-disposition"]
    assert "AAPL" in csv_resp.text and "executed_at" in csv_resp.text

    json_resp = client.get(f"/api/v1/portfolios/{portfolio_id}/export?format=json")
    assert json_resp.status_code == 200
    body = json_resp.json()
    assert body["portfolio"]["name"] == "Test"
    assert len(body["transactions"]) == 1

    md_resp = client.get(f"/api/v1/portfolios/{portfolio_id}/export?format=md")
    assert md_resp.status_code == 200
    assert "# Portfolio report" in md_resp.text
    assert "| AAPL |" in md_resp.text

    xlsx = client.get(f"/api/v1/portfolios/{portfolio_id}/export?format=xlsx")
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"  # zip container

    pdf = client.get(f"/api/v1/portfolios/{portfolio_id}/export?format=pdf")
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-"

    assert client.get(
        f"/api/v1/portfolios/{portfolio_id}/export?format=docx"
    ).status_code == 422


def test_provider_failover():
    from aiptp.marketdata.base import MarketDataError
    from aiptp.marketdata.fake import FakeProvider
    from aiptp.marketdata.service import MarketDataService

    class FailingProvider(FakeProvider):
        name = "failing"

        def get_quotes(self, symbols):
            raise MarketDataError("provider down")

    good = FakeProvider({"AAPL": "123"})
    service = MarketDataService([FailingProvider(), good], quote_ttl=0)
    quote = service.get_quote("AAPL")
    assert quote.price == Decimal("123")
    assert quote.provider == "fake"
