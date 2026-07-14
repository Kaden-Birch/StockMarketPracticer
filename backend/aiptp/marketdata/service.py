import logging
import threading
import time
from decimal import Decimal

from .base import (
    Capability,
    CorporateAction,
    History,
    MarketDataError,
    MarketDataProvider,
    Quote,
    SymbolMatch,
    SymbolNotFound,
)

log = logging.getLogger(__name__)


class MarketDataService:
    """Market Data Abstraction Layer entry point. Routes each request across
    an ordered provider chain by capability, with failover on provider errors
    (not on unknown symbols) and TTL caching. Thread-safe."""

    def __init__(
        self,
        providers: list[MarketDataProvider],
        quote_ttl: int = 15,
        history_ttl: int = 600,
    ):
        if not providers:
            raise ValueError("At least one market data provider is required")
        self.providers = providers
        self._quote_ttl = quote_ttl
        self._history_ttl = history_ttl
        self._quotes: dict[str, tuple[float, Quote]] = {}
        self._history: dict[tuple[str, str, str], tuple[float, History]] = {}
        self._fx: dict[tuple[str, str], tuple[float, Decimal]] = {}
        self._lock = threading.Lock()

    @property
    def provider(self) -> MarketDataProvider:
        return self.providers[0]

    def _chain(self, capability: str) -> list[MarketDataProvider]:
        chain = [p for p in self.providers if capability in p.capabilities]
        if not chain:
            raise MarketDataError(f"No configured provider supports {capability}")
        return chain

    def _fanout(self, capability: str, call):
        """Try each capable provider in order; SymbolNotFound is authoritative
        from the first provider that supports the capability, other errors
        fail over."""
        last_error: Exception | None = None
        for provider in self._chain(capability):
            try:
                return call(provider)
            except SymbolNotFound:
                raise
            except MarketDataError as exc:
                log.warning("%s failed on %s: %s — trying next provider",
                            capability, provider.name, exc)
                last_error = exc
        raise last_error  # type: ignore[misc]

    def get_quote(self, symbol: str) -> Quote:
        return self.get_quotes([symbol])[symbol.upper()]

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        now = time.monotonic()
        wanted = {s.upper() for s in symbols}
        out: dict[str, Quote] = {}
        with self._lock:
            for s in list(wanted):
                cached = self._quotes.get(s)
                if cached and now - cached[0] < self._quote_ttl:
                    out[s] = cached[1]
                    wanted.discard(s)
        if wanted:
            fresh = self._fanout(
                Capability.QUOTES, lambda p: p.get_quotes(sorted(wanted))
            )
            with self._lock:
                for s, q in fresh.items():
                    self._quotes[s] = (now, q)
            out.update(fresh)
        return out

    def get_history(self, symbol: str, range_: str, interval: str) -> History:
        key = (symbol.upper(), range_, interval)
        now = time.monotonic()
        with self._lock:
            cached = self._history.get(key)
            if cached and now - cached[0] < self._history_ttl:
                return cached[1]
        hist = self._fanout(
            Capability.HISTORY, lambda p: p.get_history(symbol, range_, interval)
        )
        with self._lock:
            self._history[key] = (now, hist)
        return hist

    def get_history_window(self, symbol: str, start_ts: int, end_ts: int) -> History:
        """Daily bars for an explicit historical window (roadmap 8.2 scenario
        replays). Closed windows are immutable, so they cache indefinitely
        for the process lifetime. Falls through the provider chain to the
        first provider that supports window fetches."""
        key = (symbol.upper(), f"w{start_ts}", f"w{end_ts}")
        with self._lock:
            cached = self._history.get(key)
            if cached:
                return cached[1]
        def fetch(p):
            if not hasattr(p, "get_history_window"):
                raise MarketDataError(f"{p.name} cannot fetch historical windows")
            return p.get_history_window(symbol, start_ts, end_ts)

        hist = self._fanout(Capability.HISTORY, fetch)
        with self._lock:
            self._history[key] = (time.monotonic(), hist)
        return hist

    def get_fx_rate(self, from_ccy: str, to_ccy: str) -> Decimal:
        if from_ccy == to_ccy:
            return Decimal("1")
        key = (from_ccy, to_ccy)
        now = time.monotonic()
        with self._lock:
            cached = self._fx.get(key)
            if cached and now - cached[0] < self._quote_ttl * 4:
                return cached[1]
        rate = self._fanout(Capability.FX, lambda p: p.get_fx_rate(from_ccy, to_ccy))
        with self._lock:
            self._fx[key] = (now, rate)
        return rate

    def get_corporate_actions(self, symbol: str, range_: str = "3mo") -> list[CorporateAction]:
        return self._fanout(
            Capability.CORPORATE_ACTIONS, lambda p: p.get_corporate_actions(symbol, range_)
        )

    def search(self, query: str) -> list[SymbolMatch]:
        return self._fanout(Capability.SEARCH, lambda p: p.search(query))
