"""Multiplayer: competitions (roadmap 7.1), cooperative portfolios with
trade proposals and voting (7.2), and investment clubs (7.4). Mounted by the
`multiplayer` module — everything here disappears cleanly when that module
is disabled."""

import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analytics.service import diversification, risk_metrics, value_history
from ..core.currentuser import current_username, is_admin
from ..core.events import EventBus
from ..marketdata.base import MarketDataError, SymbolNotFound
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..security.audit import audit
from ..storage.models import (
    Club,
    ClubMember,
    ClubMessage,
    Competition,
    CompetitionEntry,
    CompetitionKind,
    CompetitionScoring,
    MemberRole,
    OrderSide,
    OrderType,
    Portfolio,
    PortfolioMember,
    ProposalStatus,
    TradeProposal,
)
from ..trading.engine import TradingError, place_order
from .deps import get_bus, get_db, get_market, get_portfolio_or_404

competitions_router = APIRouter(prefix="/competitions", tags=["multiplayer"])
coop_router = APIRouter(prefix="/portfolios/{portfolio_id}", tags=["multiplayer"])
clubs_router = APIRouter(prefix="/clubs", tags=["multiplayer"])


def _invite_code() -> str:
    return secrets.token_hex(4)  # 8 chars


def _return_pct(view: dict) -> float | None:
    starting = Decimal(view["starting_balance"])
    if starting <= 0:
        return None
    return float((Decimal(view["total_value"]) - starting) / starting * 100)


# ---------------------------------------------------------------- competitions

class CompetitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    kind: CompetitionKind = CompetitionKind.PUBLIC
    scoring: CompetitionScoring = CompetitionScoring.RETURN
    starting_balance: Decimal = Field(default=Decimal("100000"), gt=0)
    ends_at: datetime | None = None


class CompetitionJoin(BaseModel):
    invite_code: str = ""
    display_name: str = Field(default="", max_length=80)


def _competition_out(c: Competition, entries: int, joined: bool) -> dict:
    return {
        "id": c.id, "name": c.name, "description": c.description,
        "kind": c.kind.value, "scoring": c.scoring.value,
        "starting_balance": str(c.starting_balance),
        "created_by": c.created_by, "entries": entries, "joined": joined,
        "ends_at": c.ends_at.isoformat() if c.ends_at else None,
        "created_at": c.created_at.isoformat(),
    }


@competitions_router.post("", status_code=201)
def create_competition(body: CompetitionCreate, session: Session = Depends(get_db)):
    comp = Competition(
        name=body.name, description=body.description, kind=body.kind,
        scoring=body.scoring, starting_balance=body.starting_balance,
        ends_at=body.ends_at, created_by=current_username(),
        invite_code=_invite_code() if body.kind == CompetitionKind.PRIVATE else "",
    )
    session.add(comp)
    audit(session, current_username(), "competition.created", comp.name)
    session.commit()
    out = _competition_out(comp, 0, False)
    if comp.kind == CompetitionKind.PRIVATE:
        out["invite_code"] = comp.invite_code  # only the creator sees it
    return out


@competitions_router.get("")
def list_competitions(session: Session = Depends(get_db)):
    """Public competitions plus private ones the caller created or joined."""
    user = current_username()
    joined_ids = set(session.scalars(
        select(CompetitionEntry.competition_id).where(CompetitionEntry.username == user)
    ))
    comps = session.scalars(select(Competition).order_by(Competition.created_at.desc())).all()
    out = []
    for c in comps:
        visible = (c.kind == CompetitionKind.PUBLIC or c.created_by == user
                   or c.id in joined_ids or is_admin())
        if not visible:
            continue
        count = session.scalar(
            select(func.count()).select_from(CompetitionEntry)
            .where(CompetitionEntry.competition_id == c.id)
        ) or 0
        row = _competition_out(c, count, c.id in joined_ids)
        if c.created_by == user and c.kind == CompetitionKind.PRIVATE:
            row["invite_code"] = c.invite_code
        out.append(row)
    return out


@competitions_router.post("/{competition_id}/join", status_code=201)
def join_competition(
    competition_id: str,
    body: CompetitionJoin,
    session: Session = Depends(get_db),
):
    """Joining creates a fresh game portfolio at the competition's starting
    balance — everyone competes from the same line (roadmap 7.1)."""
    comp = session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    if comp.kind == CompetitionKind.PRIVATE and body.invite_code != comp.invite_code:
        raise HTTPException(status_code=403, detail="Invalid invite code")
    now = datetime.now(timezone.utc)
    ends = comp.ends_at
    if ends is not None and ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    if ends is not None and ends < now:
        raise HTTPException(status_code=409, detail="Competition has ended")
    user = current_username()
    existing = session.scalar(select(CompetitionEntry).where(
        CompetitionEntry.competition_id == comp.id, CompetitionEntry.username == user))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already joined")
    portfolio = Portfolio(
        owner=user,
        name=f"{comp.name} entry",
        description=f"Game portfolio for competition '{comp.name}'",
        starting_balance=comp.starting_balance,
        cash_balance=comp.starting_balance,
        ends_at=comp.ends_at,
        notes="",
    )
    session.add(portfolio)
    session.flush()
    entry = CompetitionEntry(
        competition_id=comp.id, portfolio_id=portfolio.id, username=user,
        display_name=body.display_name or user,
    )
    session.add(entry)
    audit(session, user, "competition.joined", comp.name)
    session.commit()
    return {"portfolio_id": portfolio.id, "competition_id": comp.id}


@competitions_router.get("/{competition_id}/standings")
def competition_standings(
    competition_id: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    comp = session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    entries = session.scalars(select(CompetitionEntry).where(
        CompetitionEntry.competition_id == comp.id)).all()
    rows = []
    for e in entries:
        portfolio = session.get(Portfolio, e.portfolio_id)
        if portfolio is None:
            continue
        view = value_portfolio(portfolio, market)
        ret = _return_pct(view)
        score: float | None = ret
        if comp.scoring == CompetitionScoring.RISK_ADJUSTED:
            points = value_history(session, portfolio, market, "1Y")["points"]
            score = risk_metrics(points).get("sharpe")
        elif comp.scoring == CompetitionScoring.DIVERSIFICATION:
            score = diversification(view).get("score")
        rows.append({
            "display_name": e.display_name, "score": score,
            "return_pct": round(ret, 2) if ret is not None else None,
            "total_value": view["total_value"],
            "joined_at": e.joined_at.isoformat(),
            "is_me": e.username == current_username(),
        })
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"competition": _competition_out(comp, len(rows), False), "standings": rows}


# --------------------------------------------- cooperative portfolios (7.2)

VOTING_ROLES = (MemberRole.MANAGER, MemberRole.MEMBER)


class MemberAdd(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    role: MemberRole = MemberRole.MEMBER


class ProposalCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: OrderSide
    quantity: Decimal | None = Field(default=None, gt=0)
    notional: Decimal | None = Field(default=None, gt=0)
    rationale: str = Field(default="", max_length=2000)


class Vote(BaseModel):
    approve: bool


def _member_role(session: Session, portfolio: Portfolio, user: str) -> MemberRole | None:
    """Effective cooperative role: the owner acts as a MANAGER."""
    if portfolio.owner == user:
        return MemberRole.MANAGER
    row = session.scalar(select(PortfolioMember).where(
        PortfolioMember.portfolio_id == portfolio.id, PortfolioMember.username == user))
    return row.role if row else None


def _require_manager(session: Session, portfolio: Portfolio) -> None:
    if is_admin():
        return
    if _member_role(session, portfolio, current_username()) != MemberRole.MANAGER:
        raise HTTPException(status_code=403, detail="Manager role required")


@coop_router.get("/members")
def list_members(portfolio_id: str, session: Session = Depends(get_db)):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    rows = session.scalars(select(PortfolioMember).where(
        PortfolioMember.portfolio_id == portfolio_id).order_by(PortfolioMember.added_at)).all()
    return {
        "owner": portfolio.owner,
        "members": [{"username": m.username, "role": m.role.value,
                     "added_at": m.added_at.isoformat()} for m in rows],
    }


@coop_router.post("/members", status_code=201)
def add_member(portfolio_id: str, body: MemberAdd, session: Session = Depends(get_db)):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    _require_manager(session, portfolio)
    if body.username == portfolio.owner:
        raise HTTPException(status_code=422, detail="The owner is already a manager")
    existing = session.scalar(select(PortfolioMember).where(
        PortfolioMember.portfolio_id == portfolio_id,
        PortfolioMember.username == body.username))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already a member")
    session.add(PortfolioMember(portfolio_id=portfolio_id, username=body.username,
                                role=body.role))
    audit(session, current_username(), "coop.member_added",
          f"{body.username} ({body.role.value}) -> {portfolio.name}")
    session.commit()
    return {"username": body.username, "role": body.role.value}


@coop_router.delete("/members/{username}", status_code=204)
def remove_member(portfolio_id: str, username: str, session: Session = Depends(get_db)):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    # Members may leave on their own; removing others takes a manager.
    if username != current_username():
        _require_manager(session, portfolio)
    row = session.scalar(select(PortfolioMember).where(
        PortfolioMember.portfolio_id == portfolio_id,
        PortfolioMember.username == username))
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")
    session.delete(row)
    audit(session, current_username(), "coop.member_removed",
          f"{username} <- {portfolio.name}")
    session.commit()


def _proposal_out(p: TradeProposal, eligible: list[str]) -> dict:
    votes = json.loads(p.votes)
    return {
        "id": p.id, "proposer": p.proposer, "symbol": p.symbol,
        "side": p.side.value,
        "quantity": str(p.quantity) if p.quantity is not None else None,
        "notional": str(p.notional) if p.notional is not None else None,
        "rationale": p.rationale, "status": p.status.value, "detail": p.detail,
        "votes": votes,
        "approvals": sum(1 for v in votes.values() if v),
        "rejections": sum(1 for v in votes.values() if not v),
        "eligible_voters": len(eligible),
        "executed_order_id": p.executed_order_id,
        "created_at": p.created_at.isoformat(),
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
    }


def _eligible_voters(session: Session, portfolio: Portfolio) -> list[str]:
    voters = [portfolio.owner]
    for m in session.scalars(select(PortfolioMember).where(
            PortfolioMember.portfolio_id == portfolio.id)):
        if m.role in VOTING_ROLES:
            voters.append(m.username)
    return voters


@coop_router.get("/proposals")
def list_proposals(portfolio_id: str, session: Session = Depends(get_db)):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    eligible = _eligible_voters(session, portfolio)
    rows = session.scalars(select(TradeProposal).where(
        TradeProposal.portfolio_id == portfolio_id)
        .order_by(TradeProposal.created_at.desc())).all()
    return [_proposal_out(p, eligible) for p in rows]


@coop_router.post("/proposals", status_code=201)
def create_proposal(
    portfolio_id: str,
    body: ProposalCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
    bus: EventBus = Depends(get_bus),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    user = current_username()
    role = _member_role(session, portfolio, user)
    if role not in VOTING_ROLES and not is_admin():
        raise HTTPException(status_code=403, detail="Viewers cannot propose trades")
    if (body.quantity is None) == (body.notional is None):
        raise HTTPException(status_code=422,
                            detail="Provide exactly one of quantity or notional")
    proposal = TradeProposal(
        portfolio_id=portfolio_id, proposer=user, symbol=body.symbol.upper(),
        side=body.side, quantity=body.quantity, notional=body.notional,
        rationale=body.rationale, votes=json.dumps({user: True}),
    )
    session.add(proposal)
    audit(session, user, "coop.proposal_created",
          f"{body.side.value} {body.symbol.upper()} on {portfolio.name}")
    session.commit()
    eligible = _eligible_voters(session, portfolio)
    # A one-person "co-op" auto-passes its own proposal.
    _maybe_decide(session, portfolio, proposal, eligible, market, bus)
    return _proposal_out(proposal, eligible)


@coop_router.post("/proposals/{proposal_id}/vote")
def vote_proposal(
    portfolio_id: str,
    proposal_id: str,
    body: Vote,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
    bus: EventBus = Depends(get_bus),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    proposal = session.get(TradeProposal, proposal_id)
    if proposal is None or proposal.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != ProposalStatus.OPEN:
        raise HTTPException(status_code=409, detail=f"Proposal is {proposal.status.value}")
    user = current_username()
    eligible = _eligible_voters(session, portfolio)
    if user not in eligible:
        raise HTTPException(status_code=403, detail="Only managers and members vote")
    votes = json.loads(proposal.votes)
    votes[user] = body.approve
    proposal.votes = json.dumps(votes)
    session.commit()
    _maybe_decide(session, portfolio, proposal, eligible, market, bus)
    return _proposal_out(proposal, eligible)


def _maybe_decide(
    session: Session,
    portfolio: Portfolio,
    proposal: TradeProposal,
    eligible: list[str],
    market: MarketDataService,
    bus: EventBus,
) -> None:
    """Execute on strict majority approval; reject once a majority is
    mathematically impossible. Execution goes through the exact same
    place_order path as a manual trade (roadmap 7.2 shared decisions)."""
    votes = {u: v for u, v in json.loads(proposal.votes).items() if u in eligible}
    approvals = sum(1 for v in votes.values() if v)
    rejections = sum(1 for v in votes.values() if not v)
    needed = len(eligible) // 2 + 1
    if approvals >= needed:
        _execute_proposal(session, portfolio, proposal, market, bus)
    elif rejections > len(eligible) - needed:
        proposal.status = ProposalStatus.REJECTED
        proposal.decided_at = datetime.now(timezone.utc)
        proposal.detail = f"Rejected {rejections}/{len(eligible)}"
        session.commit()


def _execute_proposal(
    session: Session,
    portfolio: Portfolio,
    proposal: TradeProposal,
    market: MarketDataService,
    bus: EventBus,
) -> None:
    proposal.decided_at = datetime.now(timezone.utc)
    try:
        quote = market.get_quote(proposal.symbol)
        fx = Decimal("1")
        if quote.currency != portfolio.currency:
            fx = market.get_fx_rate(quote.currency, portfolio.currency)
        order, txn = place_order(
            session, portfolio,
            symbol=proposal.symbol, side=proposal.side, type_=OrderType.MARKET,
            quantity=proposal.quantity, notional=proposal.notional,
            current_price=quote.price, fx_rate=fx, quote_currency=quote.currency,
        )
        proposal.status = ProposalStatus.EXECUTED
        proposal.executed_order_id = order.id
        proposal.detail = "Approved by majority vote"
        audit(session, proposal.proposer, "coop.proposal_executed",
              f"{proposal.side.value} {proposal.symbol} on {portfolio.name}")
        session.commit()
        if txn is not None:
            bus.publish("order_filled", {
                "portfolio_id": portfolio.id, "order_id": order.id,
                "symbol": txn.symbol, "side": txn.side.value,
                "quantity": str(txn.quantity), "price": str(txn.price),
                "origin": txn.origin.value,
            })
    except (TradingError, SymbolNotFound, MarketDataError) as exc:
        session.rollback()
        proposal.status = ProposalStatus.FAILED
        proposal.decided_at = datetime.now(timezone.utc)
        proposal.detail = str(exc)
        session.commit()


# ------------------------------------------------------------- clubs (7.4)

class ClubCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    with_portfolio: bool = False
    starting_balance: Decimal = Field(default=Decimal("100000"), gt=0)


class ClubJoin(BaseModel):
    invite_code: str = Field(min_length=1, max_length=12)


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def _club_role(session: Session, club_id: str, user: str) -> MemberRole | None:
    row = session.scalar(select(ClubMember).where(
        ClubMember.club_id == club_id, ClubMember.username == user))
    return row.role if row else None


def _get_club_or_404(session: Session, club_id: str) -> Club:
    club = session.get(Club, club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    if _club_role(session, club_id, current_username()) is None and not is_admin():
        raise HTTPException(status_code=404, detail="Club not found")
    return club


def _club_out(session: Session, club: Club, include_code: bool) -> dict:
    members = session.scalars(select(ClubMember).where(
        ClubMember.club_id == club.id).order_by(ClubMember.joined_at)).all()
    out = {
        "id": club.id, "name": club.name, "description": club.description,
        "created_by": club.created_by, "club_portfolio_id": club.club_portfolio_id,
        "created_at": club.created_at.isoformat(),
        "members": [{"username": m.username, "role": m.role.value,
                     "joined_at": m.joined_at.isoformat()} for m in members],
    }
    if include_code:
        out["invite_code"] = club.invite_code
    return out


@clubs_router.post("", status_code=201)
def create_club(
    body: ClubCreate,
    session: Session = Depends(get_db),
):
    user = current_username()
    club = Club(name=body.name, description=body.description,
                invite_code=_invite_code(), created_by=user)
    session.add(club)
    session.flush()
    session.add(ClubMember(club_id=club.id, username=user, role=MemberRole.MANAGER))
    if body.with_portfolio:
        portfolio = Portfolio(
            owner=user, name=f"{body.name} club portfolio",
            description=f"Cooperative portfolio of the '{body.name}' club",
            starting_balance=body.starting_balance,
            cash_balance=body.starting_balance,
        )
        session.add(portfolio)
        session.flush()
        club.club_portfolio_id = portfolio.id
    audit(session, user, "club.created", body.name)
    session.commit()
    return _club_out(session, club, include_code=True)


@clubs_router.get("")
def list_my_clubs(session: Session = Depends(get_db)):
    user = current_username()
    club_ids = select(ClubMember.club_id).where(ClubMember.username == user)
    query = select(Club).order_by(Club.created_at)
    if not is_admin():
        query = query.where(Club.id.in_(club_ids))
    return [
        {"id": c.id, "name": c.name, "description": c.description,
         "club_portfolio_id": c.club_portfolio_id, "created_at": c.created_at.isoformat()}
        for c in session.scalars(query)
    ]


@clubs_router.post("/join", status_code=201)
def join_club(body: ClubJoin, session: Session = Depends(get_db)):
    club = session.scalar(select(Club).where(Club.invite_code == body.invite_code))
    if club is None:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    user = current_username()
    if _club_role(session, club.id, user) is not None:
        raise HTTPException(status_code=409, detail="Already a member")
    session.add(ClubMember(club_id=club.id, username=user, role=MemberRole.MEMBER))
    # Club portfolio is cooperative: joining the club joins the portfolio.
    if club.club_portfolio_id:
        exists = session.scalar(select(PortfolioMember).where(
            PortfolioMember.portfolio_id == club.club_portfolio_id,
            PortfolioMember.username == user))
        if exists is None and user != session.get(Portfolio, club.club_portfolio_id).owner:
            session.add(PortfolioMember(portfolio_id=club.club_portfolio_id,
                                        username=user, role=MemberRole.MEMBER))
    audit(session, user, "club.joined", club.name)
    session.commit()
    return {"id": club.id, "name": club.name}


@clubs_router.get("/{club_id}")
def club_detail(club_id: str, session: Session = Depends(get_db)):
    club = _get_club_or_404(session, club_id)
    include_code = (club.created_by == current_username()
                    or _club_role(session, club_id, current_username()) == MemberRole.MANAGER
                    or is_admin())
    return _club_out(session, club, include_code)


@clubs_router.delete("/{club_id}", status_code=204)
def delete_club(club_id: str, session: Session = Depends(get_db)):
    club = _get_club_or_404(session, club_id)
    if club.created_by != current_username() and not is_admin():
        raise HTTPException(status_code=403, detail="Only the creator can delete a club")
    session.delete(club)  # members/messages cascade
    audit(session, current_username(), "club.deleted", club.name)
    session.commit()


@clubs_router.delete("/{club_id}/members/{username}", status_code=204)
def leave_or_kick(club_id: str, username: str, session: Session = Depends(get_db)):
    club = _get_club_or_404(session, club_id)
    me = current_username()
    if username != me:
        if _club_role(session, club_id, me) != MemberRole.MANAGER and not is_admin():
            raise HTTPException(status_code=403, detail="Manager role required")
    row = session.scalar(select(ClubMember).where(
        ClubMember.club_id == club_id, ClubMember.username == username))
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")
    session.delete(row)
    audit(session, me, "club.member_removed", f"{username} <- {club.name}")
    session.commit()


@clubs_router.get("/{club_id}/messages")
def club_messages(club_id: str, limit: int = 100, session: Session = Depends(get_db)):
    _get_club_or_404(session, club_id)
    rows = session.scalars(
        select(ClubMessage).where(ClubMessage.club_id == club_id)
        .order_by(ClubMessage.created_at.desc()).limit(min(limit, 500))
    ).all()
    return [
        {"id": m.id, "author": m.author, "body": m.body,
         "created_at": m.created_at.isoformat()}
        for m in reversed(rows)
    ]


@clubs_router.post("/{club_id}/messages", status_code=201)
def post_message(club_id: str, body: MessageCreate, session: Session = Depends(get_db)):
    _get_club_or_404(session, club_id)
    msg = ClubMessage(club_id=club_id, author=current_username(), body=body.body)
    session.add(msg)
    session.commit()
    return {"id": msg.id, "author": msg.author, "body": msg.body,
            "created_at": msg.created_at.isoformat()}


@clubs_router.get("/{club_id}/rankings")
def club_rankings(
    club_id: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """Members ranked by their best personal portfolio return (roadmap 7.4).
    The shared club portfolio is excluded — it's collective work."""
    club = _get_club_or_404(session, club_id)
    members = session.scalars(select(ClubMember).where(
        ClubMember.club_id == club_id)).all()
    rows = []
    for m in members:
        portfolios = session.scalars(select(Portfolio).where(
            Portfolio.owner == m.username,
            Portfolio.id != (club.club_portfolio_id or ""))).all()
        best: float | None = None
        for p in portfolios:
            ret = _return_pct(value_portfolio(p, market))
            if ret is not None and (best is None or ret > best):
                best = ret
        rows.append({"username": m.username, "role": m.role.value,
                     "best_return_pct": round(best, 2) if best is not None else None})
    rows.sort(key=lambda r: (r["best_return_pct"] is None,
                             -(r["best_return_pct"] or 0)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
