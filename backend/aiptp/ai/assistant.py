"""AI Investment Assistant (PRD §16-§17).

Grounded, tool-using generation — never free-form price talk:
1. Deterministic code assembles a context pack of REAL data (portfolio,
   analytics, quotes, indicator values).
2. The model must answer in strict JSON, referencing only supplied data.
3. Output is validated: suggestions for symbols absent from the context
   pack are dropped; sizing is clamped to the portfolio's guardrails.
4. Everything is persisted with the frozen inputs_snapshot so every
   recommendation stays explainable forever.
"""

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analytics.indicators import compute_indicator
from ..analytics.service import diversification, trade_records
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import (
    OrderSide,
    OrderType,
    Origin,
    Portfolio,
    Recommendation,
    RecommendationAction,
    RecommendationStatus,
)
from ..trading.engine import TradingError, place_order

log = logging.getLogger(__name__)

DISCLAIMER = (
    "Educational simulation only. AI output is informational, may be wrong, "
    "and is not financial advice. You remain responsible for real-world "
    "investment decisions."
)

SYSTEM_PROMPT = """You are the investment assistant inside AIPTP, an educational paper-trading platform. You analyze ONLY the JSON context provided by the user message. Rules:
- Never invent prices, fundamentals, or news. Reference only data present in the context.
- Output STRICT JSON, nothing else, matching:
{"analysis": "<portfolio analysis referencing concrete numbers from the context — at most 5 sentences>",
 "suggestions": [{"action": "BUY"|"SELL"|"HOLD", "symbol": "<symbol from context>", "notional": <number or null>, "rationale": "<one sentence citing context numbers>", "confidence": <0.0-1.0>}]}
- 0 to 3 suggestions. Suggest HOLD with no notional when no action is warranted.
- Be concise; the entire response must be complete, valid JSON.
- Prefer diversification, risk management, and long-term thinking over speculation.
- This is a simulation for learning; still be conservative and explain reasoning."""


def build_context_pack(
    session: Session, portfolio: Portfolio, market: MarketDataService
) -> dict[str, Any]:
    """Deterministic assembly of the real data the model may reason over."""
    view = value_portfolio(portfolio, market)
    symbols = [h["symbol"] for h in view["holdings"]]
    indicators: dict[str, dict] = {}
    for s in symbols[:12]:
        entry = {}
        for name, period in (("RSI", 14), ("SMA", 50)):
            try:
                value = compute_indicator(market, s, name, period)
                if value is not None:
                    entry[f"{name}{period}"] = round(value, 2)
            except (MarketDataError, ValueError):
                continue
        if entry:
            indicators[s] = entry
    div = diversification(view)
    records = trade_records(session, portfolio)
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "currency": view["currency"],
        "total_value": view["total_value"],
        "cash_balance": view["cash_balance"],
        "unrealized_pnl": view["unrealized_pnl"],
        "lifetime_return": view["lifetime_return"],
        "holdings": [
            {"symbol": h["symbol"], "quantity": h["quantity"], "avg_cost": h["avg_cost"],
             "price": h["price"], "market_value": h["market_value"],
             "unrealized_pnl": h["unrealized_pnl"]}
            for h in view["holdings"]
        ],
        "allocation_pct": div["weights"],
        "diversification_score": div["score"],
        "indicators": indicators,
        "records": {k: records[k] for k in
                    ("win_rate", "closed_trades", "avg_holding_days", "avg_trip_return")},
        "guardrails": {
            "max_trade_notional": str(portfolio.ai_max_trade_notional),
            "note": "suggestions larger than max_trade_notional will be clamped",
        },
    }


def _extract_json(text: str) -> dict:
    """Small local models sometimes wrap JSON in prose/code fences, or run
    out of tokens mid-object — salvage what we can."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1:
        raise ValueError("Model did not return JSON")
    if end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    # Truncated output: salvage the analysis string; suggestions are lost.
    salvage = re.search(r'"analysis"\s*:\s*"((?:[^"\\]|\\.)*)', text)
    if salvage:
        return {"analysis": salvage.group(1).replace('\\"', '"'), "suggestions": []}
    raise ValueError("Model returned unparseable JSON")


def expected_impact(
    portfolio: Portfolio,
    view: dict,
    action: str,
    symbol: str,
    notional: Decimal | None,
) -> dict:
    """Deterministic pre-trade impact preview — computed by us, not the LLM."""
    if action == "HOLD" or notional is None:
        return {}
    total = Decimal(view["total_value"])
    cash = Decimal(view["cash_balance"])
    holding = next((h for h in view["holdings"] if h["symbol"] == symbol), None)
    position = Decimal(holding["market_value"]) if holding and holding["market_value"] else Decimal("0")
    delta = notional if action == "BUY" else -min(notional, position)
    new_cash = cash - delta
    new_position = position + delta
    return {
        "cash_before": str(cash), "cash_after": str(new_cash.quantize(Decimal('0.01'))),
        "position_value_before": str(position),
        "position_value_after": str(max(new_position, Decimal('0')).quantize(Decimal('0.01'))),
        "position_weight_after_pct": str((max(new_position, Decimal('0')) / total * 100).quantize(Decimal('0.1'))) if total else None,
    }


def analyze_portfolio(
    session: Session,
    portfolio: Portfolio,
    market: MarketDataService,
    runtime,
    model_id: str,
    bus=None,
) -> dict[str, Any]:
    """Run the assistant: build context, generate, validate, persist. Returns
    the analysis plus created recommendations. Auto-executes within
    guardrails when the portfolio opts in."""
    pack = build_context_pack(session, portfolio, market)
    raw = runtime.generate(SYSTEM_PROMPT, json.dumps(pack, indent=1), max_tokens=2000)
    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        log.warning("Model output was not valid JSON: %s", exc)
        parsed = {"analysis": raw.strip()[:2000], "suggestions": []}

    analysis = str(parsed.get("analysis", "")).strip()[:4000]
    if analysis.startswith("<") or not analysis:
        # model echoed the schema placeholder — don't present it as analysis
        analysis = "(The model did not produce a usable analysis this run — try again.)"
    known_symbols = {h["symbol"] for h in pack["holdings"]} | set(pack["indicators"])
    view = value_portfolio(portfolio, market)
    max_notional = portfolio.ai_max_trade_notional

    recommendations: list[Recommendation] = []
    dropped = 0
    for item in list(parsed.get("suggestions", []))[:3]:
        try:
            action = RecommendationAction(str(item.get("action", "")).upper())
        except ValueError:
            dropped += 1
            continue
        symbol = str(item.get("symbol", "")).upper().strip()
        if action != RecommendationAction.HOLD and symbol not in known_symbols:
            dropped += 1  # grounding rule: only symbols the model was shown
            continue
        notional = None
        if item.get("notional") is not None and action != RecommendationAction.HOLD:
            try:
                notional = Decimal(str(item["notional"])).quantize(Decimal("0.01"))
            except ArithmeticError:
                notional = None
            if notional is not None:
                if notional <= 0:
                    notional = None
                elif notional > max_notional:
                    notional = max_notional  # clamp to guardrail
        confidence = None
        try:
            c = Decimal(str(item.get("confidence")))
            if 0 <= c <= 1:
                confidence = c
        except (ArithmeticError, TypeError):
            pass
        rec = Recommendation(
            portfolio_id=portfolio.id,
            model_id=model_id,
            action=action,
            symbol=symbol,
            sizing=json.dumps({"notional": str(notional)} if notional else {}),
            rationale=str(item.get("rationale", ""))[:2000],
            confidence=confidence,
            analysis=analysis,
            inputs_snapshot=json.dumps(pack),
            expected_impact=json.dumps(
                expected_impact(portfolio, view, action.value, symbol, notional)
            ),
        )
        session.add(rec)
        recommendations.append(rec)
    session.flush()

    executed = []
    if portfolio.ai_auto_execute:
        for rec in recommendations:
            result = try_execute(session, portfolio, rec, market, auto=True)
            if result is not None:
                executed.append(result)

    if bus is not None:
        bus.publish(
            "ai_analysis",
            {"portfolio_id": portfolio.id, "model_id": model_id,
             "recommendations": len(recommendations)},
            session=session,
        )
    return {
        "model_id": model_id,
        "analysis": analysis,
        "disclaimer": DISCLAIMER,
        "recommendations": [rec_view(r) for r in recommendations],
        "dropped_ungrounded": dropped,
        "auto_executed": executed,
    }


def _ai_trades_today(session: Session, portfolio_id: str) -> int:
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.scalar(
            select(func.count(Recommendation.id)).where(
                Recommendation.portfolio_id == portfolio_id,
                Recommendation.status == RecommendationStatus.EXECUTED,
                Recommendation.decided_at >= day_start,
            )
        )
        or 0
    )


def try_execute(
    session: Session,
    portfolio: Portfolio,
    rec: Recommendation,
    market: MarketDataService,
    auto: bool,
) -> dict | None:
    """Execute a recommendation as a market order with origin AI_AUTO or
    AI_ASSISTED. Returns an outcome dict, or None for HOLD/no-sizing."""
    sizing = json.loads(rec.sizing or "{}")
    if rec.action == RecommendationAction.HOLD or not sizing.get("notional"):
        rec.status = RecommendationStatus.APPROVED
        rec.decided_at = datetime.now(timezone.utc)
        return None
    if auto and _ai_trades_today(session, portfolio.id) >= portfolio.ai_max_trades_per_day:
        return {"recommendation_id": rec.id, "status": "SKIPPED",
                "reason": "Daily AI trade cap reached"}
    notional = Decimal(sizing["notional"])
    try:
        quote = market.get_quote(rec.symbol)
        fx = market.get_fx_rate(quote.currency, portfolio.currency)
        if rec.action == RecommendationAction.BUY:
            order, txn = place_order(
                session, portfolio, symbol=rec.symbol, side=OrderSide.BUY,
                type_=OrderType.MARKET, notional=notional,
                origin=Origin.AI_AUTO if auto else Origin.AI_ASSISTED,
                current_price=quote.price, fx_rate=fx, quote_currency=quote.currency,
            )
        else:
            local_price = quote.price * fx
            holding = next((h for h in portfolio.holdings if h.symbol == rec.symbol), None)
            held = holding.quantity if holding else Decimal("0")
            qty = min((notional / local_price).quantize(Decimal("0.000001")), held)
            if qty <= 0:
                raise TradingError(f"No {rec.symbol} position to sell")
            order, txn = place_order(
                session, portfolio, symbol=rec.symbol, side=OrderSide.SELL,
                type_=OrderType.MARKET, quantity=qty,
                origin=Origin.AI_AUTO if auto else Origin.AI_ASSISTED,
                current_price=quote.price, fx_rate=fx, quote_currency=quote.currency,
            )
    except (TradingError, MarketDataError) as exc:
        rec.status = RecommendationStatus.REJECTED
        rec.decided_at = datetime.now(timezone.utc)
        return {"recommendation_id": rec.id, "status": "FAILED", "reason": str(exc)}
    rec.status = RecommendationStatus.EXECUTED
    rec.decided_at = datetime.now(timezone.utc)
    rec.executed_order_id = order.id
    return {"recommendation_id": rec.id, "status": "EXECUTED", "order_id": order.id,
            "quantity": str(txn.quantity), "price": str(txn.price)}


def rec_view(rec: Recommendation) -> dict:
    return {
        "id": rec.id,
        "portfolio_id": rec.portfolio_id,
        "model_id": rec.model_id,
        "action": rec.action.value,
        "symbol": rec.symbol,
        "sizing": json.loads(rec.sizing or "{}"),
        "rationale": rec.rationale,
        "confidence": str(rec.confidence) if rec.confidence is not None else None,
        "analysis": rec.analysis,
        "expected_impact": json.loads(rec.expected_impact or "{}"),
        "status": rec.status.value,
        "executed_order_id": rec.executed_order_id,
        "created_at": rec.created_at.isoformat(),
        "decided_at": rec.decided_at.isoformat() if rec.decided_at else None,
    }
