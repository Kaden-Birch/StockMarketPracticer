from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass
class Quote:
    symbol: str
    price: Decimal
    previous_close: Decimal | None
    currency: str
    market_state: str  # e.g. REGULAR, CLOSED, PRE, POST
    as_of: datetime
    provider: str  # provenance — no data without a source (PRD §10)


@dataclass
class Bar:
    ts: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: int | None


@dataclass
class History:
    symbol: str
    range: str
    interval: str
    currency: str
    bars: list[Bar] = field(default_factory=list)
    provider: str = ""
    fetched_at: datetime | None = None


@dataclass
class SymbolMatch:
    symbol: str
    name: str
    exchange: str
    type: str


@dataclass
class CorporateAction:
    symbol: str
    kind: str  # DIVIDEND | SPLIT
    ex_ts: int  # unix seconds of the event (ex-date)
    amount: Decimal | None = None  # per-share cash amount (dividends)
    ratio: Decimal | None = None  # new shares per old share (splits)
    provider: str = ""


class Capability:
    QUOTES = "quotes"
    HISTORY = "history"
    SEARCH = "search"
    CORPORATE_ACTIONS = "corporate_actions"
    FX = "fx"


class MarketDataProvider(Protocol):
    name: str
    capabilities: set[str]

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]: ...

    def get_history(self, symbol: str, range_: str, interval: str) -> History: ...

    def search(self, query: str) -> list[SymbolMatch]: ...

    def get_corporate_actions(self, symbol: str, range_: str) -> list[CorporateAction]: ...

    def get_fx_rate(self, from_ccy: str, to_ccy: str) -> Decimal: ...


class MarketDataError(Exception):
    pass


class SymbolNotFound(MarketDataError):
    pass


# Valid (range, interval) presets exposed to clients; mirrors PRD §11 chart ranges.
RANGE_PRESETS: dict[str, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "5D": ("5d", "15m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
    "MAX": ("max", "1mo"),
}
