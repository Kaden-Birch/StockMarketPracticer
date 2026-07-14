"""AI investor profiles (roadmap 9.2) and the personality system (9.4).

Each profile is an investing philosophy: a curated real-ticker universe, a
deterministic selection method over real quotes/history, and a personality
(risk tolerance, patience, confidence, conviction, adaptability — all 0-1).
Difficulty (9.3) scales the personality and the quality of execution; it
never fabricates data. The `value` method uses a price-based proxy
(distance below the 52-week high) because the market-data layer carries no
fundamentals yet — the profile description says so."""

from dataclasses import dataclass, field

DIFFICULTIES = ("beginner", "intermediate", "advanced", "expert")

# Execution-quality scaling by difficulty (9.3). mistake_rate is the share
# of cycles where the AI deliberately executes a documented common mistake.
DIFFICULTY_MODS: dict[str, dict] = {
    "beginner": {"mistake_rate": 0.5, "history_range": "1mo",
                 "rebalance_drift": 0.25, "explain": True},
    "intermediate": {"mistake_rate": 0.15, "history_range": "3mo",
                     "rebalance_drift": 0.15, "explain": False},
    "advanced": {"mistake_rate": 0.0, "history_range": "6mo",
                 "rebalance_drift": 0.10, "explain": False},
    "expert": {"mistake_rate": 0.0, "history_range": "1y",
               "rebalance_drift": 0.05, "explain": False},
}


@dataclass(frozen=True)
class ProfileSpec:
    id: str
    name: str
    philosophy: str
    universe: tuple[str, ...]
    method: str  # equal_weight | momentum | growth | value_proxy | quant | market_timer | chase
    target_positions: int
    cash_floor: float  # fraction kept in cash (risk management)
    traits: dict = field(default_factory=dict)


PROFILES: dict[str, ProfileSpec] = {p.id: p for p in [
    ProfileSpec(
        id="conservative", name="Conservative Investor",
        philosophy="Stability first: broad ETFs, dividend blue chips, low "
                   "volatility, a permanent cash cushion.",
        universe=("SPY", "KO", "PG", "JNJ", "WMT", "MCD", "PEP", "COST"),
        method="equal_weight", target_positions=6, cash_floor=0.25,
        traits={"risk_tolerance": 0.2, "patience": 0.9, "confidence": 0.5,
                "conviction": 0.4, "adaptability": 0.3},
    ),
    ProfileSpec(
        id="growth", name="Growth Investor",
        philosophy="Technology and high-growth names; pays up for momentum "
                   "in earnings power.",
        universe=("NVDA", "MSFT", "AMZN", "GOOGL", "META", "AMD", "NFLX",
                  "CRM", "SHOP", "TSLA"),
        method="growth", target_positions=5, cash_floor=0.05,
        traits={"risk_tolerance": 0.8, "patience": 0.6, "confidence": 0.8,
                "conviction": 0.7, "adaptability": 0.5},
    ),
    ProfileSpec(
        id="value", name="Value Investor",
        philosophy="Buys quality names trading far below their 52-week high "
                   "(price-based value proxy — no fundamentals feed yet) and "
                   "waits.",
        universe=("JPM", "BAC", "XOM", "CVX", "IBM", "INTC", "VZ", "T",
                  "GM", "F"),
        method="value_proxy", target_positions=6, cash_floor=0.10,
        traits={"risk_tolerance": 0.5, "patience": 1.0, "confidence": 0.6,
                "conviction": 0.9, "adaptability": 0.2},
    ),
    ProfileSpec(
        id="dividend", name="Dividend Investor",
        philosophy="Income and dividend growth: aristocrats, utilities, "
                   "energy majors.",
        universe=("KO", "PG", "JNJ", "XOM", "T", "VZ", "MO", "O", "ED",
                  "PEP"),
        method="equal_weight", target_positions=7, cash_floor=0.10,
        traits={"risk_tolerance": 0.3, "patience": 0.95, "confidence": 0.5,
                "conviction": 0.6, "adaptability": 0.2},
    ),
    ProfileSpec(
        id="technical", name="Technical Trader",
        philosophy="Pure price action: rides 3-month momentum, cuts losers, "
                   "no opinions about businesses.",
        universe=("AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "AMD", "META",
                  "GOOGL", "SPY", "QQQ"),
        method="momentum", target_positions=4, cash_floor=0.10,
        traits={"risk_tolerance": 0.7, "patience": 0.2, "confidence": 0.7,
                "conviction": 0.3, "adaptability": 0.8},
    ),
    ProfileSpec(
        id="quant", name="Quant Investor",
        philosophy="Statistics over stories: ranks the universe by return "
                   "per unit of volatility and holds the best scores.",
        universe=("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM",
                  "JNJ", "PG", "WMT", "KO", "META"),
        method="quant", target_positions=6, cash_floor=0.05,
        traits={"risk_tolerance": 0.6, "patience": 0.7, "confidence": 0.9,
                "conviction": 0.5, "adaptability": 0.6},
    ),
    ProfileSpec(
        id="market_timer", name="Market Timer",
        philosophy="All-in or all-out: holds the index while it trades above "
                   "its trend, hides in cash below it.",
        universe=("SPY",),
        method="market_timer", target_positions=1, cash_floor=0.0,
        traits={"risk_tolerance": 0.5, "patience": 0.4, "confidence": 0.8,
                "conviction": 0.8, "adaptability": 0.9},
    ),
    ProfileSpec(
        id="beginner", name="Beginner Investor",
        philosophy="Educational opponent: chases whatever just went up, "
                   "panic-sells dips, over-concentrates — and explains each "
                   "mistake so you can learn from it.",
        universe=("AAPL", "TSLA", "NVDA", "AMZN", "META", "AMD", "COIN",
                  "PLTR"),
        method="chase", target_positions=3, cash_floor=0.0,
        traits={"risk_tolerance": 0.9, "patience": 0.05, "confidence": 0.9,
                "conviction": 0.2, "adaptability": 0.1},
    ),
    ProfileSpec(
        id="index", name="Index Fund",
        philosophy="Owns the whole market and never trades. The benchmark "
                   "everyone is really competing against (roadmap 9.9).",
        universe=("SPY",),
        method="equal_weight", target_positions=1, cash_floor=0.0,
        traits={"risk_tolerance": 0.5, "patience": 1.0, "confidence": 0.5,
                "conviction": 1.0, "adaptability": 0.0},
    ),
]}


def effective_traits(profile: ProfileSpec, difficulty: str) -> dict:
    """Personality scaled by difficulty (9.3/9.4): lower difficulty erodes
    patience and discipline; expert sharpens them."""
    scale = {"beginner": 0.6, "intermediate": 1.0,
             "advanced": 1.1, "expert": 1.25}[difficulty]
    out = {}
    for key, val in profile.traits.items():
        if key in ("patience", "conviction", "adaptability"):
            out[key] = round(min(1.0, val * scale), 2)
        else:
            out[key] = val
    return out


def profiles_view() -> list[dict]:
    return [
        {"id": p.id, "name": p.name, "philosophy": p.philosophy,
         "universe": list(p.universe), "method": p.method,
         "traits": p.traits, "difficulties": list(DIFFICULTIES)}
        for p in PROFILES.values()
    ]
