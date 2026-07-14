"""Scenario replay engine (roadmap 8.2).

Ground rules:
  * All prices are REAL daily closes fetched for the scenario window.
  * The virtual clock (`ScenarioSession.current_ts`) only moves forward and
    every API response is truncated to bars <= current_ts — the player never
    sees the future.
  * Trades go through the SAME place_order path as live trading, filled at
    the virtual day's close, on a real (flagged) Portfolio row — so the
    immutable transaction log and accounting invariants hold in 1999 exactly
    as they do today.
  * "AI opponents" are transparent deterministic strategies computed from
    the same bars (equal-weight buy & hold, monthly DCA into the benchmark,
    3-month momentum rotation) — labelled as simulations, not oracles.
"""

import json
from bisect import bisect_right
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import Bar, MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import (
    OrderSide,
    OrderType,
    Portfolio,
    ScenarioSession,
)
from ..trading.engine import TradingError, place_order
from .catalog import SCENARIOS, Scenario

DAY = 86400


class ScenarioError(Exception):
    pass


def scenario_bars(market: MarketDataService, scenario: Scenario) -> dict[str, list[Bar]]:
    """Window bars for the universe + benchmark. Cached indefinitely by the
    market service (closed historical windows are immutable)."""
    out: dict[str, list[Bar]] = {}
    for symbol in (*scenario.universe, scenario.benchmark):
        hist = market.get_history_window(symbol, scenario.start_ts, scenario.end_ts)
        if not hist.bars:
            raise MarketDataError(f"No historical data for {symbol} in window")
        out[symbol] = hist.bars
    return out


def close_at(bars: list[Bar], ts: int) -> Decimal | None:
    """Close of the last bar at or before ts (None before first listing)."""
    idx = bisect_right([b.ts for b in bars], ts) - 1
    if idx < 0:
        return None
    return Decimal(str(bars[idx].close))


def calendar(bars_by_symbol: dict[str, list[Bar]], benchmark: str) -> list[int]:
    """The scenario's trading calendar = the benchmark's bar timestamps."""
    return [b.ts for b in bars_by_symbol[benchmark]]


def create_session(
    db: Session, market: MarketDataService, scenario_id: str,
    username: str, display_name: str = "",
) -> ScenarioSession:
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise ScenarioError(f"Unknown scenario: {scenario_id}")
    bars = scenario_bars(market, scenario)  # validates real data exists
    cal = calendar(bars, scenario.benchmark)
    portfolio = Portfolio(
        owner=username,
        name=f"{scenario.name} replay",
        description=f"Historical scenario {scenario.period} — virtual clock, real data",
        starting_balance=Decimal(scenario.starting_cash),
        cash_balance=Decimal(scenario.starting_cash),
    )
    db.add(portfolio)
    db.flush()
    sess = ScenarioSession(
        scenario_id=scenario.id, username=username,
        display_name=display_name or username,
        portfolio_id=portfolio.id, current_ts=cal[0],
        value_points=json.dumps([[cal[0], scenario.starting_cash]]),
    )
    db.add(sess)
    db.flush()
    portfolio.scenario_session_id = sess.id
    return sess


def valuation(db: Session, sess: ScenarioSession,
              bars: dict[str, list[Bar]]) -> Decimal:
    portfolio = db.get(Portfolio, sess.portfolio_id)
    total = portfolio.cash_balance
    for holding in portfolio.holdings:
        if holding.quantity <= 0:
            continue
        price = close_at(bars.get(holding.symbol, []), sess.current_ts)
        if price is not None:
            total += holding.quantity * price
    return total.quantize(Decimal("0.01"))


def trade(
    db: Session, market: MarketDataService, sess: ScenarioSession,
    symbol: str, side: OrderSide, quantity: Decimal | None,
    notional: Decimal | None,
) -> tuple:
    """Market order at the virtual day's real close, through the normal
    trading engine."""
    scenario = SCENARIOS[sess.scenario_id]
    symbol = symbol.upper()
    if symbol not in scenario.universe:
        raise ScenarioError(
            f"{symbol} is outside this scenario's universe "
            f"({', '.join(scenario.universe)})")
    if sess.completed:
        raise ScenarioError("This scenario has ended — start a new replay")
    bars = scenario_bars(market, scenario)
    price = close_at(bars[symbol], sess.current_ts)
    if price is None:
        raise ScenarioError(f"{symbol} is not trading yet at this point in history")
    portfolio = db.get(Portfolio, sess.portfolio_id)
    return place_order(
        db, portfolio, symbol=symbol, side=side, type_=OrderType.MARKET,
        quantity=quantity, notional=notional, current_price=price,
    )


def advance(db: Session, market: MarketDataService, sess: ScenarioSession,
            days: int) -> dict:
    """Step the virtual clock forward `days` trading days, appending the
    player's value at each step."""
    if sess.completed:
        raise ScenarioError("Scenario already completed")
    scenario = SCENARIOS[sess.scenario_id]
    bars = scenario_bars(market, scenario)
    cal = calendar(bars, scenario.benchmark)
    idx = bisect_right(cal, sess.current_ts) - 1
    points = json.loads(sess.value_points)
    steps = max(1, min(days, len(cal)))
    for _ in range(steps):
        if idx >= len(cal) - 1:
            sess.completed = True
            break
        idx += 1
        sess.current_ts = cal[idx]
        points.append([sess.current_ts, str(valuation(db, sess, bars))])
    if idx >= len(cal) - 1:
        sess.completed = True
    sess.value_points = json.dumps(points)
    return session_view(db, market, sess)


# ------------------------------------------------- deterministic AI opponents

def ai_buy_hold(bars: dict[str, list[Bar]], scenario: Scenario,
                cal: list[int], upto_ts: int) -> list[list]:
    """Equal-weight the universe names listed on day 1; hold."""
    cash = Decimal(scenario.starting_cash)
    day0 = cal[0]
    listed = [s for s in scenario.universe if close_at(bars[s], day0) is not None]
    per = cash / len(listed) if listed else Decimal("0")
    qty = {s: per / close_at(bars[s], day0) for s in listed}
    series = []
    for ts in cal:
        if ts > upto_ts:
            break
        value = sum((qty[s] * (close_at(bars[s], ts) or Decimal("0"))
                     for s in listed), Decimal("0"))
        series.append([ts, str(value.quantize(Decimal("0.01")))])
    return series


def ai_dca(bars: dict[str, list[Bar]], scenario: Scenario,
           cal: list[int], upto_ts: int) -> list[list]:
    """Dollar-cost average 1/12 of starting cash into the benchmark at each
    new month until invested."""
    from datetime import datetime, timezone

    cash = Decimal(scenario.starting_cash)
    chunk = cash / 12
    qty = Decimal("0")
    last_month = None
    series = []
    for ts in cal:
        if ts > upto_ts:
            break
        month = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
        price = close_at(bars[scenario.benchmark], ts)
        if price and month != last_month and cash > 0:
            spend = min(chunk, cash)
            qty += spend / price
            cash -= spend
            last_month = month
        value = cash + qty * (price or Decimal("0"))
        series.append([ts, str(value.quantize(Decimal("0.01")))])
    return series


def ai_momentum(bars: dict[str, list[Bar]], scenario: Scenario,
                cal: list[int], upto_ts: int) -> list[list]:
    """Each new month, rotate into the top-3 universe names by trailing
    63-trading-day return (cash until enough history accrues in-window)."""
    from datetime import datetime, timezone

    cash = Decimal(scenario.starting_cash)
    qty: dict[str, Decimal] = {}
    last_month = None
    series = []
    for i, ts in enumerate(cal):
        if ts > upto_ts:
            break
        month = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
        if month != last_month and i >= 63:
            last_month = month
            back = cal[i - 63]
            scored = []
            for s in scenario.universe:
                now_p, then_p = close_at(bars[s], ts), close_at(bars[s], back)
                if now_p and then_p and then_p > 0:
                    scored.append((float(now_p / then_p), s))
            scored.sort(reverse=True)
            top = [s for _, s in scored[:3]]
            if top:
                # liquidate, then equal-weight the leaders at today's closes
                for s, q in qty.items():
                    price = close_at(bars[s], ts)
                    if price:
                        cash += q * price
                qty = {}
                per = cash / len(top)
                for s in top:
                    price = close_at(bars[s], ts)
                    if price:
                        qty[s] = per / price
                cash = Decimal("0")
        elif last_month is None:
            last_month = month if i >= 63 else None
        value = cash + sum((q * (close_at(bars[s], ts) or Decimal("0"))
                            for s, q in qty.items()), Decimal("0"))
        series.append([ts, str(value.quantize(Decimal("0.01")))])
    return series


AI_STRATEGIES = {
    "ai_buy_hold": ("AI: Buy & hold (equal weight)", ai_buy_hold),
    "ai_dca": ("AI: Monthly DCA into index", ai_dca),
    "ai_momentum": ("AI: 3-month momentum rotation", ai_momentum),
}


# ---------------------------------------------------------------- API views

def session_view(db: Session, market: MarketDataService,
                 sess: ScenarioSession) -> dict:
    scenario = SCENARIOS[sess.scenario_id]
    bars = scenario_bars(market, scenario)
    cal = calendar(bars, scenario.benchmark)
    idx = bisect_right(cal, sess.current_ts) - 1
    portfolio = db.get(Portfolio, sess.portfolio_id)
    value = valuation(db, sess, bars)
    starting = Decimal(scenario.starting_cash)
    quotes = {}
    for s in scenario.universe:
        p = close_at(bars[s], sess.current_ts)
        prev = close_at(bars[s], sess.current_ts - 1) if p is not None else None
        quotes[s] = {
            "price": str(p) if p is not None else None,
            "prev_close": str(prev) if prev is not None else None,
            "listed": p is not None,
        }
    holdings = [
        {"symbol": h.symbol, "quantity": str(h.quantity),
         "price": quotes.get(h.symbol, {}).get("price"),
         "market_value": str((h.quantity * close_at(bars[h.symbol], sess.current_ts)
                              ).quantize(Decimal("0.01")))
         if close_at(bars.get(h.symbol, []), sess.current_ts) else None}
        for h in portfolio.holdings if h.quantity > 0
    ]
    bench_now = close_at(bars[scenario.benchmark], sess.current_ts)
    bench_start = Decimal(str(bars[scenario.benchmark][0].close))
    from datetime import datetime, timezone

    return {
        "id": sess.id,
        "scenario": {"id": scenario.id, "name": scenario.name,
                     "period": scenario.period, "benchmark": scenario.benchmark,
                     "universe": list(scenario.universe),
                     "description": scenario.description},
        "portfolio_id": sess.portfolio_id,
        "display_name": sess.display_name,
        "virtual_date": datetime.fromtimestamp(
            sess.current_ts, tz=timezone.utc).date().isoformat(),
        "day": idx + 1,
        "total_days": len(cal),
        "completed": sess.completed,
        "cash": str(portfolio.cash_balance),
        "value": str(value),
        "return_pct": str(((value - starting) / starting * 100).quantize(Decimal("0.01"))),
        "market_return_pct": str(((bench_now - bench_start) / bench_start * 100
                                  ).quantize(Decimal("0.01"))) if bench_now else "0",
        "quotes": quotes,
        "holdings": holdings,
    }


def comparison(db: Session, market: MarketDataService,
               sess: ScenarioSession) -> dict:
    """User vs market vs AI strategies vs other players — all truncated at
    the player's virtual date (no future knowledge, roadmap 8.2)."""
    scenario = SCENARIOS[sess.scenario_id]
    bars = scenario_bars(market, scenario)
    cal = calendar(bars, scenario.benchmark)
    upto = sess.current_ts
    starting = Decimal(scenario.starting_cash)

    bench = bars[scenario.benchmark]
    b0 = Decimal(str(bench[0].close))
    market_series = [
        [b.ts, str((starting * Decimal(str(b.close)) / b0).quantize(Decimal("0.01")))]
        for b in bench if b.ts <= upto
    ]
    series = [
        {"id": "you", "name": f"You ({sess.display_name})",
         "points": json.loads(sess.value_points)},
        {"id": "market", "name": f"Market ({scenario.benchmark})",
         "points": market_series},
    ]
    for sid, (name, fn) in AI_STRATEGIES.items():
        series.append({"id": sid, "name": name,
                       "points": fn(bars, scenario, cal, upto)})

    others = db.scalars(
        select(ScenarioSession).where(
            ScenarioSession.scenario_id == sess.scenario_id,
            ScenarioSession.id != sess.id,
        )
    ).all()
    players = []
    for o in others:
        pts = json.loads(o.value_points)
        if not pts:
            continue
        last_value = Decimal(pts[-1][1])
        players.append({
            "display_name": o.display_name,
            "day": bisect_right(cal, o.current_ts),
            "value": str(last_value),
            "return_pct": str(((last_value - starting) / starting * 100
                               ).quantize(Decimal("0.01"))),
            "completed": o.completed,
        })
    players.sort(key=lambda p: -Decimal(p["return_pct"]))
    return {"series": series, "players": players}


def history_upto(market: MarketDataService, sess: ScenarioSession,
                 symbol: str) -> dict:
    """Chart data for one symbol, truncated at the virtual date."""
    scenario = SCENARIOS[sess.scenario_id]
    symbol = symbol.upper()
    if symbol not in scenario.universe and symbol != scenario.benchmark:
        raise ScenarioError("Symbol outside the scenario universe")
    bars = scenario_bars(market, scenario)[symbol]
    return {
        "symbol": symbol,
        "bars": [
            {"ts": b.ts, "open": b.open, "high": b.high, "low": b.low,
             "close": b.close}
            for b in bars if b.ts <= sess.current_ts
        ],
    }
