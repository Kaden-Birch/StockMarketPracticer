import threading
import time

from .base import History, MarketDataProvider, Quote, SymbolMatch


class MarketDataService:
    """Market Data Abstraction Layer entry point: routes requests to the
    active provider with TTL caching. Provider adapters are swappable without
    touching the rest of the application (PRD §10). Thread-safe — called from
    both API handlers and the watcher thread."""

    def __init__(self, provider: MarketDataProvider, quote_ttl: int = 15, history_ttl: int = 600):
        self.provider = provider
        self._quote_ttl = quote_ttl
        self._history_ttl = history_ttl
        self._quotes: dict[str, tuple[float, Quote]] = {}
        self._history: dict[tuple[str, str, str], tuple[float, History]] = {}
        self._lock = threading.Lock()

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
            fresh = self.provider.get_quotes(sorted(wanted))
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
        hist = self.provider.get_history(symbol, range_, interval)
        with self._lock:
            self._history[key] = (now, hist)
        return hist

    def search(self, query: str) -> list[SymbolMatch]:
        return self.provider.search(query)
