"""Games (M11 note 10): isolated spaces that group portfolios, plus the
dashboard net-worth history (note 9)."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.service import value_history
from ..core.currentuser import current_username
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import Game, Portfolio
from .deps import get_db, get_market

router = APIRouter(prefix="/games", tags=["games"])
networth_router = APIRouter(prefix="/networth", tags=["games"])


class GameCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


@router.get("")
def list_games(session: Session = Depends(get_db)):
    user = current_username()
    games = session.scalars(select(Game).where(
        Game.owner.in_([user, "local"])).order_by(Game.created_at)).all()
    counts: dict[str | None, int] = {}
    for p in session.scalars(select(Portfolio).where(
            Portfolio.owner.in_([user, "local"]),
            Portfolio.scenario_session_id.is_(None))):
        counts[p.game_id] = counts.get(p.game_id, 0) + 1
    return [
        {"id": g.id, "name": g.name, "description": g.description,
         "portfolios": counts.get(g.id, 0),
         "created_at": g.created_at.isoformat()}
        for g in games
    ] + ([{"id": None, "name": "Ungrouped", "description": "",
           "portfolios": counts.get(None, 0), "created_at": None}]
         if counts.get(None) else [])


@router.post("", status_code=201)
def create_game(body: GameCreate, session: Session = Depends(get_db)):
    game = Game(owner=current_username(), name=body.name,
                description=body.description)
    session.add(game)
    session.commit()
    return {"id": game.id, "name": game.name}


@router.delete("/{game_id}", status_code=204)
def delete_game(game_id: str, session: Session = Depends(get_db)):
    game = session.get(Game, game_id)
    if game is None or game.owner not in (current_username(), "local"):
        raise HTTPException(status_code=404, detail="Game not found")
    # portfolios survive — they just become ungrouped
    for p in session.scalars(select(Portfolio).where(Portfolio.game_id == game_id)):
        p.game_id = None
    session.delete(game)
    session.commit()


@networth_router.get("")
def networth_history(
    range: str = Query(default="1Y"),
    game_id: str = Query(default=""),
    inflation_pct: float = Query(default=0.0, ge=0, le=20),
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """Total invested capital + cash across your live portfolios, day by
    day, reconstructed from the transaction log and real prices. Optional
    inflation adjustment discounts by a stated assumed rate (a documented
    planning assumption, not real CPI data)."""
    user = current_username()
    query = select(Portfolio).where(
        Portfolio.owner.in_([user, "local"]),
        Portfolio.scenario_session_id.is_(None),
        ~Portfolio.owner.startswith("ai:"),
    )
    if game_id:
        query = query.where(Portfolio.game_id == game_id)
    portfolios = session.scalars(query).all()
    if not portfolios:
        return {"points": [], "portfolios": 0, "note": ""}

    combined: dict[str, dict] = {}
    errors: list[str] = []
    for p in portfolios:
        created = p.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        try:
            series = value_history(session, p, market, range)["points"]
        except MarketDataError as exc:
            errors.append(f"{p.name}: {exc}")
            continue
        for point in series:
            day = point["date"]
            # a portfolio contributes nothing before it existed
            if datetime.fromisoformat(day).replace(tzinfo=timezone.utc) < created.replace(
                    hour=0, minute=0, second=0, microsecond=0):
                continue
            row = combined.setdefault(day, {"date": day, "value": 0.0})
            row["value"] += point["value"]
    points = sorted(combined.values(), key=lambda r: r["date"])

    note = ("Value = cash + market value of every position, from your real "
            "transaction history and real daily prices.")
    if inflation_pct > 0 and points:
        start = datetime.fromisoformat(points[0]["date"])
        for row in points:
            years = (datetime.fromisoformat(row["date"]) - start).days / 365.25
            row["real_value"] = round(
                row["value"] / ((1 + inflation_pct / 100) ** years), 2)
        note += (f" Inflation-adjusted line assumes {inflation_pct}%/year — a "
                 "stated planning assumption, not measured CPI.")
    for row in points:
        row["value"] = round(row["value"], 2)
    return {"points": points, "portfolios": len(portfolios),
            "range": range.upper(), "note": note, "quote_errors": errors}
