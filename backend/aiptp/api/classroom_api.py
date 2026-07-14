"""Classroom mode API (roadmap 8.6): instructors create classrooms and
assignments; students join by invite code and work in fresh portfolios
(optionally pinned to a historical scenario and/or mandate); the instructor
dashboard tracks everyone's progress."""

import secrets
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..career import mandates as mandates_mod
from ..core.currentuser import current_username, is_admin
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..scenario import engine as scenario_engine
from ..scenario.catalog import SCENARIOS
from ..security.audit import audit
from ..storage.models import (
    Assignment,
    AssignmentEntry,
    Classroom,
    ClassroomStudent,
    Portfolio,
    ScenarioSession,
)
from .deps import get_db, get_market

router = APIRouter(prefix="/classrooms", tags=["classroom"])
assignment_router = APIRouter(prefix="/assignments", tags=["classroom"])


class ClassroomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ClassroomJoin(BaseModel):
    invite_code: str = Field(min_length=1, max_length=12)


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    scenario_id: str = ""  # "" = live market
    mandate: str = ""
    starting_balance: Decimal = Field(default=Decimal("100000"), gt=0)
    due_at: datetime | None = None


def _member_or_404(db: Session, classroom_id: str) -> tuple[Classroom, bool]:
    """Returns (classroom, is_instructor); 404 for outsiders."""
    room = db.get(Classroom, classroom_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    user = current_username()
    if room.instructor == user or is_admin():
        return room, True
    enrolled = db.scalar(select(ClassroomStudent).where(
        ClassroomStudent.classroom_id == classroom_id,
        ClassroomStudent.username == user))
    if enrolled is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return room, False


@router.post("", status_code=201)
def create_classroom(body: ClassroomCreate, db: Session = Depends(get_db)):
    room = Classroom(name=body.name, instructor=current_username(),
                     invite_code=secrets.token_hex(4))
    db.add(room)
    audit(db, current_username(), "classroom.created", body.name)
    db.commit()
    return {"id": room.id, "name": room.name, "invite_code": room.invite_code,
            "instructor": room.instructor}


@router.get("")
def my_classrooms(db: Session = Depends(get_db)):
    user = current_username()
    teaching = db.scalars(select(Classroom).where(
        Classroom.instructor == user)).all()
    enrolled_ids = select(ClassroomStudent.classroom_id).where(
        ClassroomStudent.username == user)
    attending = db.scalars(select(Classroom).where(
        Classroom.id.in_(enrolled_ids))).all()
    def row(c: Classroom, role: str) -> dict:
        return {"id": c.id, "name": c.name, "instructor": c.instructor,
                "role": role, "created_at": c.created_at.isoformat()}
    return [row(c, "instructor") for c in teaching] + \
           [row(c, "student") for c in attending]


@router.post("/join", status_code=201)
def join_classroom(body: ClassroomJoin, db: Session = Depends(get_db)):
    room = db.scalar(select(Classroom).where(
        Classroom.invite_code == body.invite_code))
    if room is None:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    user = current_username()
    if room.instructor == user:
        raise HTTPException(status_code=409, detail="You teach this classroom")
    if db.scalar(select(ClassroomStudent).where(
            ClassroomStudent.classroom_id == room.id,
            ClassroomStudent.username == user)) is not None:
        raise HTTPException(status_code=409, detail="Already enrolled")
    db.add(ClassroomStudent(classroom_id=room.id, username=user))
    audit(db, user, "classroom.joined", room.name)
    db.commit()
    return {"id": room.id, "name": room.name}


@router.get("/{classroom_id}")
def classroom_detail(classroom_id: str, db: Session = Depends(get_db)):
    room, teaching = _member_or_404(db, classroom_id)
    students = db.scalars(select(ClassroomStudent).where(
        ClassroomStudent.classroom_id == classroom_id)
        .order_by(ClassroomStudent.joined_at)).all()
    out = {
        "id": room.id, "name": room.name, "instructor": room.instructor,
        "is_instructor": teaching,
        "students": [{"username": s.username, "joined_at": s.joined_at.isoformat()}
                     for s in students],
    }
    if teaching:
        out["invite_code"] = room.invite_code
    return out


@router.delete("/{classroom_id}", status_code=204)
def delete_classroom(classroom_id: str, db: Session = Depends(get_db)):
    room, teaching = _member_or_404(db, classroom_id)
    if not teaching:
        raise HTTPException(status_code=403, detail="Instructor only")
    db.delete(room)
    audit(db, current_username(), "classroom.deleted", room.name)
    db.commit()


@router.post("/{classroom_id}/assignments", status_code=201)
def create_assignment(classroom_id: str, body: AssignmentCreate,
                      db: Session = Depends(get_db)):
    room, teaching = _member_or_404(db, classroom_id)
    if not teaching:
        raise HTTPException(status_code=403, detail="Instructor only")
    if body.scenario_id and body.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=422,
                            detail=f"Unknown scenario: {body.scenario_id}")
    if body.mandate and body.mandate not in mandates_mod.MANDATE_IDS:
        raise HTTPException(status_code=422,
                            detail=f"mandate must be one of {list(mandates_mod.MANDATE_IDS)}")
    assignment = Assignment(
        classroom_id=classroom_id, title=body.title, description=body.description,
        scenario_id=body.scenario_id, mandate=body.mandate,
        starting_balance=body.starting_balance, due_at=body.due_at,
    )
    db.add(assignment)
    audit(db, current_username(), "assignment.created",
          f"{body.title} in {room.name}")
    db.commit()
    return _assignment_out(assignment)


def _assignment_out(a: Assignment) -> dict:
    return {
        "id": a.id, "classroom_id": a.classroom_id, "title": a.title,
        "description": a.description, "scenario_id": a.scenario_id,
        "mandate": a.mandate, "starting_balance": str(a.starting_balance),
        "due_at": a.due_at.isoformat() if a.due_at else None,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/{classroom_id}/assignments")
def list_assignments(classroom_id: str, db: Session = Depends(get_db)):
    _member_or_404(db, classroom_id)
    user = current_username()
    rows = db.scalars(select(Assignment).where(
        Assignment.classroom_id == classroom_id)
        .order_by(Assignment.created_at.desc())).all()
    out = []
    for a in rows:
        entry = db.scalar(select(AssignmentEntry).where(
            AssignmentEntry.assignment_id == a.id,
            AssignmentEntry.username == user))
        d = _assignment_out(a)
        d["my_entry"] = ({
            "portfolio_id": entry.portfolio_id,
            "scenario_session_id": entry.scenario_session_id,
            "started_at": entry.started_at.isoformat(),
        } if entry else None)
        out.append(d)
    return out


@assignment_router.post("/{assignment_id}/start", status_code=201)
def start_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _member_or_404(db, assignment.classroom_id)  # must be in the class
    user = current_username()
    if db.scalar(select(AssignmentEntry).where(
            AssignmentEntry.assignment_id == assignment_id,
            AssignmentEntry.username == user)) is not None:
        raise HTTPException(status_code=409, detail="Assignment already started")

    scenario_session_id = None
    if assignment.scenario_id:
        try:
            sess = scenario_engine.create_session(db, market, assignment.scenario_id,
                                                  user, display_name=user)
        except MarketDataError as exc:
            raise HTTPException(status_code=503,
                                detail=f"Historical data unavailable: {exc}")
        portfolio = db.get(Portfolio, sess.portfolio_id)
        portfolio.name = assignment.title
        portfolio.starting_balance = assignment.starting_balance
        portfolio.cash_balance = assignment.starting_balance
        scenario_session_id = sess.id
        portfolio_id = sess.portfolio_id
    else:
        portfolio = Portfolio(
            owner=user, name=assignment.title,
            description=f"Classroom assignment: {assignment.description}",
            starting_balance=assignment.starting_balance,
            cash_balance=assignment.starting_balance,
        )
        db.add(portfolio)
        db.flush()
        portfolio_id = portfolio.id
    portfolio.mandate = assignment.mandate
    db.add(AssignmentEntry(
        assignment_id=assignment_id, username=user, portfolio_id=portfolio_id,
        scenario_session_id=scenario_session_id,
    ))
    audit(db, user, "assignment.started", assignment.title)
    db.commit()
    return {"portfolio_id": portfolio_id,
            "scenario_session_id": scenario_session_id}


@router.get("/{classroom_id}/progress")
def classroom_progress(
    classroom_id: str,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """Instructor dashboard (roadmap 8.6): per assignment, per student —
    started, current value/return, scenario progress, mandate compliance."""
    room, teaching = _member_or_404(db, classroom_id)
    if not teaching:
        raise HTTPException(status_code=403, detail="Instructor only")
    students = [s.username for s in db.scalars(select(ClassroomStudent).where(
        ClassroomStudent.classroom_id == classroom_id))]
    assignments = db.scalars(select(Assignment).where(
        Assignment.classroom_id == classroom_id)).all()
    out = []
    for a in assignments:
        entries = {e.username: e for e in db.scalars(select(AssignmentEntry).where(
            AssignmentEntry.assignment_id == a.id))}
        rows = []
        # enrolled students first, then anyone else with an entry (e.g. the
        # instructor trying their own assignment in desktop mode)
        everyone = students + [u for u in entries if u not in students]
        for student in everyone:
            entry = entries.get(student)
            row: dict = {"username": student, "started": entry is not None}
            if entry is not None:
                portfolio = db.get(Portfolio, entry.portfolio_id)
                if portfolio is not None:
                    if entry.scenario_session_id:
                        sess = db.get(ScenarioSession, entry.scenario_session_id)
                        if sess is not None:
                            try:
                                view = scenario_engine.session_view(db, market, sess)
                                row.update(value=view["value"],
                                           return_pct=view["return_pct"],
                                           scenario_day=view["day"],
                                           scenario_total_days=view["total_days"],
                                           completed=view["completed"])
                            except MarketDataError:
                                row["note"] = "historical data unavailable"
                    else:
                        try:
                            view = value_portfolio(portfolio, market)
                            starting = Decimal(view["starting_balance"])
                            ret = ((Decimal(view["total_value"]) - starting)
                                   / starting * 100) if starting else Decimal("0")
                            row.update(value=view["total_value"],
                                       return_pct=str(ret.quantize(Decimal("0.01"))))
                        except MarketDataError:
                            row["note"] = "market data unavailable"
                    if a.mandate:
                        comp = mandates_mod.compliance(db, portfolio, market)
                        row["mandate_compliant"] = comp.get("compliant")
            rows.append(row)
        out.append({"assignment": _assignment_out(a), "students": rows})
    return {"classroom": room.name, "progress": out}
