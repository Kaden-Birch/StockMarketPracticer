"""What-If simulator (PRD §21): hypothetical scenarios as transforms over
the immutable transaction log, replayed against real historical prices. The
actual portfolio is never touched.

Scenario approximations (documented): dividends of a substituted-away symbol
are dropped rather than re-derived; adopt-AI applies BUY recommendations
only (uncapped shorts make no sense in a long-only simulator); FX for
foreign symbols uses the current rate across the series (as in analytics).
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.service import RANGE_TO_YAHOO, _close_map, replay_series
from ..marketdata.service import MarketDataService
from ..storage.models import (
    OrderSide,
    Portfolio,
    Recommendation,
    RecommendationAction,
    Transaction,
    TransactionKind,
)


class WhatIfError(ValueError):
    pass


def _txn(kind, side, symbol, quantity, amount, executed_at):
    return SimpleNamespace(kind=kind, side=side, symbol=symbol,
                           quantity=quantity, amount=amount, executed_at=executed_at)


def _close_on(closes: dict[str, float], date_iso: str) -> float | None:
    """Close on the date, or the nearest earlier trading day."""
    if date_iso in closes:
        return closes[date_iso]
    earlier = [d for d in closes if d <= date_iso]
    if earlier:
        return closes[max(earlier)]
    later = sorted(d for d in closes if d > date_iso)
    return closes[later[0]] if later else None


def _actual_txns(session: Session, portfolio: Portfolio) -> list[Transaction]:
    return list(
        session.scalars(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio.id)
            .order_by(Transaction.executed_at)
        ).all()
    )


def build_hypothetical(
    session: Session,
    portfolio: Portfolio,
    market: MarketDataService,
    scenario: dict[str, Any],
    range_: str,
) -> tuple[list, str]:
    """Returns (hypothetical txn list, human description)."""
    kind = scenario.get("type")
    actual = _actual_txns(session, portfolio)
    yahoo_range = RANGE_TO_YAHOO.get(range_.upper(), "1y")

    if kind == "substitute":
        src = str(scenario.get("from_symbol", "")).upper()
        dst = str(scenario.get("to_symbol", "")).upper()
        if not src or not dst:
            raise WhatIfError("substitute requires from_symbol and to_symbol")
        closes = _close_map(market, dst, "max")
        if not closes:
            raise WhatIfError(f"No history for {dst}")
        out = []
        for t in actual:
            if t.symbol == src and t.kind == TransactionKind.TRADE:
                close = _close_on(closes, t.executed_at.date().isoformat())
                if close is None:
                    continue
                qty = (t.amount / Decimal(str(close))).quantize(Decimal("0.000001"))
                out.append(_txn(t.kind, t.side, dst, qty, t.amount, t.executed_at))
            elif t.symbol == src:
                continue  # drop dividends/splits of the substituted symbol
            else:
                out.append(t)
        return out, f"Every {src} trade made in {dst} instead"

    if kind == "never_sold":
        symbol = str(scenario.get("symbol", "")).upper()
        if not symbol:
            raise WhatIfError("never_sold requires a symbol")
        out = [
            t for t in actual
            if not (t.symbol == symbol and t.kind == TransactionKind.TRADE
                    and t.side == OrderSide.SELL)
        ]
        removed = len(actual) - len(out)
        if removed == 0:
            raise WhatIfError(f"No {symbol} sells to suppress")
        return out, f"Never sold {symbol} ({removed} sale(s) suppressed)"

    if kind == "adopt_ai":
        recs = session.scalars(
            select(Recommendation)
            .where(Recommendation.portfolio_id == portfolio.id)
            .order_by(Recommendation.created_at)
        ).all()
        out = list(actual)
        adopted = 0
        for rec in recs:
            sizing = json.loads(rec.sizing or "{}")
            if rec.action != RecommendationAction.BUY or not sizing.get("notional"):
                continue
            if rec.status.value == "EXECUTED":
                continue  # already reflected in the actual log
            notional = Decimal(sizing["notional"])
            closes = _close_map(market, rec.symbol, "max")
            close = _close_on(closes, rec.created_at.date().isoformat()) if closes else None
            if close is None:
                continue
            qty = (notional / Decimal(str(close))).quantize(Decimal("0.000001"))
            out.append(_txn(TransactionKind.TRADE, OrderSide.BUY, rec.symbol,
                            qty, notional, rec.created_at))
            adopted += 1
        if adopted == 0:
            raise WhatIfError("No unexecuted AI buy recommendations to adopt")
        return out, f"Adopted {adopted} unexecuted AI buy recommendation(s)"

    if kind == "monthly_dca":
        symbol = str(scenario.get("symbol", "")).upper()
        if not symbol:
            raise WhatIfError("monthly_dca requires a symbol")
        buys = [t for t in actual
                if t.symbol == symbol and t.kind == TransactionKind.TRADE
                and t.side == OrderSide.BUY]
        if not buys:
            raise WhatIfError(f"No {symbol} purchases to re-schedule")
        total = sum((t.amount for t in buys), Decimal("0"))
        first = min(t.executed_at for t in buys)
        if first.tzinfo is None:
            first = first.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        months = max(1, int((now - first).days // 30))
        chunk = (total / months).quantize(Decimal("0.01"))
        closes = _close_map(market, symbol, "max")
        out = [t for t in actual if t not in buys]
        scheduled = 0
        for k in range(months):
            when = first + timedelta(days=30 * k)
            close = _close_on(closes, when.date().isoformat()) if closes else None
            if close is None:
                continue
            qty = (chunk / Decimal(str(close))).quantize(Decimal("0.000001"))
            out.append(_txn(TransactionKind.TRADE, OrderSide.BUY, symbol, qty, chunk, when))
            scheduled += 1
        return out, (
            f"Re-scheduled {total} of {symbol} lump purchases as "
            f"{scheduled} monthly buys of {chunk}"
        )

    raise WhatIfError(
        "type must be one of: substitute, never_sold, adopt_ai, monthly_dca"
    )


def simulate(
    session: Session,
    portfolio: Portfolio,
    market: MarketDataService,
    scenario: dict[str, Any],
    range_: str = "1Y",
    benchmark: str = "SPY",
) -> dict[str, Any]:
    actual_txns = _actual_txns(session, portfolio)
    hypo_txns, description = build_hypothetical(session, portfolio, market, scenario, range_)

    actual_points = replay_series(
        actual_txns, portfolio.starting_balance, market, range_, benchmark, portfolio.currency
    )
    hypo_points = replay_series(
        hypo_txns, portfolio.starting_balance, market, range_, benchmark, portfolio.currency
    )
    actual_final = actual_points[-1]["value"] if actual_points else float(portfolio.starting_balance)
    hypo_final = hypo_points[-1]["value"] if hypo_points else float(portfolio.starting_balance)
    return {
        "portfolio_id": portfolio.id,
        "scenario": scenario,
        "description": description,
        "range": range_.upper(),
        "currency": portfolio.currency,
        "actual_final": actual_final,
        "hypothetical_final": hypo_final,
        "delta": round(hypo_final - actual_final, 2),
        "delta_pct": round((hypo_final - actual_final) / actual_final * 100, 2) if actual_final else None,
        "actual_points": actual_points,
        "hypothetical_points": hypo_points,
        "note": "Hypothetical replay against real historical prices; the actual portfolio is unchanged.",
    }
