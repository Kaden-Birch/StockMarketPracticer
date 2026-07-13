"""Automation rule engine: evaluates enabled rules against fresh market/
portfolio state and executes their actions with safety rails (edge
triggering, cooldowns, daily caps, full fire log)."""

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analytics.indicators import compute_indicator
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import (
    AutomationRule,
    Notification,
    OrderSide,
    OrderType,
    Origin,
    PercentOf,
    Portfolio,
    RuleActionType,
    RuleFire,
    Transaction,
    TransactionKind,
)
from ..trading.engine import TradingError, place_order
from ..trading.rebalance import execute_rebalance, plan_rebalance
from . import conditions

log = logging.getLogger(__name__)


def _recent_dividends(session: Session, portfolio_id: str) -> dict[str, datetime]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = session.scalars(
        select(Transaction).where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.kind == TransactionKind.DIVIDEND,
            Transaction.executed_at >= cutoff,
        )
    ).all()
    out: dict[str, datetime] = {}
    for t in rows:
        ts = t.executed_at if t.executed_at.tzinfo else t.executed_at.replace(tzinfo=timezone.utc)
        if t.symbol not in out or ts > out[t.symbol]:
            out[t.symbol] = ts
    return out


def _within_caps(session: Session, rule: AutomationRule, now: datetime) -> bool:
    if rule.last_fired_at is not None:
        last = rule.last_fired_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now - last).total_seconds() < rule.cooldown_seconds:
            return False
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fired_today = session.scalar(
        select(func.count(RuleFire.id)).where(
            RuleFire.rule_id == rule.id, RuleFire.fired_at >= day_start
        )
    )
    return (fired_today or 0) < rule.max_fires_per_day


def _execute_action(
    session: Session,
    rule: AutomationRule,
    portfolio: Portfolio,
    market: MarketDataService,
) -> tuple[str, str]:
    """Returns (result, detail)."""
    params = json.loads(rule.action_params or "{}")
    if rule.action_type == RuleActionType.NOTIFY:
        return "NOTIFIED", params.get("message", f"Rule '{rule.name}' condition met")

    if rule.action_type == RuleActionType.REBALANCE:
        targets = {k: Decimal(str(v)) for k, v in (params.get("targets") or {}).items()}
        plan = plan_rebalance(portfolio, targets, market)
        results = execute_rebalance(session, portfolio, plan, market, origin=Origin.AUTOMATION)
        return "EXECUTED", f"Rebalanced: {json.dumps(results)}"

    symbol = params["symbol"].upper()
    quote = market.get_quote(symbol)
    fx = market.get_fx_rate(quote.currency, portfolio.currency)
    quantity = Decimal(str(params["quantity"])) if params.get("quantity") else None
    notional = Decimal(str(params["notional"])) if params.get("notional") else None
    percent = Decimal(str(params["percent"])) if params.get("percent") else None
    side = OrderSide.BUY if rule.action_type == RuleActionType.BUY else OrderSide.SELL
    if percent is not None:
        if side == OrderSide.SELL:
            holding = next((h for h in portfolio.holdings if h.symbol == symbol), None)
            held = holding.quantity if holding else Decimal("0")
            quantity = (held * percent / 100).quantize(Decimal("0.000001"))
            notional = None
            if quantity <= 0:
                return "REJECTED", f"No {symbol} position to sell"
        else:
            notional = (portfolio.cash_balance * percent / 100).quantize(Decimal("0.01"))
            quantity = None
    order, txn = place_order(
        session,
        portfolio,
        symbol=symbol,
        side=side,
        type_=OrderType.MARKET,
        quantity=quantity,
        notional=notional,
        origin=Origin.AUTOMATION,
        current_price=quote.price,
        fx_rate=fx,
        quote_currency=quote.currency,
    )
    if txn is None:
        return "REJECTED", order.reject_reason or "Order did not fill"
    return "EXECUTED", (
        f"{side.value} {txn.quantity} {symbol} @ {txn.price} {quote.currency}"
    )


def run_rules(
    session: Session,
    market: MarketDataService,
    bus=None,
    prices: dict[str, Decimal] | None = None,
    previous_closes: dict[str, Decimal] | None = None,
    scheduled_only: bool = False,
) -> int:
    """Evaluate enabled rules. When `prices` is given (watch cycle), only
    rules referencing those symbols or no symbols are considered; when
    scheduled_only, only rules containing a schedule condition run (the
    1-minute tick)."""
    now = datetime.now(timezone.utc)
    rules = session.scalars(
        select(AutomationRule).where(AutomationRule.enabled == True)  # noqa: E712
    ).all()
    fired = 0
    indicator_cache: dict[tuple[str, str, int], float | None] = {}

    def indicator_fn(symbol: str, name: str, period: int) -> float | None:
        key = (symbol, name.upper(), period)
        if key not in indicator_cache:
            try:
                indicator_cache[key] = compute_indicator(market, symbol, name, period)
            except (MarketDataError, ValueError) as exc:
                log.warning("Indicator %s(%s,%s) failed: %s", name, symbol, period, exc)
                indicator_cache[key] = None
        return indicator_cache[key]

    portfolio_views: dict[str, dict] = {}
    for rule in rules:
        try:
            trigger = json.loads(rule.trigger)
        except json.JSONDecodeError:
            continue
        is_scheduled = conditions.has_schedule(trigger)
        if scheduled_only and not is_scheduled:
            continue
        symbols = conditions.referenced_symbols(trigger)
        if not scheduled_only and prices is not None:
            if is_scheduled:
                continue  # schedule rules run on the minute tick only
            if symbols and not (symbols & set(prices)):
                continue

        portfolio = session.get(Portfolio, rule.portfolio_id)
        if portfolio is None:
            continue
        if portfolio.id not in portfolio_views:
            try:
                portfolio_views[portfolio.id] = value_portfolio(portfolio, market)
            except MarketDataError as exc:
                log.warning("Valuation failed for rule %s: %s", rule.name, exc)
                continue

        eval_prices = dict(prices or {})
        eval_prev = dict(previous_closes or {})
        missing = {s for s in symbols if s not in eval_prices}
        if missing:
            try:
                quotes = market.get_quotes(sorted(missing))
                for s, q in quotes.items():
                    eval_prices[s] = q.price
                    if q.previous_close:
                        eval_prev[s] = q.previous_close
            except MarketDataError as exc:
                log.warning("Quote fetch failed for rule %s: %s", rule.name, exc)
                continue

        ctx = conditions.RuleContext(
            prices=eval_prices,
            previous_closes=eval_prev,
            portfolio_view=portfolio_views[portfolio.id],
            indicator_fn=indicator_fn,
            recent_dividends=_recent_dividends(session, portfolio.id),
            now=now,
        )
        try:
            condition_met = conditions.evaluate(trigger, ctx)
        except Exception as exc:  # malformed rule must never kill the cycle
            log.error("Rule %s evaluation error: %s", rule.name, exc)
            continue

        if not condition_met:
            if not rule.armed:
                rule.armed = True  # condition released — re-arm edge trigger
            continue
        # Edge triggering: fire once per condition transition, not every tick
        # the condition holds. Schedule rules are inherently edge-like (their
        # minute passes) so they skip arming.
        if not is_scheduled:
            if not rule.armed:
                continue
            rule.armed = False
        if not _within_caps(session, rule, now):
            continue

        try:
            result, detail = _execute_action(session, rule, portfolio, market)
        except (TradingError, MarketDataError) as exc:
            result, detail = "REJECTED", str(exc)
        except Exception as exc:
            log.exception("Rule %s action error", rule.name)
            result, detail = "ERROR", str(exc)

        rule.last_fired_at = now
        rule.fire_count += 1
        session.add(RuleFire(rule_id=rule.id, result=result, detail=detail))
        if bus is not None:
            bus.publish(
                "rule_fired",
                {"rule_id": rule.id, "rule_name": rule.name, "result": result,
                 "detail": detail, "portfolio_id": portfolio.id},
                session=session,
            )
        fired += 1
        # refresh cached view after a trade so later rules see updated state
        if result == "EXECUTED":
            try:
                portfolio_views[portfolio.id] = value_portfolio(portfolio, market)
            except MarketDataError:
                portfolio_views.pop(portfolio.id, None)
    return fired


def run_scheduled_rules_cycle(session_factory, market: MarketDataService, bus=None) -> None:
    with session_factory() as session:
        count = run_rules(session, market, bus, scheduled_only=True)
        session.commit()
        if count:
            log.info("Scheduled rules fired: %d", count)
