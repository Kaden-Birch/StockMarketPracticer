"""Scenario catalog (roadmap 8.2): real historical periods, replayed from
REAL daily bars (PRD: no fabricated market data — ever). Universes contain
tickers that still trade today, because providers only serve surviving
listings; each description says so, since surviving-company universes are
gentler than the era actually was (survivorship bias)."""

from dataclasses import dataclass
from datetime import datetime, timezone


def _ts(y: int, m: int, d: int) -> int:
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    period: str
    description: str
    start_ts: int
    end_ts: int
    benchmark: str
    universe: tuple[str, ...]
    starting_cash: str
    difficulty: str  # relaxed | standard | brutal


SCENARIOS: dict[str, Scenario] = {s.id: s for s in [
    Scenario(
        id="dotcom_crash",
        name="Dot-com bubble & crash",
        period="Jan 1999 – Oct 2002",
        description=(
            "Ride the final melt-up of the internet bubble, then survive the "
            "78% Nasdaq collapse. You start in January 1999 with no knowledge "
            "of what March 2000 brings. Universe limited to companies that "
            "survived the era (the real thing was harsher — many names went "
            "to zero)."),
        start_ts=_ts(1999, 1, 4), end_ts=_ts(2002, 10, 31),
        benchmark="SPY",
        universe=("MSFT", "INTC", "CSCO", "ORCL", "IBM", "AAPL", "QCOM", "AMZN"),
        starting_cash="100000", difficulty="brutal",
    ),
    Scenario(
        id="gfc_2008",
        name="2008 financial crisis",
        period="Jan 2007 – Dec 2009",
        description=(
            "From peak housing euphoria through the Lehman weekend to the "
            "March 2009 bottom and the first year of recovery. Banks, energy "
            "and blue chips — decide what to hold when everything correlates "
            "to one."),
        start_ts=_ts(2007, 1, 3), end_ts=_ts(2009, 12, 31),
        benchmark="SPY",
        universe=("JPM", "BAC", "C", "GS", "XOM", "GE", "WMT", "MSFT", "AAPL"),
        starting_cash="100000", difficulty="brutal",
    ),
    Scenario(
        id="covid_crash",
        name="COVID crash & rebound",
        period="Jan 2020 – Dec 2020",
        description=(
            "The fastest 30% drawdown in history followed by the fastest "
            "recovery. Airlines and cruise lines craterd while big tech "
            "soared — one year that tested every investing instinct."),
        start_ts=_ts(2020, 1, 2), end_ts=_ts(2020, 12, 31),
        benchmark="SPY",
        universe=("AAPL", "MSFT", "AMZN", "NVDA", "DAL", "CCL", "WMT", "JNJ"),
        starting_cash="100000", difficulty="standard",
    ),
    Scenario(
        id="inflation_cycle",
        name="Inflation & rate-hike cycle",
        period="Jan 2021 – Jun 2023",
        description=(
            "Stimulus-era froth, then the fastest rate-hiking cycle in four "
            "decades. Growth deflates, energy rips, and 'safe' bonds have "
            "their worst year ever. Balance growth against real assets."),
        start_ts=_ts(2021, 1, 4), end_ts=_ts(2023, 6, 30),
        benchmark="SPY",
        universe=("AAPL", "MSFT", "NVDA", "XOM", "CVX", "KO", "PG"),
        starting_cash="100000", difficulty="standard",
    ),
    Scenario(
        id="tech_boom",
        name="2016-2019 technology boom",
        period="Jan 2016 – Dec 2019",
        description=(
            "Four years of a roaring tech bull market — cloud, chips and "
            "streaming. Easy mode? Beating the index while it compounds 15% "
            "a year is harder than it looks."),
        start_ts=_ts(2016, 1, 4), end_ts=_ts(2019, 12, 31),
        benchmark="QQQ",
        universe=("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "NFLX", "AMD"),
        starting_cash="100000", difficulty="relaxed",
    ),
]}


def catalog_view() -> list[dict]:
    return [
        {"id": s.id, "name": s.name, "period": s.period,
         "description": s.description, "benchmark": s.benchmark,
         "universe": list(s.universe), "starting_cash": s.starting_cash,
         "difficulty": s.difficulty}
        for s in SCENARIOS.values()
    ]
