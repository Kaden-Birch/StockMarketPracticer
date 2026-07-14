"""Learning system API (roadmap M10), mounted by the knowledge module."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.currentuser import current_username
from ..core.events import EventBus
from ..gamify.service import award_action, gamification_enabled
from ..knowledge import context as ctx_mod
from ..knowledge import simulators
from ..knowledge.content import (
    CATEGORIES,
    CONCEPTS,
    PATHS,
    concept_view,
    search,
)
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import ConceptProgress, utcnow
from .deps import get_bus, get_db, get_market

router = APIRouter(prefix="/learn", tags=["learn"])

PASS_PCT = 70


def _progress_row(session: Session, concept_id: str) -> ConceptProgress:
    username = current_username()
    row = session.scalar(select(ConceptProgress).where(
        ConceptProgress.username == username,
        ConceptProgress.concept_id == concept_id))
    if row is None:
        row = ConceptProgress(username=username, concept_id=concept_id,
                              viewed_count=0, quiz_passed=False)
        session.add(row)
    return row


@router.get("/concepts")
def list_concepts(q: str = "", category: str = "",
                  session: Session = Depends(get_db)):
    hits = search(q)
    if category:
        if category not in CATEGORIES:
            raise HTTPException(status_code=422,
                                detail=f"category must be one of {sorted(CATEGORIES)}")
        hits = [c for c in hits if c.category == category]
    username = current_username()
    progress = {cp.concept_id: cp for cp in session.scalars(
        select(ConceptProgress).where(ConceptProgress.username == username))}
    out = []
    for c in hits:
        v = concept_view(c)
        cp = progress.get(c.id)
        v["viewed"] = cp is not None and cp.viewed_count > 0
        v["quiz_passed"] = cp.quiz_passed if cp else False
        out.append(v)
    return {"categories": [{"id": k, "name": n} for k, n in CATEGORIES.items()],
            "concepts": out}


@router.get("/concepts/{concept_id}")
def get_concept(
    concept_id: str,
    session: Session = Depends(get_db),
    bus: EventBus = Depends(get_bus),
):
    concept = CONCEPTS.get(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    row = _progress_row(session, concept_id)
    first_view = row.viewed_count == 0
    row.viewed_count += 1
    row.last_viewed = utcnow()
    if first_view and gamification_enabled(session):
        award_action(session, bus, "concept_viewed", reason=concept_id)
    session.commit()
    out = concept_view(concept, include_quiz=True)
    out["viewed_count"] = row.viewed_count
    out["quiz_passed"] = row.quiz_passed
    out["quiz_score"] = row.quiz_score
    return out


class QuizSubmit(BaseModel):
    answers: list[int]


@router.post("/concepts/{concept_id}/quiz")
def submit_quiz(
    concept_id: str,
    body: QuizSubmit,
    session: Session = Depends(get_db),
    bus: EventBus = Depends(get_bus),
):
    concept = CONCEPTS.get(concept_id)
    if concept is None or not concept.quiz:
        raise HTTPException(status_code=404, detail="No quiz for this concept")
    if len(body.answers) != len(concept.quiz):
        raise HTTPException(status_code=422,
                            detail=f"Expected {len(concept.quiz)} answers")
    results = []
    correct = 0
    for q, a in zip(concept.quiz, body.answers):
        ok = a == q.answer
        correct += ok
        results.append({"correct": ok, "answer": q.answer, "why": q.why})
    score = round(correct / len(concept.quiz) * 100)
    row = _progress_row(session, concept_id)
    row.quiz_score = max(row.quiz_score or 0, score)
    newly_passed = score >= PASS_PCT and not row.quiz_passed
    if score >= PASS_PCT:
        row.quiz_passed = True
    if newly_passed and gamification_enabled(session):
        award_action(session, bus, "quiz_passed", reason=concept_id)
    session.commit()
    return {"score": score, "passed": score >= PASS_PCT, "results": results}


@router.get("/paths")
def learning_paths(session: Session = Depends(get_db),
                   bus: EventBus = Depends(get_bus)):
    username = current_username()
    progress = {cp.concept_id: cp for cp in session.scalars(
        select(ConceptProgress).where(ConceptProgress.username == username))}
    out = []
    for path in PATHS.values():
        steps = []
        done = 0
        for cid in path.concepts:
            cp = progress.get(cid)
            viewed = cp is not None and cp.viewed_count > 0
            passed = cp.quiz_passed if cp else False
            has_quiz = bool(CONCEPTS[cid].quiz)
            complete = passed if has_quiz else viewed
            done += complete
            steps.append({"concept_id": cid, "term": CONCEPTS[cid].term,
                          "viewed": viewed, "has_quiz": has_quiz,
                          "quiz_passed": passed, "complete": complete})
        completed = done == len(path.concepts)
        marker_id = f"path:{path.id}"
        if completed and marker_id not in progress:
            marker = ConceptProgress(username=username, concept_id=marker_id,
                                     viewed_count=1, quiz_passed=True)
            session.add(marker)
            if gamification_enabled(session):
                award_action(session, bus, "path_completed", reason=path.id)
            session.commit()
        out.append({"id": path.id, "name": path.name,
                    "description": path.description, "steps": steps,
                    "done": done, "total": len(path.concepts),
                    "completed": completed})
    return out


@router.get("/progress")
def knowledge_progress(session: Session = Depends(get_db)):
    """Knowledge tracking (10.7) + learning achievements (10.8)."""
    username = current_username()
    rows = [cp for cp in session.scalars(select(ConceptProgress).where(
        ConceptProgress.username == username))
        if not cp.concept_id.startswith("path:")]
    viewed = [r for r in rows if r.viewed_count > 0]
    passed = [r for r in rows if r.quiz_passed]
    by_category: dict[str, dict] = {
        k: {"name": n, "viewed": 0, "total": 0} for k, n in CATEGORIES.items()}
    for c in CONCEPTS.values():
        by_category[c.category]["total"] += 1
    viewed_ids = {r.concept_id for r in viewed}
    for cid in viewed_ids:
        c = CONCEPTS.get(cid)
        if c:
            by_category[c.category]["viewed"] += 1
    path_done = {cp.concept_id.removeprefix("path:") for cp in session.scalars(
        select(ConceptProgress).where(
            ConceptProgress.username == username,
            ConceptProgress.concept_id.startswith("path:")))}

    achievements = [
        {"id": "first_concept", "name": "First Steps",
         "description": "Learned your first investing concept",
         "earned": len(viewed) >= 1},
        {"id": "fundamentals", "name": "Completed Fundamentals",
         "description": "Finished the Beginner Investor path",
         "earned": "beginner_investor" in path_done},
        {"id": "portfolio_expert", "name": "Portfolio Management Expert",
         "description": "Studied every portfolio-management concept",
         "earned": by_category["portfolio"]["viewed"] ==
                   by_category["portfolio"]["total"]},
        {"id": "economist", "name": "Market Historian",
         "description": "Studied every economics concept",
         "earned": by_category["economics"]["viewed"] ==
                   by_category["economics"]["total"]},
        {"id": "quiz_ace", "name": "Quiz Ace",
         "description": "Passed 5 quizzes",
         "earned": len(passed) >= 5},
    ]
    return {
        "concepts_viewed": len(viewed),
        "concepts_total": len(CONCEPTS),
        "quizzes_passed": len(passed),
        "paths_completed": sorted(path_done),
        "categories": by_category,
        "achievements": achievements,
    }


@router.get("/suggestions")
def learning_suggestions(
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """Contextual learning (10.3) grounded in the real portfolio, plus the
    mentor's recommendations (10.9)."""
    out = ctx_mod.suggestions(session, market)
    for s in out:
        c = CONCEPTS.get(s["concept_id"])
        if c:
            s["term"] = c.term
    return out


class AskBody(BaseModel):
    mode: str = Field(pattern="^(simple|examples|portfolio_impact|compare)$")
    other_concept: str = ""
    portfolio_id: str = ""


ASK_SYSTEM = (
    "You are an investing teacher inside a paper-trading simulator. You are "
    "given a VERIFIED reference explanation of a concept (and sometimes real "
    "portfolio facts). Answer the student's request using ONLY that "
    "material plus general arithmetic — do not invent statistics, prices, "
    "or predictions. Maximum 150 words, plain text. This is education, "
    "never financial advice."
)


@router.post("/concepts/{concept_id}/ask")
def ask_ai(
    concept_id: str,
    body: AskBody,
    request: Request,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """AI explanations (10.4): explain simply / give examples / impact on my
    portfolio / compare concepts — grounded in the dictionary content."""
    concept = CONCEPTS.get(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    manager = request.app.state.model_manager
    if not manager.runtime.model_id:
        raise HTTPException(
            status_code=409,
            detail="No AI model loaded — the three built-in explanation "
                   "levels above never need one")
    pack: dict = {
        "concept": concept.term,
        "reference": {"beginner": concept.beginner,
                      "intermediate": concept.intermediate,
                      "advanced": concept.advanced},
        "request": body.mode,
    }
    if body.mode == "compare":
        other = CONCEPTS.get(body.other_concept)
        if other is None:
            raise HTTPException(status_code=422,
                                detail="other_concept required for compare")
        pack["compare_with"] = {"concept": other.term,
                                "reference": other.intermediate}
    if body.mode == "portfolio_impact":
        from ..api.deps import get_portfolio_or_404
        from ..analytics.service import diversification
        from ..portfolio.service import value_portfolio

        if not body.portfolio_id:
            raise HTTPException(status_code=422,
                                detail="portfolio_id required for portfolio_impact")
        portfolio = get_portfolio_or_404(session, body.portfolio_id)
        try:
            view = value_portfolio(portfolio, market)
            pack["portfolio_facts"] = {
                "positions": [{"symbol": h["symbol"],
                               "market_value": h["market_value"]}
                              for h in view["holdings"]],
                "cash": view["cash_balance"],
                "total": view["total_value"],
                "diversification_score": diversification(view).get("score"),
            }
        except MarketDataError as exc:
            raise HTTPException(status_code=503,
                                detail=f"Market data unavailable: {exc}")
    text = manager.runtime.generate(ASK_SYSTEM, json.dumps(pack, indent=1),
                                    max_tokens=300).strip()
    return {"answer": text + "\n\n(Educational explanation — not financial advice.)"}


class SimulateBody(BaseModel):
    params: dict = Field(default_factory=dict)


@router.post("/simulate/{kind}")
def simulate(
    kind: str,
    body: SimulateBody,
    market: MarketDataService = Depends(get_market),
):
    """Interactive simulations (10.5)."""
    p = body.params
    try:
        if kind == "compound_growth":
            return simulators.compound_growth(
                float(p.get("principal", 1000)),
                float(p.get("monthly", 100)),
                float(p.get("annual_rate_pct", 7)),
                int(p.get("years", 30)))
        if kind == "diversification":
            return simulators.diversification_sim(
                float(p.get("single_volatility_pct", 40)),
                float(p.get("correlation", 0.3)))
        if kind == "risk_allocation":
            return simulators.risk_allocation_sim(
                float(p.get("stocks_pct", 60)),
                float(p.get("bonds_pct", 30)),
                float(p.get("cash_pct", 10)),
                int(p.get("years", 20)),
                float(p.get("start", 10000)))
        if kind == "market_crash":
            return simulators.crash_sim(
                market,
                str(p.get("scenario_id", "gfc_2008")),
                float(p.get("starting_value", 10000)))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503,
                            detail=f"Historical data unavailable: {exc}")
    raise HTTPException(
        status_code=404,
        detail="kind must be one of: compound_growth, diversification, "
               "risk_allocation, market_crash")
