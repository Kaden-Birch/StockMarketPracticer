"""AI opponent decision engine (roadmap 9.1-9.7).

Deterministic: decisions come from real quotes and real history through the
profile's documented method — no randomness, no LLM. "Mistakes" at beginner
difficulty are deliberate, documented common errors chosen by a stable hash
(so runs are reproducible) and always explained (9.3). Every action —
including HOLD — is recorded with reason, data used, confidence, and
expected outcome (9.5). Trades execute through the normal place_order path
with origin=AI_AUTO, so AI trades stay permanently marked (PRD §17).
"""

import hashlib
import json
import logging
from datetime import timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError, Quote
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import (
    AiDecision,
    AiPlayer,
    Competition,
    CompetitionEntry,
    OrderSide,
    OrderType,
    Origin,
    Portfolio,
    Transaction,
    TransactionKind,
    utcnow,
)
from ..trading.engine import TradingError, place_order
from .profiles import DIFFICULTY_MODS, PROFILES, ProfileSpec, effective_traits

log = logging.getLogger(__name__)

AI_OWNER_PREFIX = "ai:"


def _hist_return(market: MarketDataService, symbol: str, range_: str) -> float | None:
    """Total return over the range from real bars; None when unavailable."""
    try:
        bars = market.get_history(symbol, range_, "1d").bars
    except MarketDataError:
        return None
    if len(bars) < 2 or not bars[0].close:
        return None
    return bars[-1].close / bars[0].close - 1


def _volatility(market: MarketDataService, symbol: str, range_: str) -> float | None:
    try:
        bars = market.get_history(symbol, range_, "1d").bars
    except MarketDataError:
        return None
    closes = [b.close for b in bars if b.close]
    if len(closes) < 10:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    return (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5


def _year_high(market: MarketDataService, symbol: str) -> float | None:
    try:
        bars = market.get_history(symbol, "1y", "1d").bars
    except MarketDataError:
        return None
    highs = [b.high or b.close for b in bars if b.close]
    return max(highs) if highs else None


def _stable_pick(seed: str, options: int) -> int:
    """Deterministic pseudo-choice: same seed -> same pick, every run."""
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16) % options


def select_targets(
    market: MarketDataService, spec: ProfileSpec, difficulty: str,
    quotes: dict[str, Quote],
) -> tuple[list[str], dict]:
    """The profile's documented selection method -> (symbols, data_used)."""
    mods = DIFFICULTY_MODS[difficulty]
    range_ = mods["history_range"]
    available = [s for s in spec.universe if s in quotes]
    data: dict = {"universe": available, "method": spec.method,
                  "history_range": range_}

    if spec.method == "equal_weight":
        picks = available[: spec.target_positions]
        data["selection"] = "first N of the curated universe (static)"
        return picks, data

    if spec.method in ("momentum", "growth"):
        scored = []
        for s in available:
            r = _hist_return(market, s, range_)
            if r is not None:
                scored.append((r, s))
        scored.sort(reverse=True)
        data["scores"] = {s: round(r * 100, 2) for r, s in scored}
        data["selection"] = f"top {spec.target_positions} by {range_} return"
        return [s for _, s in scored[: spec.target_positions]], data

    if spec.method == "value_proxy":
        scored = []
        for s in available:
            high = _year_high(market, s)
            price = float(quotes[s].price)
            if high and high > 0:
                discount = 1 - price / high  # deeper below 52w high = cheaper
                scored.append((discount, s))
        scored.sort(reverse=True)
        data["scores"] = {s: round(d * 100, 1) for d, s in scored}
        data["selection"] = (f"top {spec.target_positions} by discount to "
                             "52-week high (price-based value proxy)")
        return [s for _, s in scored[: spec.target_positions]], data

    if spec.method == "quant":
        scored = []
        for s in available:
            r = _hist_return(market, s, range_)
            v = _volatility(market, s, range_)
            if r is not None and v and v > 0:
                scored.append((r / v, s))
        scored.sort(reverse=True)
        data["scores"] = {s: round(x, 2) for x, s in scored}
        data["selection"] = f"top {spec.target_positions} by return/volatility"
        return [s for _, s in scored[: spec.target_positions]], data

    if spec.method == "market_timer":
        try:
            bars = market.get_history("SPY", "6mo", "1d").bars
        except MarketDataError:
            return [], data
        closes = [b.close for b in bars if b.close]
        if len(closes) < 20:
            return [], data
        trend = sum(closes[-100:]) / len(closes[-100:])
        price = float(quotes["SPY"].price) if "SPY" in quotes else closes[-1]
        data["spy_price"] = round(price, 2)
        data["spy_trend"] = round(trend, 2)
        if price >= trend:
            data["selection"] = "risk-ON: SPY above its trend average"
            return ["SPY"], data
        data["selection"] = "risk-OFF: SPY below its trend average -> cash"
        return [], data

    if spec.method == "chase":  # the Beginner Investor
        scored = []
        for s in available:
            q = quotes[s]
            if q.previous_close and q.previous_close > 0:
                day_move = float((q.price - q.previous_close) / q.previous_close)
                scored.append((day_move, s))
        scored.sort(reverse=True)
        data["scores"] = {s: round(m * 100, 2) for m, s in scored}
        data["selection"] = "chases today's biggest gainers (a classic mistake)"
        return [s for _, s in scored[: spec.target_positions]], data

    return [], data


def run_player_cycle(
    session: Session, market: MarketDataService, player: AiPlayer,
    max_trades: int = 3,
) -> list[AiDecision]:
    """One decision cycle for one AI player. Commits are the caller's job."""
    spec = PROFILES[player.profile]
    mods = DIFFICULTY_MODS[player.difficulty]
    traits = json.loads(player.traits) if player.traits else effective_traits(
        spec, player.difficulty)
    portfolio = session.get(Portfolio, player.portfolio_id)
    if portfolio is None:
        return []
    decisions: list[AiDecision] = []

    def record(action: str, symbol: str, reason: str, data: dict,
               confidence: int, expected: str, order_id: str | None = None) -> None:
        d = AiDecision(
            ai_player_id=player.id, action=action, symbol=symbol,
            reason=reason, data_used=json.dumps(data), confidence=confidence,
            expected_outcome=expected, executed_order_id=order_id,
        )
        session.add(d)
        decisions.append(d)

    try:
        quotes = market.get_quotes(list(spec.universe))
    except MarketDataError as exc:
        record("HOLD", "", f"Market data unavailable this cycle: {exc}",
               {}, 0, "Wait for data")
        player.last_cycle_at = utcnow()
        return decisions

    targets, data = select_targets(market, spec, player.difficulty, quotes)

    # ---- adaptive behavior (9.7): observe the competition and react ----
    if player.adaptive:
        targets, data = _adapt(session, market, player, portfolio, spec,
                               traits, targets, data, quotes)

    view = value_portfolio(portfolio, market)
    total = Decimal(view["total_value"])
    held = {h["symbol"]: Decimal(h["market_value"] or "0")
            for h in view["holdings"]}

    cash_floor = Decimal(str(spec.cash_floor))
    investable = total * (1 - cash_floor)
    per_position = (investable / len(targets)).quantize(Decimal("0.01")) if targets else Decimal("0")
    conf_base = int(40 + traits.get("confidence", 0.5) * 50)
    trades_done = 0

    # ---- deliberate, documented mistakes at low difficulty (9.3) ----
    mistake_budget = 1 if (mods["mistake_rate"] > 0 and _stable_pick(
        f"{player.id}:{len(decisions)}:{view['total_value']}", 100
    ) < mods["mistake_rate"] * 100) else 0

    # sell positions that are no longer targets
    for symbol, mv in held.items():
        if trades_done >= max_trades:
            break
        if symbol in targets or mv <= 0:
            continue
        if mistake_budget and spec.method != "chase":
            # the documented mistake: refuses to sell a loser ("gets attached")
            mistake_budget -= 1
            record("MISTAKE", symbol,
                   f"Kept {symbol} even though it no longer fits the strategy "
                   "— holding losers out of attachment is a classic mistake "
                   "(shown for learning; higher difficulties sell here).",
                   data, 30, "Likely continued drag on returns")
            continue
        try:
            order, txn = place_order(
                session, portfolio, symbol=symbol, side=OrderSide.SELL,
                type_=OrderType.MARKET, notional=None,
                quantity=session_holding_qty(session, portfolio, symbol),
                current_price=quotes[symbol].price if symbol in quotes else None,
                origin=Origin.AI_AUTO,
            )
            trades_done += 1
            record("SELL", symbol,
                   f"{symbol} dropped out of the target set "
                   f"({data.get('selection', spec.method)}).",
                   data, conf_base,
                   "Redeploy into higher-ranked names", order.id)
        except (TradingError, MarketDataError) as exc:
            record("HOLD", symbol, f"Wanted to sell {symbol} but could not: {exc}",
                   data, 20, "Retry next cycle")

    # buy / top up targets
    for symbol in targets:
        if trades_done >= max_trades:
            break
        current = held.get(symbol, Decimal("0"))
        gap = per_position - current
        drift = float(gap / per_position) if per_position > 0 else 0
        if per_position <= 0 or drift < mods["rebalance_drift"]:
            continue
        spend = min(gap, portfolio.cash_balance - total * cash_floor)
        if spend < Decimal("50"):
            continue
        if mistake_budget and spec.method == "chase":
            spend = min(portfolio.cash_balance, per_position * 2)  # overconcentrates
        try:
            order, txn = place_order(
                session, portfolio, symbol=symbol, side=OrderSide.BUY,
                type_=OrderType.MARKET, notional=spend.quantize(Decimal("0.01")),
                quantity=None,
                current_price=quotes[symbol].price if symbol in quotes else None,
                origin=Origin.AI_AUTO,
            )
            trades_done += 1
            reason = (f"{symbol} ranks in the target set: "
                      f"{data.get('selection', spec.method)}.")
            expected = "Track the strategy's target allocation"
            if spec.id == "beginner":
                reason = (f"Bought {symbol} because it's going up today — "
                          "chasing gainers is a classic beginner mistake "
                          "(I'm showing you what NOT to do).")
                expected = "Often buys the top — watch what happens"
            record("BUY", symbol, reason, data, conf_base, expected, order.id)
        except (TradingError, MarketDataError) as exc:
            record("HOLD", symbol, f"Wanted to buy {symbol} but could not: {exc}",
                   data, 20, "Retry next cycle")

    if trades_done == 0 and not decisions:
        record("HOLD", "",
               f"Portfolio already tracks the target set within "
               f"{int(mods['rebalance_drift'] * 100)}% drift "
               f"({data.get('selection', spec.method)}).",
               data, conf_base, "Stay the course")
    player.last_cycle_at = utcnow()
    return decisions


def session_holding_qty(session: Session, portfolio: Portfolio,
                        symbol: str) -> Decimal | None:
    from ..storage.models import Holding

    h = session.scalar(select(Holding).where(
        Holding.portfolio_id == portfolio.id, Holding.symbol == symbol))
    return h.quantity if h else None


def _adapt(session, market, player, portfolio, spec, traits, targets, data,
           quotes):
    """Adaptive AI (9.7): reads real standings + the humans' portfolios and
    shifts strategy. Everything observed lands in data_used."""
    adaptability = traits.get("adaptability", 0.5)
    entries = session.scalars(select(CompetitionEntry).where(
        CompetitionEntry.competition_id == player.competition_id)).all()
    my_return = None
    best: tuple[float, Portfolio | None] = (-999.0, None)
    for e in entries:
        p = session.get(Portfolio, e.portfolio_id)
        if p is None:
            continue
        try:
            v = value_portfolio(p, market)
        except MarketDataError:
            continue
        starting = Decimal(v["starting_balance"])
        ret = float((Decimal(v["total_value"]) - starting) / starting) if starting else 0.0
        if p.id == portfolio.id:
            my_return = ret
        elif ret > best[0]:
            best = (ret, p)
    if my_return is None or best[1] is None:
        return targets, data
    gap = best[0] - my_return
    data["adaptive"] = {"my_return_pct": round(my_return * 100, 2),
                        "leader_return_pct": round(best[0] * 100, 2)}
    if gap > 0.02 * (1.1 - adaptability):  # trailing -> borrow the leader's best idea
        leader_holdings = sorted(
            ((h.quantity, h.symbol) for h in best[1].holdings if h.quantity > 0),
            reverse=True)
        if leader_holdings:
            borrowed = leader_holdings[0][1]
            if borrowed not in targets:
                if borrowed not in quotes:  # outside this AI's universe
                    try:
                        quotes.update(market.get_quotes([borrowed]))
                    except MarketDataError:
                        return targets, data
                targets = targets[: max(1, len(targets) - 1)] + [borrowed]
                data["adaptive"]["borrowed_idea"] = borrowed
                data["selection"] = (data.get("selection", "") +
                                     f" + adapted: added leader's top holding {borrowed}")
    elif gap < -0.02:  # leading -> protect it
        if len(targets) > 1:
            targets = targets[:-1]
            data["adaptive"]["derisked"] = True
            data["selection"] = (data.get("selection", "") +
                                 " + adapted: leading, dropped weakest name to de-risk")
    return targets, data


def run_ai_cycle(session_factory, market: MarketDataService, bus=None) -> int:
    """Scheduler job: one decision cycle for every AI player in an active
    competition. Patience gates cadence: impatient profiles act every cycle,
    patient ones sit out most of them."""
    acted = 0
    with session_factory() as session:
        players = session.scalars(select(AiPlayer)).all()
        for player in players:
            comp = session.get(Competition, player.competition_id)
            if comp is None:
                continue
            if comp.ends_at is not None:
                ends = comp.ends_at
                if ends.tzinfo is None:
                    ends = ends.replace(tzinfo=timezone.utc)
                if ends < utcnow():
                    continue
            traits = json.loads(player.traits) if player.traits else {}
            patience = traits.get("patience", 0.5)
            if player.last_cycle_at is not None:
                last = player.last_cycle_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                min_gap_minutes = 15 + patience * 240  # 15min .. ~4h
                if (utcnow() - last).total_seconds() < min_gap_minutes * 60:
                    continue
            try:
                run_player_cycle(session, market, player)
                session.commit()
                acted += 1
            except Exception:  # noqa: BLE001 — one AI must not break the cycle
                session.rollback()
                log.exception("AI player %s cycle failed", player.display_name)
    return acted


# --------------------------------------------------- post-game analysis (9.6)

def post_game_analysis(session: Session, market: MarketDataService,
                       competition: Competition, username: str) -> dict:
    """Deterministic report: why you won/lost, what worked, what mistakes
    occurred — computed from the real portfolios, never guessed."""
    entries = session.scalars(select(CompetitionEntry).where(
        CompetitionEntry.competition_id == competition.id)).all()
    rows = []
    for e in entries:
        p = session.get(Portfolio, e.portfolio_id)
        if p is None:
            continue
        try:
            view = value_portfolio(p, market)
        except MarketDataError:
            continue
        starting = Decimal(view["starting_balance"])
        ret = float((Decimal(view["total_value"]) - starting) / starting * 100) if starting else 0.0
        txns = session.scalars(select(Transaction).where(
            Transaction.portfolio_id == p.id,
            Transaction.kind == TransactionKind.TRADE)).all()
        sells = [t for t in txns if t.realized_pnl is not None]
        wins = [t for t in sells if t.realized_pnl > 0]
        from ..analytics.service import diversification

        rows.append({
            "name": e.display_name,
            "is_you": e.username == username,
            "is_ai": p.owner.startswith(AI_OWNER_PREFIX),
            "return_pct": round(ret, 2),
            "trades": len(txns),
            "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else None,
            "diversification": diversification(view).get("score"),
            "cash_pct": round(float(Decimal(view["cash_balance"]) /
                                    Decimal(view["total_value"]) * 100), 1)
            if Decimal(view["total_value"]) > 0 else None,
        })
    rows.sort(key=lambda r: -r["return_pct"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    me = next((r for r in rows if r["is_you"]), None)
    findings: list[str] = []
    if me is not None and rows:
        winner = rows[0]
        if me["rank"] == 1:
            findings.append(f"You won with {me['return_pct']}% — "
                            f"{me['return_pct'] - rows[1]['return_pct']:.2f} points "
                            "ahead of the runner-up." if len(rows) > 1 else
                            "You won — though with no rivals it was a solo race.")
        else:
            findings.append(
                f"{winner['name']} won with {winner['return_pct']}% vs your "
                f"{me['return_pct']}%.")
            if winner["trades"] < me["trades"]:
                findings.append(
                    f"The winner traded less than you ({winner['trades']} vs "
                    f"{me['trades']} trades) — activity was not rewarded here.")
            if (winner.get("diversification") or 0) > (me.get("diversification") or 0) + 10:
                findings.append(
                    "The winner was meaningfully more diversified "
                    f"({winner['diversification']} vs {me['diversification']}).")
            if (me.get("cash_pct") or 0) > 40:
                findings.append(
                    f"You held {me['cash_pct']}% in cash — uninvested money "
                    "can't compound.")
        if me.get("win_rate") is not None and me["win_rate"] < 50 and me["trades"] >= 4:
            findings.append(f"Your closed-trade win rate was {me['win_rate']}% — "
                            "review the entries that went straight down.")
        ai_beaten = [r["name"] for r in rows if r["is_ai"] and r["rank"] > me["rank"]]
        ai_ahead = [r["name"] for r in rows if r["is_ai"] and r["rank"] < me["rank"]]
        if ai_beaten:
            findings.append("AI opponents you beat: " + ", ".join(ai_beaten) + ".")
        if ai_ahead:
            findings.append("AI opponents ahead of you: " + ", ".join(ai_ahead) +
                            " — open their decision logs to see exactly why.")
    return {"standings": rows, "findings": findings}
