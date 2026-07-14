"""AI competitors API (roadmap 9.1-9.8), mounted by the ai_competitors
module. AI players join regular competitions, so human/AI/mixed games (9.1)
fall out of the existing standings for free."""

import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..aicomp import engine as ai_engine
from ..aicomp.profiles import (
    DIFFICULTIES,
    PROFILES,
    effective_traits,
    profiles_view,
)
from ..core.currentuser import current_username, is_admin
from ..marketdata.service import MarketDataService
from ..security.audit import audit
from ..storage.models import (
    AiDecision,
    AiPlayer,
    Competition,
    CompetitionEntry,
    CompetitionKind,
    Portfolio,
)
from .deps import get_db, get_market

router = APIRouter(prefix="/ai-players", tags=["ai-competitors"])
comp_router = APIRouter(prefix="/competitions/{competition_id}",
                        tags=["ai-competitors"])
tournament_router = APIRouter(prefix="/tournaments", tags=["ai-competitors"])


class AiPlayerCreate(BaseModel):
    profile: str
    difficulty: str = "intermediate"
    adaptive: bool = False


TOURNAMENTS = {
    "beat_the_market": {
        "name": "Beat the Market",
        "description": "Just you against a passive index fund. Most "
                       "professionals lose this one.",
        "players": [("index", "expert", False)],
    },
    "growth_vs_value": {
        "name": "Growth vs Value",
        "description": "The oldest argument in investing, settled with real "
                       "prices: a growth AI, a value AI, and you.",
        "players": [("growth", "advanced", False), ("value", "advanced", False)],
    },
    "human_vs_ai": {
        "name": "Human vs AI",
        "description": "The full roster: all eight AI investing philosophies "
                       "at once. Expert difficulty, adaptive.",
        "players": [(pid, "expert", True) for pid in
                    ("conservative", "growth", "value", "dividend",
                     "technical", "quant", "market_timer", "beginner")],
    },
}


def _competition_for(session: Session, competition_id: str) -> Competition:
    comp = session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    return comp


def _add_ai_player(session: Session, market: MarketDataService,
                   comp: Competition, profile_id: str, difficulty: str,
                   adaptive: bool) -> AiPlayer:
    spec = PROFILES.get(profile_id)
    if spec is None:
        raise HTTPException(status_code=422,
                            detail=f"profile must be one of {sorted(PROFILES)}")
    if difficulty not in DIFFICULTIES:
        raise HTTPException(status_code=422,
                            detail=f"difficulty must be one of {list(DIFFICULTIES)}")
    display = f"{spec.name} ({difficulty}) 🤖"
    portfolio = Portfolio(
        owner=f"{ai_engine.AI_OWNER_PREFIX}{profile_id}",
        name=f"{display} — {comp.name}",
        description=spec.philosophy,
        starting_balance=comp.starting_balance,
        cash_balance=comp.starting_balance,
    )
    session.add(portfolio)
    session.flush()
    player = AiPlayer(
        competition_id=comp.id, portfolio_id=portfolio.id, profile=profile_id,
        difficulty=difficulty, display_name=display,
        traits=json.dumps(effective_traits(spec, difficulty)), adaptive=adaptive,
    )
    session.add(player)
    session.flush()
    session.add(CompetitionEntry(
        competition_id=comp.id, portfolio_id=portfolio.id,
        username=f"{ai_engine.AI_OWNER_PREFIX}{player.id}", display_name=display,
    ))
    # First decision cycle runs immediately so the opponent starts investing.
    ai_engine.run_player_cycle(session, market, player)
    return player


@router.get("/profiles")
def list_profiles():
    return profiles_view()


@comp_router.post("/ai-players", status_code=201)
def add_ai_player(
    competition_id: str,
    body: AiPlayerCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    comp = _competition_for(session, competition_id)
    if comp.created_by != current_username() and not is_admin():
        raise HTTPException(status_code=403,
                            detail="Only the competition creator adds AI players")
    player = _add_ai_player(session, market, comp, body.profile,
                            body.difficulty, body.adaptive)
    audit(session, current_username(), "ai_player.added",
          f"{player.display_name} -> {comp.name}")
    session.commit()
    return _player_out(session, market, player)


def _player_out(session: Session, market: MarketDataService,
                player: AiPlayer) -> dict:
    from ..portfolio.service import value_portfolio

    spec = PROFILES[player.profile]
    out = {
        "id": player.id, "profile": player.profile,
        "name": player.display_name, "philosophy": spec.philosophy,
        "difficulty": player.difficulty, "adaptive": player.adaptive,
        "traits": json.loads(player.traits),
        "portfolio_id": player.portfolio_id,
        "last_cycle_at": player.last_cycle_at.isoformat()
        if player.last_cycle_at else None,
    }
    portfolio = session.get(Portfolio, player.portfolio_id)
    if portfolio is not None:
        try:
            view = value_portfolio(portfolio, market)
            starting = Decimal(view["starting_balance"])
            out["value"] = view["total_value"]
            out["return_pct"] = str(((Decimal(view["total_value"]) - starting)
                                     / starting * 100).quantize(Decimal("0.01")))
            out["holdings"] = [
                {"symbol": h["symbol"], "market_value": h["market_value"]}
                for h in view["holdings"]
            ]
        except Exception:  # noqa: BLE001 — market data outage must not 500 this
            out["value"] = None
    return out


@comp_router.get("/ai-players")
def list_ai_players(
    competition_id: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    _competition_for(session, competition_id)
    players = session.scalars(select(AiPlayer).where(
        AiPlayer.competition_id == competition_id)).all()
    return [_player_out(session, market, p) for p in players]


@router.get("/{player_id}/decisions")
def decision_log(player_id: str, limit: int = 50,
                 session: Session = Depends(get_db)):
    """Full transparency (9.5): decision, reason, data used, confidence,
    expected outcome — for every action including HOLD."""
    player = session.get(AiPlayer, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="AI player not found")
    rows = session.scalars(
        select(AiDecision).where(AiDecision.ai_player_id == player_id)
        .order_by(AiDecision.created_at.desc()).limit(min(limit, 200))
    ).all()
    return {
        "player": player.display_name,
        "decisions": [
            {"action": d.action, "symbol": d.symbol, "reason": d.reason,
             "data_used": json.loads(d.data_used), "confidence": d.confidence,
             "expected_outcome": d.expected_outcome,
             "executed_order_id": d.executed_order_id,
             "created_at": d.created_at.isoformat()}
            for d in rows
        ],
    }


@router.post("/{player_id}/cycle")
def force_cycle(
    player_id: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """Run one decision cycle now (the scheduler also runs them on a
    patience-gated cadence)."""
    player = session.get(AiPlayer, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="AI player not found")
    decisions = ai_engine.run_player_cycle(session, market, player)
    session.commit()
    return {"decisions": len(decisions)}


@comp_router.get("/analysis")
def competition_analysis(
    competition_id: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """Post-game analysis (9.6) — works mid-game too as a live debrief."""
    comp = _competition_for(session, competition_id)
    return ai_engine.post_game_analysis(session, market, comp,
                                        current_username())


@tournament_router.get("")
def list_tournaments():
    return [
        {"id": tid, "name": t["name"], "description": t["description"],
         "ai_players": [{"profile": p, "difficulty": d, "adaptive": a}
                        for p, d, a in t["players"]]}
        for tid, t in TOURNAMENTS.items()
    ]


class TournamentStart(BaseModel):
    template: str
    starting_balance: Decimal = Field(default=Decimal("100000"), gt=0)


@tournament_router.post("", status_code=201)
def start_tournament(
    body: TournamentStart,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """One click (9.8): a private competition pre-populated with AI players;
    the creator is auto-joined."""
    template = TOURNAMENTS.get(body.template)
    if template is None:
        raise HTTPException(status_code=422,
                            detail=f"template must be one of {sorted(TOURNAMENTS)}")
    import secrets

    user = current_username()
    comp = Competition(
        name=template["name"], description=template["description"],
        kind=CompetitionKind.PRIVATE, starting_balance=body.starting_balance,
        invite_code=secrets.token_hex(4), created_by=user,
    )
    session.add(comp)
    session.flush()
    my_portfolio = Portfolio(
        owner=user, name=f"{comp.name} entry",
        description=f"Tournament entry — {comp.name}",
        starting_balance=comp.starting_balance,
        cash_balance=comp.starting_balance,
    )
    session.add(my_portfolio)
    session.flush()
    session.add(CompetitionEntry(
        competition_id=comp.id, portfolio_id=my_portfolio.id,
        username=user, display_name=user,
    ))
    for profile_id, difficulty, adaptive in template["players"]:
        _add_ai_player(session, market, comp, profile_id, difficulty, adaptive)
    audit(session, user, "tournament.started", template["name"])
    session.commit()
    return {"competition_id": comp.id, "portfolio_id": my_portfolio.id,
            "invite_code": comp.invite_code,
            "ai_players": len(template["players"])}
