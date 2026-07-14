"""Interactive simulations (roadmap 10.5).

Three are pure, clearly-labeled educational math (compound growth,
diversification, allocation risk) — deterministic formulas with stated
assumptions, not market forecasts. The crash simulator is different: it
replays a REAL historical benchmark path (from the scenario catalog
windows) against a chosen starting value, honoring the platform rule that
market data is never fabricated.
"""

from decimal import Decimal

from ..marketdata.service import MarketDataService
from ..scenario.catalog import SCENARIOS

# Long-run planning assumptions for the allocation simulator — documented
# in the response, deliberately round, and clearly not predictions.
ALLOCATION_ASSUMPTIONS = {
    "stocks": {"return": 0.07, "volatility": 0.16},
    "bonds": {"return": 0.03, "volatility": 0.06},
    "cash": {"return": 0.01, "volatility": 0.0},
}


def compound_growth(principal: float, monthly: float, annual_rate_pct: float,
                    years: int) -> dict:
    """Deterministic compounding: month-by-month value plus contributed vs
    earned split."""
    years = max(1, min(years, 60))
    r = annual_rate_pct / 100 / 12
    value = principal
    contributed = principal
    points = []
    for m in range(years * 12 + 1):
        if m > 0:
            value = value * (1 + r) + monthly
            contributed += monthly
        if m % 12 == 0:
            points.append({"year": m // 12, "value": round(value, 2),
                           "contributed": round(contributed, 2),
                           "earned": round(value - contributed, 2)})
    return {
        "assumption": f"steady {annual_rate_pct}%/year, compounded monthly — "
                      "real markets are volatile around any average",
        "points": points,
        "final_value": points[-1]["value"],
        "total_contributed": points[-1]["contributed"],
        "growth_share_pct": round(points[-1]["earned"] / points[-1]["value"] * 100, 1)
        if points[-1]["value"] > 0 else 0,
    }


def diversification_sim(single_volatility_pct: float = 40.0,
                        correlation: float = 0.3) -> dict:
    """Portfolio volatility vs number of equally-weighted holdings:
    σ_p = σ √(1/n + ρ(1−1/n)). Shows what diversifies away and what
    (systematic risk) never does."""
    correlation = min(max(correlation, 0.0), 1.0)
    sigma = single_volatility_pct / 100
    points = []
    for n in range(1, 31):
        var = sigma * sigma * (1 / n + correlation * (1 - 1 / n))
        points.append({"holdings": n, "portfolio_volatility_pct":
                       round(var ** 0.5 * 100, 2)})
    floor = round(sigma * (correlation ** 0.5) * 100, 2)
    return {
        "assumption": f"each stock ~{single_volatility_pct}% volatility, "
                      f"average pairwise correlation {correlation}",
        "points": points,
        "systematic_floor_pct": floor,
        "lesson": (f"Risk falls fast to ~{floor}% and then stops: that floor "
                   "is market risk, which no amount of stock-picking "
                   "diversifies away."),
    }


def risk_allocation_sim(stocks_pct: float, bonds_pct: float,
                        cash_pct: float, years: int = 20,
                        start: float = 10000.0) -> dict:
    """Expected path plus a ±1σ and ±2σ cone for an allocation, from the
    documented long-run assumptions. Percentile math, not a forecast."""
    total = stocks_pct + bonds_pct + cash_pct
    if total <= 0:
        raise ValueError("Allocation must sum to a positive number")
    w = {k: v / total for k, v in
         (("stocks", stocks_pct), ("bonds", bonds_pct), ("cash", cash_pct))}
    mu = sum(w[k] * ALLOCATION_ASSUMPTIONS[k]["return"] for k in w)
    # correlation between classes ignored on purpose (stated) — keep it simple
    sigma = sum(w[k] * ALLOCATION_ASSUMPTIONS[k]["volatility"] for k in w)
    years = max(1, min(years, 50))
    points = []
    for t in range(years + 1):
        expected = start * (1 + mu) ** t
        spread = sigma * (t ** 0.5)
        points.append({
            "year": t,
            "expected": round(expected, 2),
            "optimistic": round(expected * (1 + spread), 2),      # ~+1σ
            "pessimistic": round(expected * max(0.05, 1 - spread), 2),  # ~-1σ
            "severe": round(expected * max(0.02, 1 - 2 * spread), 2),   # ~-2σ
        })
    return {
        "assumptions": {"weights": w, "expected_return_pct": round(mu * 100, 2),
                        "volatility_pct": round(sigma * 100, 2),
                        "note": "long-run planning assumptions, not forecasts; "
                                "class correlations simplified to 1"},
        "points": points,
    }


def crash_sim(market: MarketDataService, scenario_id: str,
              starting_value: float) -> dict:
    """Apply a REAL historical benchmark path to a starting value: what a
    2008 (or dot-com, or COVID) would have done to this much money in the
    benchmark, including the recovery — genuine closes, nothing simulated."""
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    bars = market.get_history_window(
        scenario.benchmark, scenario.start_ts, scenario.end_ts).bars
    if not bars:
        raise ValueError("Historical data unavailable")
    base = bars[0].close
    points = [{"ts": b.ts, "value": round(starting_value * b.close / base, 2)}
              for b in bars if b.close]
    values = [p["value"] for p in points]
    peak = trough_after_peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd
            trough_after_peak = v
    return {
        "scenario": scenario.name,
        "period": scenario.period,
        "benchmark": scenario.benchmark,
        "source": "real historical closes",
        "points": points,
        "worst_value": trough_after_peak,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "end_value": values[-1],
        "recovered": values[-1] >= starting_value,
    }
