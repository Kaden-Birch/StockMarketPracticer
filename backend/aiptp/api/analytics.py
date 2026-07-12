from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.service import diversification, risk_metrics, trade_records, value_history
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..reports.export import to_csv, to_json, to_markdown
from ..storage.models import Transaction
from .deps import get_db, get_market, get_portfolio_or_404

router = APIRouter(prefix="/portfolios/{portfolio_id}", tags=["analytics"])


@router.get("/value-history")
def get_value_history(
    portfolio_id: str,
    range: str = "1Y",
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    try:
        return value_history(session, portfolio, market, range)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/analytics")
def get_analytics(
    portfolio_id: str,
    range: str = "1Y",
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    view = value_portfolio(portfolio, market)
    try:
        history = value_history(session, portfolio, market, range)
        risk = risk_metrics(history["points"])
    except MarketDataError as exc:
        history = None
        risk = {"error": str(exc)}
    return {
        "portfolio_id": portfolio.id,
        "range": range.upper(),
        "risk": risk,
        "records": trade_records(session, portfolio),
        "diversification": diversification(view),
    }


@router.get("/export")
def export_portfolio(
    portfolio_id: str,
    format: str = "csv",
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    view = value_portfolio(portfolio, market)
    txns = session.scalars(
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.executed_at)
    ).all()
    fmt = format.lower()
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in portfolio.name)[:40]
    if fmt == "csv":
        return Response(
            to_csv(view, txns),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'},
        )
    analytics = None
    try:
        analytics = {
            "risk": risk_metrics(value_history(session, portfolio, market, "1Y")["points"]),
            "records": trade_records(session, portfolio),
            "diversification": diversification(view),
        }
    except MarketDataError:
        pass
    if fmt == "json":
        return Response(
            to_json(view, txns, analytics),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.json"'},
        )
    if fmt in ("md", "markdown"):
        return Response(
            to_markdown(view, txns, analytics),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
        )
    raise HTTPException(status_code=422, detail="format must be csv, json, or md")
