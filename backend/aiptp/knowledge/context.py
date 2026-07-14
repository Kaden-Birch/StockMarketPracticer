"""Contextual learning (roadmap 10.3) + mentor integration (10.9).

Detects learning opportunities from the user's REAL portfolio state and the
persistent mentor's memory, and points each one at a dictionary concept.
Every suggestion carries the evidence that triggered it."""

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.service import diversification
from ..core.currentuser import current_username
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import (
    ConceptProgress,
    MentorProfile,
    Portfolio,
    Transaction,
    TransactionKind,
)

# mentor observation code -> concept the mentor recommends studying (10.9)
MENTOR_CONCEPT_MAP = {
    "sells_winners_early": "momentum",
    "panic_selling": "market_cycle",
    "no_international_exposure": "geographic_diversification",
    "concentrated_portfolio": "concentration_risk",
    "cash_drag": "dca",
    "frequent_trading": "index_investing",
    "no_education_activity": "pe_ratio",
}


def suggestions(session: Session, market: MarketDataService) -> list[dict]:
    username = current_username()
    out: list[dict] = []
    seen_concepts: set[str] = set()

    def add(concept_id: str, why: str, portfolio_name: str | None = None) -> None:
        if concept_id in seen_concepts:
            return
        seen_concepts.add(concept_id)
        out.append({"concept_id": concept_id, "why": why,
                    "portfolio": portfolio_name})

    portfolios = session.scalars(select(Portfolio).where(
        Portfolio.owner.in_([username, "local"]),
        Portfolio.scenario_session_id.is_(None),
    )).all()

    for p in portfolios:
        try:
            view = value_portfolio(p, market)
        except MarketDataError:
            continue
        total = Decimal(view["total_value"])
        if total <= 0 or not view["holdings"]:
            continue
        div = diversification(view)
        score = div.get("score")
        weights = div.get("weights", {})
        # 10.3 example: heavy sector/name concentration
        heavy = [(s, w) for s, w in weights.items() if s != "CASH" and w >= 50]
        if heavy:
            add("concentration_risk",
                f"{heavy[0][0]} is {heavy[0][1]:.0f}% of '{p.name}' — one "
                "position dominates the outcome. Learn about concentration "
                "risk.", p.name)
        elif score is not None and score < 40:
            add("diversification",
                f"'{p.name}' has a diversification score of {score}/100. "
                "Learn why investors diversify.", p.name)
        cash_pct = float(Decimal(view["cash_balance"]) / total * 100)
        if cash_pct > 60:
            add("dca",
                f"{cash_pct:.0f}% of '{p.name}' sits in cash. Learn how "
                "dollar cost averaging puts money to work without timing "
                "stress.", p.name)

    # 10.3 example: everything domestic
    trades = session.scalars(select(Transaction).where(
        Transaction.kind == TransactionKind.TRADE).limit(200)).all()
    if len(trades) >= 5 and all(
            t.quote_currency in ("", "USD") and t.fx_rate == Decimal("1")
            for t in trades):
        add("geographic_diversification",
            "Every trade so far settled in USD — your whole simulation is "
            "one economy. Learn why investors diversify geographically.")

    # 10.9: the mentor's knowledge gaps and active observations
    prof = session.get(MentorProfile, username)
    if prof is not None:
        gaps = json.loads(prof.knowledge_gaps or "[]")
        if any("valuation" in g for g in gaps):
            add("pe_ratio", "The mentor noticed you haven't explored "
                "valuation metrics yet — start with the P/E ratio.")
        if any("backtesting" in g for g in gaps):
            add("index_investing", "Before building strategies, learn the "
                "benchmark every strategy must beat: the index.")
    from ..storage.models import MentorObservation, ObservationStatus

    for obs in session.scalars(select(MentorObservation).where(
            MentorObservation.username == username,
            MentorObservation.status != ObservationStatus.RESOLVED)):
        concept = MENTOR_CONCEPT_MAP.get(obs.code)
        if concept:
            add(concept, f"Your mentor flagged: “{obs.title}”. The related "
                "concept explains the underlying idea.")

    # never re-suggest what's already studied (viewed + quiz passed)
    done = {cp.concept_id for cp in session.scalars(select(ConceptProgress).where(
        ConceptProgress.username == username, ConceptProgress.quiz_passed == True))}  # noqa: E712
    return [s for s in out if s["concept_id"] not in done][:6]
