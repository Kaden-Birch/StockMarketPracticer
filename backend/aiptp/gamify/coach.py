"""AI Learning Coach foundation (roadmap 6.10): deterministic observations
about the portfolio paired with learning suggestions. Reading a suggestion
earns education XP; richer lesson content arrives with M8/M10."""

from decimal import Decimal

from sqlalchemy.orm import Session

from ..analytics.service import diversification, trade_records
from ..marketdata.service import MarketDataService
from ..storage.models import Portfolio


def coach_observations(
    session: Session, portfolio: Portfolio, market: MarketDataService
) -> list[dict]:
    from ..portfolio.service import value_portfolio

    view = value_portfolio(portfolio, market)
    div = diversification(view)
    records = trade_records(session, portfolio)
    out: list[dict] = []

    weights = {k: v for k, v in div["weights"].items() if k != "CASH"}
    if weights:
        top_symbol, top_weight = max(weights.items(), key=lambda kv: kv[1])
        if top_weight > 40:
            out.append({
                "id": "concentration",
                "observation": f"You are heavily concentrated: {top_symbol} is "
                               f"{top_weight}% of this portfolio.",
                "suggestion": "Would you like to learn about diversification and "
                              "position sizing?",
                "topic": "diversification",
            })
    if div["score"] is not None and div["score"] < 40 and len(view["holdings"]) >= 1:
        out.append({
            "id": "low_diversification",
            "observation": f"The diversification score is {div['score']} — most of the "
                           "portfolio's fate rides on very few positions.",
            "suggestion": "Spreading capital across sectors reduces single-company risk.",
            "topic": "diversification",
        })
    cash_pct = div["weights"].get("CASH", 0)
    if cash_pct > 80 and len(view["holdings"]) > 0:
        out.append({
            "id": "cash_drag",
            "observation": f"{cash_pct}% of the portfolio sits in cash.",
            "suggestion": "Uninvested cash avoids risk but also avoids returns — "
                          "dollar-cost averaging is one way to deploy it gradually.",
            "topic": "dollar_cost_averaging",
        })
    avg_days = records.get("avg_holding_days")
    if avg_days is not None and avg_days < 7 and (records.get("closed_trades") or 0) >= 3:
        out.append({
            "id": "short_holding",
            "observation": f"Your average holding period is {avg_days} days.",
            "suggestion": "Frequent trading usually hurts returns — long holding "
                          "periods let compounding work.",
            "topic": "long_term_investing",
        })
    win_rate = records.get("win_rate")
    if win_rate is not None and win_rate < 40 and (records.get("closed_trades") or 0) >= 5:
        out.append({
            "id": "low_win_rate",
            "observation": f"Your win rate is {win_rate}% over "
                           f"{records['closed_trades']} closed trades.",
            "suggestion": "Backtesting a rule-based strategy can separate luck from edge.",
            "topic": "backtesting",
        })
    if not out:
        out.append({
            "id": "healthy",
            "observation": "No red flags in this portfolio right now.",
            "suggestion": "Keep the streak going — reviewing your allocation weekly "
                          "is a great habit.",
            "topic": "portfolio_review",
        })
    for item in out:
        item["disclaimer"] = "Educational guidance, not financial advice."
    return out
