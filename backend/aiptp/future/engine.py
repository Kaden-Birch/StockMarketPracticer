"""Future-mode engine (M11 note 11).

The one place in the platform that shows non-real prices — by design, and
loudly labeled. Each session starts at TODAY'S real quotes and walks
forward along a deterministic simulated path (geometric Brownian motion
whose drift and volatility are measured from the stock's real past year).
The same seed always produces the same future, so a session is a stable,
replayable practice world where a year passes in minutes.

Honesty rules: prices are marked simulated in every payload; calibration is
statistics, not prediction; future portfolios never touch live listings,
the watcher, leaderboards, or the mentor.
"""

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError, SymbolNotFound
from ..marketdata.service import MarketDataService
from ..storage.models import (
    FutureSession,
    OrderSide,
    OrderType,
    Portfolio,
)
from ..trading.engine import place_order

DISCLAIMER = ("SIMULATED prices — statistically shaped like each stock's real "
              "past year, but fiction. Nothing here predicts the real market.")

MAX_SYMBOLS = 12
MAX_STEP = 2600  # ~10 simulated years


class FutureError(Exception):
    pass


def _normal(seed: str, symbol: str, step: int) -> float:
    """Deterministic standard-normal draw via Box-Muller over two hash-derived
    uniforms — same (seed, symbol, step) always yields the same value."""
    h = hashlib.sha256(f"{seed}:{symbol}:{step}".encode()).digest()
    u1 = (int.from_bytes(h[:8], "big") + 1) / (2 ** 64 + 2)
    u2 = int.from_bytes(h[8:16], "big") / 2 ** 64
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def calibrate(market: MarketDataService, symbols: list[str]) -> dict:
    """Per-symbol (p0, mu, sigma) from the REAL last year of daily closes."""
    out = {}
    for symbol in symbols:
        bars = market.get_history(symbol, "1y", "1d").bars
        closes = [b.close for b in bars if b.close]
        if len(closes) < 60:
            raise FutureError(f"Not enough real history to calibrate {symbol}")
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        mu = sum(rets) / len(rets)
        sigma = math.sqrt(sum((r - mu) ** 2 for r in rets) / len(rets))
        out[symbol] = {"p0": closes[-1], "mu": mu, "sigma": max(sigma, 1e-4)}
    return out


_paths: dict[tuple[str, str], list[float]] = {}  # (session, symbol) -> log prices


def price_at(sess: FutureSession, symbol: str, step: int) -> Decimal:
    """Simulated price after `step` trading days. The walk is deterministic,
    so the per-session path is cached and extended lazily."""
    key = (sess.id, symbol)
    path = _paths.get(key)
    if path is None:
        cal = json.loads(sess.calibration)[symbol]
        path = [math.log(cal["p0"])]
        _paths[key] = path
    if step >= len(path):
        cal = json.loads(sess.calibration)[symbol]
        mu, sigma = cal["mu"], cal["sigma"]
        for i in range(len(path), step + 1):
            path.append(path[-1] + (mu - sigma * sigma / 2)
                        + sigma * _normal(sess.seed, symbol, i))
    return Decimal(str(math.exp(path[step]))).quantize(Decimal("0.0001"))


def virtual_date(sess: FutureSession, step: int | None = None) -> str:
    """Calendar date for a step: created_at plus step trading days (~7/5)."""
    created = sess.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    days = round((step if step is not None else sess.current_step) * 7 / 5)
    return (created + timedelta(days=days)).date().isoformat()


def create_session(db: Session, market: MarketDataService, username: str,
                   symbols: list[str], starting_cash: Decimal,
                   seed: str | None = None) -> FutureSession:
    symbols = [s.upper().strip() for s in symbols if s.strip()][:MAX_SYMBOLS]
    if len(symbols) < 1:
        raise FutureError("Pick at least one symbol")
    try:
        cal = calibrate(market, symbols)
    except SymbolNotFound as exc:
        raise FutureError(str(exc))
    portfolio = Portfolio(
        owner=username,
        name="Future mode game",
        description="Accelerated-time practice game on SIMULATED prices",
        starting_balance=starting_cash,
        cash_balance=starting_cash,
    )
    db.add(portfolio)
    db.flush()
    sess = FutureSession(
        username=username, portfolio_id=portfolio.id,
        seed=seed or hashlib.sha256(portfolio.id.encode()).hexdigest()[:16],
        symbols=json.dumps(symbols), calibration=json.dumps(cal),
        value_points=json.dumps([[0, str(starting_cash)]]),
    )
    db.add(sess)
    db.flush()
    # reuse the scenario exclusion marker: keeps future portfolios out of
    # live listings, the watcher, corporate actions, mentor, leaderboards
    portfolio.scenario_session_id = sess.id
    return sess


def valuation(db: Session, sess: FutureSession, step: int | None = None) -> Decimal:
    portfolio = db.get(Portfolio, sess.portfolio_id)
    step = sess.current_step if step is None else step
    total = portfolio.cash_balance
    symbols = set(json.loads(sess.symbols))
    for holding in portfolio.holdings:
        if holding.quantity > 0 and holding.symbol in symbols:
            total += holding.quantity * price_at(sess, holding.symbol, step)
    return total.quantize(Decimal("0.01"))


def trade(db: Session, sess: FutureSession, symbol: str, side: OrderSide,
          quantity: Decimal | None, notional: Decimal | None):
    symbol = symbol.upper()
    if symbol not in json.loads(sess.symbols):
        raise FutureError(f"{symbol} is not in this game's universe")
    price = price_at(sess, symbol, sess.current_step)
    portfolio = db.get(Portfolio, sess.portfolio_id)
    return place_order(
        db, portfolio, symbol=symbol, side=side, type_=OrderType.MARKET,
        quantity=quantity, notional=notional, current_price=price,
    )


def advance(db: Session, sess: FutureSession, days: int) -> None:
    days = max(1, min(days, 260))
    points = json.loads(sess.value_points)
    # sample the value curve at most weekly so long jumps stay light
    stride = 1 if days <= 30 else 5
    target = min(sess.current_step + days, MAX_STEP)
    step = sess.current_step
    while step < target:
        step = min(step + stride, target)
        points.append([step, str(valuation(db, sess, step))])
    sess.current_step = target
    sess.value_points = json.dumps(points)


def session_view(db: Session, sess: FutureSession) -> dict:
    symbols = json.loads(sess.symbols)
    portfolio = db.get(Portfolio, sess.portfolio_id)
    cal = json.loads(sess.calibration)
    quotes = {}
    for s in symbols:
        now_p = price_at(sess, s, sess.current_step)
        prev_p = price_at(sess, s, sess.current_step - 1) if sess.current_step > 0 else None
        quotes[s] = {"price": str(now_p),
                     "prev_close": str(prev_p) if prev_p is not None else None,
                     "start_price": str(cal[s]["p0"]), "simulated": True}
    value = valuation(db, sess)
    starting = portfolio.starting_balance
    holdings = [
        {"symbol": h.symbol, "quantity": str(h.quantity),
         "market_value": str((h.quantity * price_at(sess, h.symbol, sess.current_step)
                              ).quantize(Decimal("0.01")))}
        for h in portfolio.holdings if h.quantity > 0
    ]
    return {
        "id": sess.id,
        "simulated": True,
        "disclaimer": DISCLAIMER,
        "portfolio_id": sess.portfolio_id,
        "symbols": symbols,
        "seed": sess.seed,
        "step": sess.current_step,
        "virtual_date": virtual_date(sess),
        "years_elapsed": round(sess.current_step / 260, 2),
        "cash": str(portfolio.cash_balance),
        "value": str(value),
        "return_pct": str(((value - starting) / starting * 100).quantize(Decimal("0.01")))
        if starting else "0",
        "quotes": quotes,
        "holdings": holdings,
        "value_points": [
            {"step": p[0], "date": virtual_date(sess, p[0]), "value": p[1]}
            for p in json.loads(sess.value_points)
        ],
    }


def list_sessions(db: Session, username: str) -> list[FutureSession]:
    return list(db.scalars(select(FutureSession).where(
        FutureSession.username == username
    ).order_by(FutureSession.created_at.desc())))
