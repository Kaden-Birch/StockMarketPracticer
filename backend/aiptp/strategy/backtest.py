"""Backtest engine (PRD §22).

Fidelity by construction: each historical day is replayed through the SAME
`conditions.evaluate` used by live automation and the SAME `place_order` /
`fill_order` / lot-accounting machinery used by live trading, against a
scratch in-memory database. Only real historical bars are used.

Deviations (documented): daily-bar granularity (fills at bar close),
schedule/dividend/earnings/news conditions are inert in backtests, and batch
analytics run on CPU here (the GPU path activates on hardware that has one).
"""

import json
import logging
import math
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from ..analytics import indicators as ind
from ..analytics.service import risk_metrics
from ..automation import conditions
from ..marketdata.service import MarketDataService
from ..storage.db import Base, make_engine, make_session_factory
from ..storage.models import (
    CostBasisMethod,
    Holding,
    OrderSide,
    OrderType,
    Origin,
    Portfolio,
    Strategy,
    Transaction,
)
from ..trading.engine import TradingError, place_order

log = logging.getLogger(__name__)

RANGE_TO_YAHOO = {"6M": "6mo", "1Y": "1y", "2Y": "2y", "5Y": "5y", "MAX": "max"}


def substitute_symbol(node: Any, symbol: str):
    """Replace $SYMBOL placeholders so one templated AST serves the whole
    universe."""
    if isinstance(node, dict):
        return {k: substitute_symbol(v, symbol) for k, v in node.items()}
    if isinstance(node, list):
        return [substitute_symbol(v, symbol) for v in node]
    if node == "$SYMBOL":
        return symbol
    return node


def _close_series(market: MarketDataService, symbol: str, yahoo_range: str) -> dict[str, float]:
    hist = market.get_history(symbol, yahoo_range, "1d")
    return {
        datetime.fromtimestamp(b.ts, tz=timezone.utc).date().isoformat(): b.close
        for b in hist.bars
        if b.close
    }


def classify_regimes(bench_closes: list[float], window: int = 40) -> list[str]:
    """bull / bear / sideways by trailing benchmark return over `window`
    trading days (±5% thresholds)."""
    out = []
    for i in range(len(bench_closes)):
        j = max(0, i - window)
        base = bench_closes[j]
        change = (bench_closes[i] - base) / base if base else 0
        out.append("bull" if change > 0.05 else "bear" if change < -0.05 else "sideways")
    return out


def run_backtest(
    strategy: Strategy,
    market: MarketDataService,
    range_: str = "1Y",
    progress=None,
) -> dict[str, Any]:
    yahoo_range = RANGE_TO_YAHOO.get(range_.upper(), "1y")
    universe = [s.upper() for s in json.loads(strategy.universe)]
    entry_ast = json.loads(strategy.entry_trigger)
    exit_ast = json.loads(strategy.exit_trigger) if strategy.exit_trigger else None

    bench_closes_map = _close_series(market, strategy.benchmark, yahoo_range)
    days = sorted(bench_closes_map)
    if len(days) < 10:
        raise ValueError("Not enough benchmark history for this range")
    closes = {s: _close_series(market, s, yahoo_range) for s in universe}

    # Scratch in-memory portfolio — real engine, throwaway storage.
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    scratch = make_session_factory(engine)()
    portfolio = Portfolio(
        name=f"backtest:{strategy.name}",
        starting_balance=strategy.initial_cash,
        cash_balance=strategy.initial_cash,
        cost_basis_method=CostBasisMethod.FIFO,
    )
    scratch.add(portfolio)
    scratch.flush()

    def indicator_fn_at(day_index: int):
        def fn(symbol: str, name: str, period: int) -> float | None:
            series = [
                closes[symbol][d]
                for d in days[: day_index + 1]
                if d in closes.get(symbol, {})
            ]
            func = ind.INDICATORS.get(name.upper())
            return func(series, period) if func else None
        return fn

    points: list[dict] = []
    trade_log: list[dict] = []
    last_price: dict[str, Decimal] = {}
    prev_price: dict[str, Decimal] = {}

    for i, day in enumerate(days):
        prices: dict[str, Decimal] = {}
        for s in universe:
            close = closes[s].get(day)
            if close is not None:
                if s in last_price:
                    prev_price[s] = last_price[s]
                prices[s] = last_price[s] = Decimal(str(close))
            elif s in last_price:
                prices[s] = last_price[s]

        holdings = {h.symbol: h for h in portfolio.holdings if h.quantity > 0}
        position_value = sum(
            (h.quantity * prices[s] for s, h in holdings.items() if s in prices),
            Decimal("0"),
        )
        total_value = portfolio.cash_balance + position_value
        view = {
            "total_value": str(total_value),
            "cash_balance": str(portfolio.cash_balance),
            "holdings": [
                {"symbol": s, "market_value": str(h.quantity * prices[s])}
                for s, h in holdings.items()
                if s in prices
            ],
        }
        ctx = conditions.RuleContext(
            prices=prices,
            previous_closes=prev_price,
            portfolio_view=view,
            indicator_fn=indicator_fn_at(i),
            recent_dividends={},
            now=datetime.fromisoformat(day + "T21:00:00+00:00"),
        )

        for s in universe:
            if s not in prices:
                continue
            held = s in holdings
            try:
                if not held and conditions.evaluate(substitute_symbol(entry_ast, s), ctx):
                    order, txn = place_order(
                        scratch, portfolio, symbol=s, side=OrderSide.BUY,
                        type_=OrderType.MARKET, notional=strategy.entry_notional,
                        origin=Origin.AUTOMATION, current_price=prices[s],
                    )
                    if txn:
                        trade_log.append({"date": day, "side": "BUY", "symbol": s,
                                          "quantity": str(txn.quantity),
                                          "price": str(txn.price)})
                elif held and exit_ast and conditions.evaluate(substitute_symbol(exit_ast, s), ctx):
                    qty = holdings[s].quantity
                    order, txn = place_order(
                        scratch, portfolio, symbol=s, side=OrderSide.SELL,
                        type_=OrderType.MARKET, quantity=qty,
                        origin=Origin.AUTOMATION, current_price=prices[s],
                    )
                    if txn:
                        trade_log.append({"date": day, "side": "SELL", "symbol": s,
                                          "quantity": str(txn.quantity),
                                          "price": str(txn.price),
                                          "realized_pnl": str(txn.realized_pnl)})
            except TradingError:
                continue  # e.g. cash exhausted — same behavior as live
        scratch.flush()
        # New Holding rows are added via the session, not the relationship —
        # expire so the next day's holdings check sees them.
        scratch.expire(portfolio)

        holdings = {h.symbol: h for h in portfolio.holdings if h.quantity > 0}
        position_value = sum(
            (h.quantity * prices[s] for s, h in holdings.items() if s in prices),
            Decimal("0"),
        )
        equity = float(portfolio.cash_balance + position_value)
        points.append({"date": day, "value": round(equity, 2),
                       "benchmark_close": bench_closes_map[day]})
        if progress and i % 20 == 0:
            progress(int(i / len(days) * 100))

    # ---- report ----
    txns = scratch.scalars(select(Transaction)).all()
    sells = [t for t in txns if t.side == OrderSide.SELL and t.realized_pnl is not None]
    wins = sum(1 for t in sells if t.realized_pnl > 0)
    initial = float(strategy.initial_cash)
    final = points[-1]["value"]
    bench_first, bench_last = points[0]["benchmark_close"], points[-1]["benchmark_close"]

    regimes = classify_regimes([p["benchmark_close"] for p in points])
    regime_returns: dict[str, list[float]] = {"bull": [], "bear": [], "sideways": []}
    for k in range(1, len(points)):
        prev_v, cur_v = points[k - 1]["value"], points[k]["value"]
        if prev_v > 0:
            regime_returns[regimes[k]].append((cur_v - prev_v) / prev_v)
    by_regime = {
        name: {
            "days": len(rets),
            "total_return_pct": round((math.prod(1 + r for r in rets) - 1) * 100, 2) if rets else None,
            "avg_daily_return_pct": round(statistics.fmean(rets) * 100, 4) if rets else None,
        }
        for name, rets in regime_returns.items()
    }

    open_positions = [
        {"symbol": h.symbol, "quantity": str(h.quantity),
         "value": str((h.quantity * last_price[h.symbol]).quantize(Decimal("0.01")))}
        for h in portfolio.holdings
        if h.quantity > 0 and h.symbol in last_price
    ]
    realized_total = sum((t.realized_pnl for t in sells), Decimal("0"))
    scratch.close()
    return {
        "strategy_id": strategy.id,
        "range": range_.upper(),
        "days": len(points),
        "initial_cash": str(strategy.initial_cash),
        "final_value": final,
        "total_return_pct": round((final - initial) / initial * 100, 2),
        "benchmark": strategy.benchmark,
        "benchmark_return_pct": round((bench_last - bench_first) / bench_first * 100, 2),
        "trades": len(trade_log),
        "closed_trades": len(sells),
        "wins": wins,
        "losses": len(sells) - wins,
        "win_rate": round(wins / len(sells) * 100, 1) if sells else None,
        "realized_pnl": str(realized_total.quantize(Decimal("0.01"))),
        "risk": risk_metrics(points),
        "by_regime": by_regime,
        "open_positions": open_positions,
        "trade_log": trade_log[-500:],
        "equity_curve": points,
    }
