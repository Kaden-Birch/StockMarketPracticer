"""Portfolio mandates (roadmap 8.4): named rule sets a portfolio promises to
follow. Compliance is measured and reported — the platform never force-
liquidates. Rules only use data we actually have (valuations, the value
series, the dividend transaction log); the technology mandate uses a curated
ticker list because the market-data layer has no sector fundamentals yet —
documented, not fabricated."""

from datetime import timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.service import diversification, risk_metrics, value_history
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import Portfolio, Transaction, TransactionKind, utcnow

MANDATE_IDS = ("retirement", "growth", "dividend", "technology")

MANDATE_INFO = {
    "retirement": {
        "name": "Retirement Fund",
        "summary": "Capital preservation: low volatility, real diversification, "
                   "shallow drawdowns.",
    },
    "growth": {
        "name": "Growth Fund",
        "summary": "Stay invested for growth: high equity exposure, accepting "
                   "higher risk.",
    },
    "dividend": {
        "name": "Dividend Fund",
        "summary": "Own income producers: the portfolio must actually collect "
                   "dividends.",
    },
    "technology": {
        "name": "Technology Fund",
        "summary": "Sector restriction: hold only technology names (curated "
                    "list until real sector data lands).",
    },
}

# Curated technology tickers (no sector fundamentals in the MDAL yet).
TECH_TICKERS = {
    "AAPL", "MSFT", "NVDA", "AMD", "INTC", "GOOGL", "GOOG", "META", "AMZN",
    "NFLX", "CRM", "ORCL", "ADBE", "CSCO", "IBM", "QCOM", "TXN", "AVGO",
    "MU", "TSM", "ASML", "NOW", "SHOP", "PLTR", "SNOW", "UBER", "SMCI",
    "PANW", "ANET", "DELL", "HPQ", "SAP", "INTU", "AMAT", "LRCX", "KLAC",
}


def rule(rule_id: str, label: str, status: str, value: Any, threshold: str) -> dict:
    return {"id": rule_id, "label": label, "status": status,
            "value": value, "threshold": threshold}


def compliance(session: Session, portfolio: Portfolio,
               market: MarketDataService) -> dict:
    """Evaluate the portfolio against its mandate. status per rule:
    ok | violation | pending (not enough history to judge)."""
    mandate = portfolio.mandate
    if mandate not in MANDATE_IDS:
        return {"mandate": "", "rules": [], "compliant": None}

    try:
        view = value_portfolio(portfolio, market)
    except MarketDataError:
        return {"mandate": mandate, "rules": [], "compliant": None,
                "note": "Market data unavailable — compliance not evaluated"}

    created = portfolio.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_days = (utcnow() - created).days
    rules: list[dict] = []

    risk: dict = {}
    if mandate in ("retirement",):
        try:
            points = value_history(session, portfolio, market, "1Y")["points"]
            risk = risk_metrics(points)
        except MarketDataError:
            risk = {}

    if mandate == "retirement":
        vol = risk.get("volatility")
        rules.append(rule(
            "low_volatility", "Annualized volatility below 25%",
            "pending" if vol is None else ("ok" if vol < 25 else "violation"),
            vol, "< 25%"))
        div = diversification(view).get("score")
        rules.append(rule(
            "diversified", "Diversification score at least 60",
            "pending" if div is None else ("ok" if div >= 60 else "violation"),
            div, ">= 60"))
        dd = risk.get("max_drawdown")
        rules.append(rule(
            "shallow_drawdown", "Max drawdown no worse than -20%",
            "pending" if dd is None else ("ok" if dd > -20 else "violation"),
            dd, "> -20%"))

    elif mandate == "growth":
        total = Decimal(view["total_value"])
        invested_pct = (float((total - Decimal(view["cash_balance"])) / total * 100)
                        if total > 0 else 0.0)
        rules.append(rule(
            "fully_invested", "At least 80% of capital invested",
            "ok" if invested_pct >= 80 else (
                "pending" if age_days < 7 else "violation"),
            round(invested_pct, 1), ">= 80%"))
        positions = len(view["holdings"])
        rules.append(rule(
            "not_a_single_bet", "At least 3 positions",
            "ok" if positions >= 3 else (
                "pending" if age_days < 7 else "violation"),
            positions, ">= 3"))

    elif mandate == "dividend":
        income = session.scalar(
            select(Transaction).where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.kind == TransactionKind.DIVIDEND,
            ).limit(1))
        rules.append(rule(
            "collects_dividends", "Portfolio has collected dividend income",
            "ok" if income is not None else (
                "pending" if age_days < 90 else "violation"),
            "yes" if income is not None else "none yet",
            "dividend income within the first 90 days"))
        positions = len(view["holdings"])
        rules.append(rule(
            "invested", "Holds income-producing positions",
            "ok" if positions >= 1 else (
                "pending" if age_days < 7 else "violation"),
            positions, ">= 1 position"))

    elif mandate == "technology":
        offenders = [h["symbol"] for h in view["holdings"]
                     if h["symbol"] not in TECH_TICKERS]
        rules.append(rule(
            "tech_only", "All holdings on the technology list",
            "ok" if not offenders else "violation",
            offenders or "all compliant", "0 non-tech holdings"))

    statuses = [r["status"] for r in rules]
    compliant = (all(s == "ok" for s in statuses)
                 if statuses and "pending" not in statuses else None)
    if statuses and "violation" in statuses:
        compliant = False
    return {"mandate": mandate, "info": MANDATE_INFO[mandate],
            "rules": rules, "compliant": compliant}
