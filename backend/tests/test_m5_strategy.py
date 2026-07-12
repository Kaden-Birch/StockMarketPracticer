"""M5: backtesting through the shared live code paths, and the what-if
simulator's transaction transforms."""

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiptp.marketdata.base import Bar

# (Transaction/OrderSide imported lazily inside insert_txn to keep fixtures light)


def make_bars(prices: list[float], start_days_ago: int | None = None) -> list[Bar]:
    n = len(prices)
    start_days_ago = start_days_ago if start_days_ago is not None else n
    base = int(time.time()) - start_days_ago * 86400
    return [
        Bar(ts=base + i * 86400, open=p, high=p, low=p, close=p, volume=0)
        for i, p in enumerate(prices)
    ]


def wait_done(client, run_id: str) -> dict:
    for _ in range(100):
        run = client.get(f"/api/v1/strategies/backtests/{run_id}").json()
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.05)
    raise AssertionError("backtest did not finish")


def test_backtest_buy_dip_sell_rip(client, fake_provider):
    # 30 days: flat 100, dip to 80 (day 10-12), recover, spike to 130 (day 25+)
    prices = [100.0] * 10 + [80.0, 78.0, 82.0] + [100.0] * 12 + [130.0] * 5
    fake_provider.set_price("XYZ", str(prices[-1]))
    fake_provider.history_bars["XYZ"] = make_bars(prices)
    fake_provider.set_price("SPY", "500")
    fake_provider.history_bars["SPY"] = make_bars([500.0] * len(prices))

    strategy = client.post(
        "/api/v1/strategies",
        json={
            "name": "Dip buyer",
            "universe": ["XYZ"],
            "entry_trigger": {"price": {"symbol": "$SYMBOL", "op": "<", "value": 90}},
            "exit_trigger": {"price": {"symbol": "$SYMBOL", "op": ">", "value": 120}},
            "entry_notional": "1000",
            "initial_cash": "10000",
        },
    )
    assert strategy.status_code == 201, strategy.text
    sid = strategy.json()["id"]

    start = client.post(f"/api/v1/strategies/{sid}/backtest", json={"range": "1Y"})
    assert start.status_code == 202
    run = wait_done(client, start.json()["run_id"])
    assert run["status"] == "DONE", run["error"]
    r = run["results"]

    # bought at 80 (first dip close), sold at 130: 1000/80 = 12.5 shares
    assert r["trades"] == 2
    assert r["closed_trades"] == 1
    assert r["win_rate"] == 100.0
    log = r["trade_log"]
    assert log[0]["side"] == "BUY" and Decimal(log[0]["price"]) == 80
    assert log[1]["side"] == "SELL" and Decimal(log[1]["price"]) == 130
    assert Decimal(log[1]["realized_pnl"]) == Decimal("625.00")  # 12.5 * 50
    assert r["final_value"] == 10625.0
    assert r["total_return_pct"] == 6.25
    assert r["benchmark_return_pct"] == 0.0
    assert len(r["equity_curve"]) == len(prices)
    assert r["open_positions"] == []
    assert set(r["by_regime"]) == {"bull", "bear", "sideways"}


def test_backtest_open_position_valued_and_no_reentry(client, fake_provider):
    # enters at 80 and never exits: open position marked to market
    prices = [100.0] * 5 + [80.0] * 25
    fake_provider.set_price("ABC", "80")
    fake_provider.history_bars["ABC"] = make_bars(prices)
    fake_provider.set_price("SPY", "500")
    fake_provider.history_bars["SPY"] = make_bars([500.0] * len(prices))

    sid = client.post(
        "/api/v1/strategies",
        json={
            "name": "Hold forever",
            "universe": ["ABC"],
            "entry_trigger": {"price": {"symbol": "$SYMBOL", "op": "<", "value": 90}},
            "entry_notional": "2000",
            "initial_cash": "5000",
        },
    ).json()["id"]
    run = wait_done(
        client, client.post(f"/api/v1/strategies/{sid}/backtest", json={}).json()["run_id"]
    )
    r = run["results"]
    assert r["trades"] == 1  # holds — no re-entry while position is open
    assert len(r["open_positions"]) == 1
    assert r["final_value"] == 5000.0  # flat after entry: value conserved
    assert r["closed_trades"] == 0 and r["win_rate"] is None


def test_backtest_indicator_strategy(client, fake_provider):
    # declining series keeps RSI low -> RSI<50 entry fires once cash allows
    prices = [float(100 - i) for i in range(30)]
    fake_provider.set_price("DEF", str(prices[-1]))
    fake_provider.history_bars["DEF"] = make_bars(prices)
    fake_provider.set_price("SPY", "500")
    fake_provider.history_bars["SPY"] = make_bars([500.0] * len(prices))
    sid = client.post(
        "/api/v1/strategies",
        json={
            "name": "RSI entry",
            "universe": ["DEF"],
            "entry_trigger": {"indicator": {"symbol": "$SYMBOL", "name": "RSI",
                                             "period": 14, "op": "<", "value": 50}},
            "entry_notional": "1000",
            "initial_cash": "3000",
        },
    ).json()["id"]
    run = wait_done(
        client, client.post(f"/api/v1/strategies/{sid}/backtest", json={}).json()["run_id"]
    )
    assert run["status"] == "DONE", run["error"]
    assert run["results"]["trades"] == 1  # enters when RSI computable, then holds


def test_strategy_validation(client):
    r = client.post(
        "/api/v1/strategies",
        json={"name": "bad", "universe": ["X"],
              "entry_trigger": {"price": {"symbol": "$SYMBOL"}}},
    )
    assert r.status_code == 422


# ---- what-if simulator ----

def seed_history(fake_provider, symbol: str, prices: list[float]):
    fake_provider.set_price(symbol, str(prices[-1]))
    fake_provider.history_bars[symbol] = make_bars(prices, start_days_ago=len(prices))


def insert_txn(client, portfolio_id, symbol, side, qty, price, days_ago):
    """Insert a past-dated transaction directly — orders always execute 'now',
    but what-if scenarios only differentiate on historical dates."""
    from aiptp.storage.models import OrderSide, Transaction

    session = client.app.state.session_factory()
    try:
        session.add(
            Transaction(
                portfolio_id=portfolio_id,
                symbol=symbol,
                side=OrderSide(side),
                quantity=Decimal(str(qty)),
                price=Decimal(str(price)),
                amount=Decimal(str(qty)) * Decimal(str(price)),
                executed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
            )
        )
        session.commit()
    finally:
        session.close()


def test_whatif_substitute(client, fake_provider, portfolio_id):
    seed_history(fake_provider, "SPY", [500.0] * 40)
    seed_history(fake_provider, "AAPL", [200.0] * 40)  # flat
    # ROCKET: 50 until ~10 days ago, then 100
    seed_history(fake_provider, "ROCKET", [50.0] * 30 + [100.0] * 10)

    insert_txn(client, portfolio_id, "AAPL", "BUY", 10, 200, days_ago=25)
    result = client.post(
        f"/api/v1/portfolios/{portfolio_id}/whatif",
        json={"scenario": {"type": "substitute", "from_symbol": "AAPL",
                            "to_symbol": "ROCKET"}, "range": "1M"},
    ).json()
    # actual: 8000 cash + 10 AAPL * 200 = 10000
    # hypothetical: 2000 bought ROCKET at 50 (25 days ago) = 40 shares,
    # worth 100 each now: 8000 + 4000 = 12000
    assert result["actual_final"] == 10000.0
    assert result["hypothetical_final"] == 12000.0
    assert result["delta"] == 2000.0
    assert "ROCKET" in result["description"]
    # actual portfolio untouched (transaction log unchanged)
    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    assert [t["symbol"] for t in txns] == ["AAPL"]


def test_whatif_never_sold(client, fake_provider, portfolio_id):
    seed_history(fake_provider, "SPY", [500.0] * 40)
    # 200 until ~10 days ago, then 400
    seed_history(fake_provider, "AAPL", [200.0] * 30 + [400.0] * 10)

    insert_txn(client, portfolio_id, "AAPL", "BUY", 10, 200, days_ago=25)
    insert_txn(client, portfolio_id, "AAPL", "SELL", 10, 200, days_ago=15)
    result = client.post(
        f"/api/v1/portfolios/{portfolio_id}/whatif",
        json={"scenario": {"type": "never_sold", "symbol": "AAPL"}, "range": "1M"},
    ).json()
    # actual: sold flat -> 10000. hypothetical: kept 10 shares now worth 400:
    # 8000 + 4000 = 12000
    assert result["actual_final"] == 10000.0
    assert result["hypothetical_final"] == 12000.0
    assert result["delta"] == 2000.0

    # probe: nothing to suppress
    r = client.post(
        f"/api/v1/portfolios/{portfolio_id}/whatif",
        json={"scenario": {"type": "never_sold", "symbol": "MSFT"}},
    )
    assert r.status_code == 422


def test_whatif_monthly_dca_and_unknown_type(client, fake_provider, portfolio_id):
    seed_history(fake_provider, "SPY", [500.0] * 80)
    seed_history(fake_provider, "AAPL", [200.0] * 80)
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "notional": "3000"},
    )
    result = client.post(
        f"/api/v1/portfolios/{portfolio_id}/whatif",
        json={"scenario": {"type": "monthly_dca", "symbol": "AAPL"}, "range": "1M"},
    )
    assert result.status_code == 200
    body = result.json()
    # flat prices: DCA ends at the same value, just spread out
    assert body["hypothetical_final" ] == body["actual_final"]

    assert client.post(
        f"/api/v1/portfolios/{portfolio_id}/whatif",
        json={"scenario": {"type": "time_travel"}},
    ).status_code == 422
