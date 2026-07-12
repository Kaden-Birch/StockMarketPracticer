"""Analytics v1: portfolio value history reconstructed from the immutable
transaction log + real daily bars, risk metrics, and trade records.

Approximations (documented): foreign-currency positions are valued at the
current FX rate across the whole series (historical FX series arrives with a
keyed provider); the holding-period/win-rate matcher pairs sells to buys FIFO
regardless of the portfolio's cost-basis method."""

import math
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import OrderSide, Portfolio, Transaction, TransactionKind

TRADING_DAYS = 252
RANGE_TO_YAHOO = {"1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y", "5Y": "5y", "MAX": "max"}


def _close_map(market: MarketDataService, symbol: str, range_: str) -> dict[str, float]:
    hist = market.get_history(symbol, range_, "1d")
    out = {}
    for bar in hist.bars:
        day = datetime.fromtimestamp(bar.ts, tz=timezone.utc).date().isoformat()
        out[day] = bar.close
    return out


def replay_series(
    txns: list,
    starting_balance: Decimal,
    market: MarketDataService,
    range_: str = "1Y",
    benchmark: str = "SPY",
    portfolio_currency: str = "USD",
) -> list[dict[str, Any]]:
    """Daily value series from ANY transaction-like list (objects with kind,
    side, symbol, quantity, amount, executed_at). Shared by portfolio value
    history and the what-if simulator's hypothetical replays."""
    yahoo_range = RANGE_TO_YAHOO.get(range_.upper(), "1y")
    symbols = sorted({t.symbol for t in txns})
    bench_closes = _close_map(market, benchmark, yahoo_range)
    days = sorted(bench_closes)
    closes: dict[str, dict[str, float]] = {}
    fx_now: dict[str, Decimal] = {}
    for s in symbols:
        try:
            closes[s] = _close_map(market, s, yahoo_range)
            quote = market.get_quote(s)
            fx_now[s] = market.get_fx_rate(quote.currency, portfolio_currency)
        except MarketDataError:
            closes[s] = {}
            fx_now[s] = Decimal("1")

    txns = sorted(txns, key=lambda t: t.executed_at.isoformat())
    points = []
    txn_idx = 0
    cash = starting_balance
    qty: dict[str, Decimal] = {s: Decimal("0") for s in symbols}
    last_close: dict[str, float] = {}
    for day in days:
        day_end = f"{day}T23:59:59"
        while txn_idx < len(txns):
            t = txns[txn_idx]
            if t.executed_at.isoformat() > day_end:
                break
            if t.kind == TransactionKind.SPLIT:
                qty[t.symbol] += t.quantity
            elif t.kind == TransactionKind.DIVIDEND:
                cash += t.amount
            else:
                if t.side == OrderSide.BUY:
                    cash -= t.amount
                    qty[t.symbol] += t.quantity
                else:
                    cash += t.amount
                    qty[t.symbol] -= t.quantity
            txn_idx += 1
        position_value = Decimal("0")
        for s in symbols:
            if qty[s] <= 0:
                continue
            close = closes[s].get(day)
            if close is None:
                close = last_close.get(s)
                if close is None:
                    # position predates available history; use earliest bar
                    close = next(iter(closes[s].values()), None)
            if close is None:
                continue
            last_close[s] = close
            position_value += qty[s] * Decimal(str(close)) * fx_now[s]
        total = float(cash + position_value)
        points.append({"date": day, "value": round(total, 2),
                       "benchmark_close": bench_closes[day]})
    return points


def value_history(
    session: Session,
    portfolio: Portfolio,
    market: MarketDataService,
    range_: str = "1Y",
    benchmark: str = "SPY",
) -> dict[str, Any]:
    """Daily (trading-day) series of total portfolio value, plus the
    benchmark's closes for the same dates."""
    txns = session.scalars(
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.executed_at)
    ).all()
    points = replay_series(
        list(txns), portfolio.starting_balance, market, range_, benchmark,
        portfolio.currency,
    )
    return {
        "portfolio_id": portfolio.id,
        "range": range_.upper(),
        "currency": portfolio.currency,
        "benchmark": benchmark,
        "points": points,
    }


def _daily_returns(values: list[float]) -> list[float]:
    return [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]


def risk_metrics(points: list[dict[str, Any]]) -> dict[str, Any]:
    values = [p["value"] for p in points]
    bench = [p["benchmark_close"] for p in points]
    out: dict[str, Any] = {
        "volatility": None, "sharpe": None, "sortino": None,
        "beta": None, "max_drawdown": None,
    }
    returns = _daily_returns(values)
    if len(returns) < 5:
        return out
    mean_r = statistics.fmean(returns)
    std_r = statistics.pstdev(returns)
    out["volatility"] = round(std_r * math.sqrt(TRADING_DAYS) * 100, 2)  # % annualized
    if std_r > 0:
        out["sharpe"] = round(mean_r / std_r * math.sqrt(TRADING_DAYS), 2)
    downside = [r for r in returns if r < 0]
    if downside:
        dstd = math.sqrt(sum(r * r for r in downside) / len(returns))
        if dstd > 0:
            out["sortino"] = round(mean_r / dstd * math.sqrt(TRADING_DAYS), 2)
    bench_returns = _daily_returns(bench)
    n = min(len(returns), len(bench_returns))
    if n >= 5:
        r, b = returns[-n:], bench_returns[-n:]
        mb = statistics.fmean(b)
        var_b = sum((x - mb) ** 2 for x in b) / n
        if var_b > 0:
            mr = statistics.fmean(r)
            cov = sum((r[i] - mr) * (b[i] - mb) for i in range(n)) / n
            out["beta"] = round(cov / var_b, 2)
    peak, max_dd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            max_dd = min(max_dd, (v - peak) / peak)
    out["max_drawdown"] = round(max_dd * 100, 2)  # negative %
    return out


def trade_records(session: Session, portfolio: Portfolio) -> dict[str, Any]:
    """Best/worst, win rate, average return and holding period from a FIFO
    pairing of the trade log."""
    txns = session.scalars(
        select(Transaction)
        .where(
            Transaction.portfolio_id == portfolio.id,
            Transaction.kind == TransactionKind.TRADE,
        )
        .order_by(Transaction.executed_at)
    ).all()
    open_lots: dict[str, list[list]] = {}  # symbol -> [qty, unit_cost, date]
    realized: dict[str, Decimal] = {}
    wins = losses = closed_sells = 0
    holding_days: list[float] = []
    trip_returns: list[float] = []
    largest_gain: Transaction | None = None
    largest_loss: Transaction | None = None
    for t in txns:
        if t.side == OrderSide.BUY:
            unit = t.amount / t.quantity if t.quantity else Decimal("0")
            open_lots.setdefault(t.symbol, []).append([t.quantity, unit, t.executed_at])
        else:
            remaining = t.quantity
            unit_price = t.amount / t.quantity if t.quantity else Decimal("0")
            lots = open_lots.get(t.symbol, [])
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(lot[0], remaining)
                pnl = take * (unit_price - lot[1])
                realized[t.symbol] = realized.get(t.symbol, Decimal("0")) + pnl
                if lot[1] > 0:
                    trip_returns.append(float((unit_price - lot[1]) / lot[1]))
                held = (t.executed_at - lot[2]).total_seconds() / 86400
                holding_days.append(held)
                lot[0] -= take
                remaining -= take
                if lot[0] <= 0:
                    lots.pop(0)
            if t.realized_pnl is not None:
                closed_sells += 1
                if t.realized_pnl > 0:
                    wins += 1
                    if largest_gain is None or t.realized_pnl > largest_gain.realized_pnl:
                        largest_gain = t
                elif t.realized_pnl < 0:
                    losses += 1
                    if largest_loss is None or t.realized_pnl < largest_loss.realized_pnl:
                        largest_loss = t

    def txn_view(t: Transaction | None):
        if t is None:
            return None
        return {"symbol": t.symbol, "quantity": str(t.quantity),
                "realized_pnl": str(t.realized_pnl), "executed_at": t.executed_at.isoformat()}

    best = max(realized.items(), key=lambda kv: kv[1], default=None)
    worst = min(realized.items(), key=lambda kv: kv[1], default=None)
    closed = closed_sells
    return {
        "realized_by_symbol": {s: str(v.quantize(Decimal('0.01'))) for s, v in realized.items()},
        "best_symbol": {"symbol": best[0], "realized_pnl": str(best[1].quantize(Decimal('0.01')))} if best else None,
        "worst_symbol": {"symbol": worst[0], "realized_pnl": str(worst[1].quantize(Decimal('0.01')))} if worst else None,
        "largest_gain": txn_view(largest_gain),
        "largest_loss": txn_view(largest_loss),
        "win_rate": round(wins / closed * 100, 1) if closed else None,
        "closed_trades": closed,
        "avg_trip_return": round(statistics.fmean(trip_returns) * 100, 2) if trip_returns else None,
        "avg_holding_days": round(statistics.fmean(holding_days), 1) if holding_days else None,
    }


def diversification(portfolio_view: dict[str, Any]) -> dict[str, Any]:
    """Herfindahl-based concentration score over current position weights
    (0 = fully concentrated, 100 = perfectly spread incl. cash)."""
    total = Decimal(portfolio_view["total_value"])
    if total <= 0:
        return {"score": None, "weights": {}}
    weights = {"CASH": float(Decimal(portfolio_view["cash_balance"]) / total)}
    for h in portfolio_view["holdings"]:
        if h["market_value"] is not None:
            weights[h["symbol"]] = float(Decimal(h["market_value"]) / total)
    hhi = sum(w * w for w in weights.values())
    n = len(weights)
    score = 100.0 if n <= 1 else round((1 - (hhi - 1 / n) / (1 - 1 / n)) * 100, 1)
    return {"score": score, "weights": {k: round(v * 100, 2) for k, v in weights.items()}}
