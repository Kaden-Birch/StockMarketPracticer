import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..automation.conditions import validate_trigger
from ..security.audit import audit
from ..storage.models import AutomationRule, RuleActionType, RuleFire
from .deps import get_db, get_portfolio_or_404

router = APIRouter(prefix="/portfolios/{portfolio_id}/rules", tags=["automation"])


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trigger: dict
    action_type: RuleActionType
    action_params: dict = {}
    cooldown_seconds: int = Field(default=3600, ge=0)
    max_fires_per_day: int = Field(default=5, ge=1, le=100)
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    trigger: dict | None = None
    action_type: RuleActionType | None = None
    action_params: dict | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0)
    max_fires_per_day: int | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None


def _validate_action(action_type: RuleActionType, params: dict) -> None:
    if action_type in (RuleActionType.BUY, RuleActionType.SELL):
        if not params.get("symbol"):
            raise HTTPException(status_code=422, detail=f"{action_type.value} action requires a symbol")
        sizing = [k for k in ("quantity", "notional", "percent") if params.get(k)]
        if len(sizing) != 1:
            raise HTTPException(
                status_code=422,
                detail=f"{action_type.value} action requires exactly one of quantity, notional, percent",
            )
    if action_type == RuleActionType.REBALANCE and not params.get("targets"):
        raise HTTPException(status_code=422, detail="REBALANCE action requires targets")


def _rule_view(rule: AutomationRule) -> dict:
    return {
        "id": rule.id,
        "portfolio_id": rule.portfolio_id,
        "name": rule.name,
        "trigger": json.loads(rule.trigger),
        "action_type": rule.action_type.value,
        "action_params": json.loads(rule.action_params or "{}"),
        "enabled": rule.enabled,
        "cooldown_seconds": rule.cooldown_seconds,
        "max_fires_per_day": rule.max_fires_per_day,
        "last_fired_at": rule.last_fired_at.isoformat() if rule.last_fired_at else None,
        "fire_count": rule.fire_count,
        "created_at": rule.created_at.isoformat(),
    }


@router.post("", status_code=201)
def create_rule(
    portfolio_id: str,
    body: RuleCreate,
    request: Request,
    session: Session = Depends(get_db),
):
    get_portfolio_or_404(session, portfolio_id)
    try:
        validate_trigger(body.trigger)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _validate_action(body.action_type, body.action_params)
    rule = AutomationRule(
        portfolio_id=portfolio_id,
        name=body.name,
        trigger=json.dumps(body.trigger),
        action_type=body.action_type,
        action_params=json.dumps(body.action_params),
        cooldown_seconds=body.cooldown_seconds,
        max_fires_per_day=body.max_fires_per_day,
        enabled=body.enabled,
    )
    session.add(rule)
    audit(session, getattr(request.state, "username", "local"), "rule.create", rule.name)
    session.commit()
    return _rule_view(rule)


@router.get("")
def list_rules(portfolio_id: str, session: Session = Depends(get_db)):
    get_portfolio_or_404(session, portfolio_id)
    rules = session.scalars(
        select(AutomationRule)
        .where(AutomationRule.portfolio_id == portfolio_id)
        .order_by(AutomationRule.created_at)
    ).all()
    return [_rule_view(r) for r in rules]


@router.patch("/{rule_id}")
def update_rule(
    portfolio_id: str,
    rule_id: str,
    body: RuleUpdate,
    request: Request,
    session: Session = Depends(get_db),
):
    get_portfolio_or_404(session, portfolio_id)
    rule = session.get(AutomationRule, rule_id)
    if rule is None or rule.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    if body.trigger is not None:
        try:
            validate_trigger(body.trigger)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        rule.trigger = json.dumps(body.trigger)
        rule.armed = True
    effective_action = body.action_type or rule.action_type
    if body.action_params is not None:
        _validate_action(effective_action, body.action_params)
        rule.action_params = json.dumps(body.action_params)
    if body.action_type is not None:
        rule.action_type = body.action_type
    for field in ("name", "cooldown_seconds", "max_fires_per_day", "enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(rule, field, value)
    audit(session, getattr(request.state, "username", "local"), "rule.update", rule.name)
    session.commit()
    return _rule_view(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    portfolio_id: str, rule_id: str, request: Request, session: Session = Depends(get_db)
):
    get_portfolio_or_404(session, portfolio_id)
    rule = session.get(AutomationRule, rule_id)
    if rule is None or rule.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    audit(session, getattr(request.state, "username", "local"), "rule.delete", rule.name)
    session.delete(rule)
    session.commit()


@router.get("/{rule_id}/fires")
def list_fires(
    portfolio_id: str, rule_id: str, limit: int = 50, session: Session = Depends(get_db)
):
    get_portfolio_or_404(session, portfolio_id)
    rule = session.get(AutomationRule, rule_id)
    if rule is None or rule.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    fires = session.scalars(
        select(RuleFire)
        .where(RuleFire.rule_id == rule_id)
        .order_by(RuleFire.fired_at.desc())
        .limit(min(limit, 200))
    ).all()
    return [
        {"id": f.id, "fired_at": f.fired_at.isoformat(), "result": f.result, "detail": f.detail}
        for f in fires
    ]
