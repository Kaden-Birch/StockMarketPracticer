"""Leaderboards (roadmap 7.3). Strictly opt-in: only portfolios whose owner
flipped `public_on_leaderboard` appear. Six categories, computed from real
portfolio state and cached for a few minutes (the ranking math replays
transaction history, which is too heavy per request)."""

import json
import time
from decimal import Decimal
from threading import Lock
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.service import diversification, risk_metrics, value_history
from ..core.currentuser import current_username
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import (
    BacktestRun,
    BacktestStatus,
    GameMode,
    Portfolio,
    Strategy,
)
from .deps import get_db, get_market

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])

CATEGORIES = {
    "highest_return": "Highest return",
    "risk_adjusted": "Best risk-adjusted (Sharpe)",
    "diversification": "Best diversification",
    "beginner_improvement": "Best beginner improvement",
    "lowest_drawdown": "Lowest drawdown",
    "best_strategy": "Best strategy (backtested)",
}

CACHE_TTL = 300  # seconds (roadmap 7.3: ~5 minute refresh)
_cache: dict[str, Any] = {"at": 0.0, "data": None}
_cache_lock = Lock()


def _return_pct(view: dict) -> float | None:
    starting = Decimal(view["starting_balance"])
    if starting <= 0:
        return None
    return round(float((Decimal(view["total_value"]) - starting) / starting * 100), 2)


def _compute(session: Session, market: MarketDataService) -> dict[str, Any]:
    portfolios = session.scalars(
        select(Portfolio).where(Portfolio.public_on_leaderboard.is_(True))
    ).all()

    returns, sharpe, diverse, beginner, drawdown = [], [], [], [], []
    for p in portfolios:
        view = value_portfolio(p, market)
        ret = _return_pct(view)
        entry = {"portfolio": p.name, "owner": p.owner, "mode": p.mode.value}
        if ret is not None:
            returns.append({**entry, "score": ret, "label": f"{ret:+.2f}%"})
            if p.mode == GameMode.BEGINNER:
                beginner.append({**entry, "score": ret, "label": f"{ret:+.2f}%"})
        div = diversification(view).get("score")
        if div is not None:
            diverse.append({**entry, "score": div, "label": f"{div:.1f}/100"})
        try:
            risk = risk_metrics(value_history(session, p, market, "1Y")["points"])
        except MarketDataError:
            # History or benchmark unavailable — this portfolio simply
            # doesn't appear in the history-based categories.
            risk = {}
        if risk.get("sharpe") is not None:
            sharpe.append({**entry, "score": risk["sharpe"],
                           "label": f"Sharpe {risk['sharpe']}"})
        dd = risk.get("max_drawdown")
        if dd is not None:
            # Stored as a negative percentage; closest to zero wins.
            drawdown.append({**entry, "score": -abs(dd),
                             "label": f"{-abs(dd):.2f}% max drawdown"})

    # Best strategy: highest completed backtest return per strategy.
    strategies = []
    runs = session.scalars(select(BacktestRun).where(
        BacktestRun.status == BacktestStatus.DONE)).all()
    best_by_strategy: dict[str, float] = {}
    for run in runs:
        ret = json.loads(run.results or "{}").get("total_return_pct")
        if ret is None:
            continue
        prev = best_by_strategy.get(run.strategy_id)
        if prev is None or ret > prev:
            best_by_strategy[run.strategy_id] = ret
    for sid, ret in best_by_strategy.items():
        strategy = session.get(Strategy, sid)
        if strategy is not None:
            strategies.append({"portfolio": strategy.name, "owner": "",
                               "mode": "", "score": ret, "label": f"{ret:+.2f}%"})

    def ranked(rows: list[dict]) -> list[dict]:
        rows.sort(key=lambda r: -r["score"])
        return [{**r, "rank": i} for i, r in enumerate(rows[:25], 1)]

    return {
        "highest_return": ranked(returns),
        "risk_adjusted": ranked(sharpe),
        "diversification": ranked(diverse),
        "beginner_improvement": ranked(beginner),
        "lowest_drawdown": ranked(drawdown),
        "best_strategy": ranked(strategies),
    }


def _boards(session: Session, market: MarketDataService) -> dict[str, Any]:
    with _cache_lock:
        if _cache["data"] is not None and time.monotonic() - _cache["at"] < CACHE_TTL:
            return _cache["data"]
    data = _compute(session, market)
    with _cache_lock:
        _cache["data"] = data
        _cache["at"] = time.monotonic()
    return data


def invalidate_cache() -> None:
    with _cache_lock:
        _cache["data"] = None
        _cache["at"] = 0.0


@router.get("")
def all_leaderboards(
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    me = current_username()
    boards = _boards(session, market)
    return {
        "categories": [
            {"id": cid, "name": name,
             "entries": [{**e, "is_me": e["owner"] == me} for e in boards[cid]]}
            for cid, name in CATEGORIES.items()
        ],
    }


@router.get("/{category}")
def one_leaderboard(
    category: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    if category not in CATEGORIES:
        raise HTTPException(status_code=404, detail="Unknown leaderboard category")
    me = current_username()
    boards = _boards(session, market)
    return {"id": category, "name": CATEGORIES[category],
            "entries": [{**e, "is_me": e["owner"] == me} for e in boards[category]]}
