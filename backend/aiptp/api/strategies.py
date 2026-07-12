import json
import threading
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..automation.conditions import validate_trigger
from ..marketdata.base import MarketDataError, SymbolNotFound
from ..storage.models import BacktestRun, BacktestStatus, Strategy
from ..strategy.backtest import run_backtest, substitute_symbol
from ..strategy.whatif import WhatIfError, simulate
from .deps import get_bus, get_db, get_market, get_portfolio_or_404

router = APIRouter(prefix="/strategies", tags=["strategies"])
whatif_router = APIRouter(prefix="/portfolios/{portfolio_id}", tags=["whatif"])


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    universe: list[str] = Field(min_length=1, max_length=20)
    entry_trigger: dict
    exit_trigger: dict | None = None
    entry_notional: Decimal = Field(default=Decimal("1000"), gt=0)
    initial_cash: Decimal = Field(default=Decimal("10000"), gt=0)
    benchmark: str = "SPY"

    @field_validator("universe")
    @classmethod
    def _upper(cls, v: list[str]) -> list[str]:
        return sorted({s.strip().upper() for s in v if s.strip()})


def _strategy_view(s: Strategy) -> dict:
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "universe": json.loads(s.universe),
        "entry_trigger": json.loads(s.entry_trigger),
        "exit_trigger": json.loads(s.exit_trigger) if s.exit_trigger else None,
        "entry_notional": str(s.entry_notional),
        "initial_cash": str(s.initial_cash),
        "benchmark": s.benchmark,
        "created_at": s.created_at.isoformat(),
    }


def _run_view(r: BacktestRun) -> dict:
    return {
        "id": r.id, "strategy_id": r.strategy_id, "range": r.range,
        "status": r.status.value, "progress_pct": r.progress_pct, "error": r.error,
        "results": json.loads(r.results or "{}"),
        "created_at": r.created_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


@router.post("", status_code=201)
def create_strategy(body: StrategyCreate, session: Session = Depends(get_db)):
    # Validate the templated ASTs with a placeholder symbol substituted in.
    try:
        validate_trigger(substitute_symbol(body.entry_trigger, "TEST"))
        if body.exit_trigger is not None:
            validate_trigger(substitute_symbol(body.exit_trigger, "TEST"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    strategy = Strategy(
        name=body.name,
        description=body.description,
        universe=json.dumps(body.universe),
        entry_trigger=json.dumps(body.entry_trigger),
        exit_trigger=json.dumps(body.exit_trigger) if body.exit_trigger else None,
        entry_notional=body.entry_notional,
        initial_cash=body.initial_cash,
        benchmark=body.benchmark.upper(),
    )
    session.add(strategy)
    session.commit()
    return _strategy_view(strategy)


@router.get("")
def list_strategies(session: Session = Depends(get_db)):
    return [
        _strategy_view(s)
        for s in session.scalars(select(Strategy).order_by(Strategy.created_at)).all()
    ]


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: str, session: Session = Depends(get_db)):
    strategy = session.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    session.delete(strategy)
    session.commit()


class BacktestBody(BaseModel):
    range: str = "1Y"


@router.post("/{strategy_id}/backtest", status_code=202)
def start_backtest(
    strategy_id: str,
    body: BacktestBody,
    request: Request,
    session: Session = Depends(get_db),
    market=Depends(get_market),
    bus=Depends(get_bus),
):
    strategy = session.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    run = BacktestRun(strategy_id=strategy.id, range=body.range.upper())
    session.add(run)
    session.commit()
    run_id = run.id
    session_factory = request.app.state.session_factory

    def progress(pct: int) -> None:
        with session_factory() as s:
            row = s.get(BacktestRun, run_id)
            if row:
                row.progress_pct = pct
                s.commit()
        if bus is not None:
            bus.publish("backtest_progress", {"run_id": run_id, "pct": pct})

    def worker() -> None:
        try:
            results = run_backtest(strategy, market, body.range, progress)
            status, error = BacktestStatus.DONE, ""
        except (MarketDataError, SymbolNotFound, ValueError) as exc:
            results, status, error = {}, BacktestStatus.FAILED, str(exc)
        except Exception as exc:  # noqa: BLE001 — a failed run must be recorded
            results, status, error = {}, BacktestStatus.FAILED, f"internal error: {exc}"
        with session_factory() as s:
            row = s.get(BacktestRun, run_id)
            if row:
                row.status = status
                row.error = error
                row.progress_pct = 100
                row.results = json.dumps(results)
                row.finished_at = datetime.now(timezone.utc)
                s.commit()
        if bus is not None:
            bus.publish("backtest_done", {"run_id": run_id, "status": status.value})

    threading.Thread(target=worker, daemon=True, name=f"backtest-{run_id}").start()
    return {"run_id": run_id, "status": "RUNNING"}


@router.get("/{strategy_id}/backtests")
def list_backtests(strategy_id: str, session: Session = Depends(get_db)):
    if session.get(Strategy, strategy_id) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    runs = session.scalars(
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(20)
    ).all()
    return [_run_view(r) for r in runs]


@router.get("/backtests/{run_id}")
def get_backtest(run_id: str, session: Session = Depends(get_db)):
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return _run_view(run)


class WhatIfBody(BaseModel):
    scenario: dict
    range: str = "1Y"


@whatif_router.post("/whatif")
def what_if(
    portfolio_id: str,
    body: WhatIfBody,
    session: Session = Depends(get_db),
    market=Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    try:
        return simulate(session, portfolio, market, body.scenario, body.range)
    except WhatIfError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
