import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.assistant import DISCLAIMER, analyze_portfolio, rec_view, try_execute
from ..ai.catalog import CATALOG
from ..ai.manager import detect_hardware
from ..marketdata.base import MarketDataError
from ..security.audit import audit
from ..storage.models import AppSetting, Recommendation, RecommendationStatus
from .deps import get_bus, get_db, get_market, get_portfolio_or_404

router = APIRouter(prefix="/ai", tags=["ai"])
prouter = APIRouter(prefix="/portfolios/{portfolio_id}/ai", tags=["ai"])

DEFAULT_MODEL_KEY = "ai.default_model"


def _manager(request: Request):
    return request.app.state.model_manager


def _default_model(session: Session, request: Request, portfolio=None) -> str:
    if portfolio is not None and portfolio.ai_default_model:
        return portfolio.ai_default_model
    setting = session.get(AppSetting, DEFAULT_MODEL_KEY)
    if setting and setting.value:
        return setting.value
    manager = _manager(request)
    if manager.runtime.model_id:  # something is already loaded — use it
        return manager.runtime.model_id
    for model_id in CATALOG:
        if manager.installed(model_id):
            return model_id
    return ""


# ---- model management ----

@router.get("/hardware")
def hardware(request: Request):
    hw = detect_hardware()
    hw["runtime_kind"] = _manager(request).runtime_kind
    return hw


@router.get("/models")
def models(request: Request, session: Session = Depends(get_db)):
    setting = session.get(AppSetting, DEFAULT_MODEL_KEY)
    return {
        "models": _manager(request).catalog_view(),
        "loaded": _manager(request).runtime.model_id,
        "default_model": setting.value if setting else "",
        "disclaimer": DISCLAIMER,
    }


@router.post("/models/{model_id}/install", status_code=202)
async def install_model(model_id: str, request: Request, session: Session = Depends(get_db)):
    manager = _manager(request)
    if model_id not in CATALOG:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")
    if manager.installed(model_id):
        return {"status": "installed"}
    audit(session, getattr(request.state, "username", "local"), "ai.model_install", model_id)
    session.commit()
    try:
        await run_in_threadpool(manager.download, model_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Download failed: {exc}")
    return {"status": "installed"}


@router.delete("/models/{model_id}", status_code=204)
def remove_model(model_id: str, request: Request, session: Session = Depends(get_db)):
    if model_id not in CATALOG:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")
    if not _manager(request).remove(model_id):
        raise HTTPException(status_code=404, detail="Model not installed")
    audit(session, getattr(request.state, "username", "local"), "ai.model_remove", model_id)
    session.commit()


@router.post("/models/{model_id}/load")
async def load_model(model_id: str, request: Request):
    manager = _manager(request)
    try:
        await run_in_threadpool(manager.load, model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Load failed: {exc}")
    return {"loaded": model_id}


@router.post("/models/{model_id}/benchmark")
async def benchmark_model(model_id: str, request: Request):
    manager = _manager(request)
    if not manager.installed(model_id):
        raise HTTPException(status_code=409, detail="Model not installed")
    try:
        return await run_in_threadpool(manager.benchmark, model_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {exc}")


class DefaultModelBody(BaseModel):
    model_id: str


@router.put("/default-model")
def set_default_model(body: DefaultModelBody, request: Request, session: Session = Depends(get_db)):
    if body.model_id and body.model_id not in CATALOG:
        raise HTTPException(status_code=404, detail=f"Unknown model: {body.model_id}")
    setting = session.get(AppSetting, DEFAULT_MODEL_KEY)
    if setting is None:
        setting = AppSetting(key=DEFAULT_MODEL_KEY)
        session.add(setting)
    setting.value = body.model_id
    session.commit()
    return {"default_model": body.model_id}


# ---- assistant + recommendations (per portfolio) ----

class AnalyzeBody(BaseModel):
    model_id: str | None = None


class AiSettingsBody(BaseModel):
    ai_auto_execute: bool | None = None
    ai_max_trade_notional: Decimal | None = Field(default=None, gt=0)
    ai_max_trades_per_day: int | None = Field(default=None, ge=1, le=50)
    ai_default_model: str | None = None


@prouter.post("/analyze")
async def analyze(
    portfolio_id: str,
    body: AnalyzeBody,
    request: Request,
    session: Session = Depends(get_db),
    market=Depends(get_market),
    bus=Depends(get_bus),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    manager = _manager(request)
    model_id = body.model_id or _default_model(session, request, portfolio)
    if not model_id:
        raise HTTPException(
            status_code=409,
            detail="No model available — install one from the Models page first",
        )
    if manager.runtime.model_id != model_id:
        if not manager.installed(model_id) and manager.runtime_kind != "FakeRuntime":
            raise HTTPException(status_code=409, detail=f"Model {model_id} is not installed")
        try:
            await run_in_threadpool(manager.load, model_id) if manager.runtime_kind != "FakeRuntime" else manager.runtime.load(model_id, None)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Model load failed: {exc}")
    try:
        result = await run_in_threadpool(
            analyze_portfolio, session, portfolio, market, manager.runtime, model_id, bus
        )
        session.commit()
    except MarketDataError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc))
    return result


@prouter.get("/recommendations")
def list_recommendations(
    portfolio_id: str,
    status: RecommendationStatus | None = None,
    limit: int = 50,
    session: Session = Depends(get_db),
):
    get_portfolio_or_404(session, portfolio_id)
    query = (
        select(Recommendation)
        .where(Recommendation.portfolio_id == portfolio_id)
        .order_by(Recommendation.created_at.desc())
        .limit(min(limit, 200))
    )
    if status:
        query = query.where(Recommendation.status == status)
    return [rec_view(r) for r in session.scalars(query).all()]


@prouter.post("/recommendations/{rec_id}/approve")
def approve_recommendation(
    portfolio_id: str,
    rec_id: str,
    request: Request,
    session: Session = Depends(get_db),
    market=Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    rec = session.get(Recommendation, rec_id)
    if rec is None or rec.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.status != RecommendationStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Recommendation is {rec.status.value}")
    outcome = try_execute(session, portfolio, rec, market, auto=False)
    audit(session, getattr(request.state, "username", "local"),
          "ai.recommendation_approved", f"{rec.action.value} {rec.symbol}")
    session.commit()
    return {"recommendation": rec_view(rec), "outcome": outcome}


@prouter.post("/recommendations/{rec_id}/reject")
def reject_recommendation(
    portfolio_id: str, rec_id: str, request: Request, session: Session = Depends(get_db)
):
    get_portfolio_or_404(session, portfolio_id)
    rec = session.get(Recommendation, rec_id)
    if rec is None or rec.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.status != RecommendationStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Recommendation is {rec.status.value}")
    rec.status = RecommendationStatus.REJECTED
    rec.decided_at = datetime.now(timezone.utc)
    session.commit()
    return rec_view(rec)


@prouter.get("/settings")
def get_ai_settings(portfolio_id: str, session: Session = Depends(get_db)):
    p = get_portfolio_or_404(session, portfolio_id)
    return {
        "ai_auto_execute": p.ai_auto_execute,
        "ai_max_trade_notional": str(p.ai_max_trade_notional),
        "ai_max_trades_per_day": p.ai_max_trades_per_day,
        "ai_default_model": p.ai_default_model,
    }


@prouter.put("/settings")
def update_ai_settings(
    portfolio_id: str,
    body: AiSettingsBody,
    request: Request,
    session: Session = Depends(get_db),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    if body.ai_default_model and body.ai_default_model not in CATALOG:
        raise HTTPException(status_code=404, detail="Unknown model")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(portfolio, field, value)
    audit(session, getattr(request.state, "username", "local"),
          "ai.settings", portfolio.name,
          json.dumps(body.model_dump(exclude_none=True), default=str))
    session.commit()
    return get_ai_settings(portfolio_id, session)