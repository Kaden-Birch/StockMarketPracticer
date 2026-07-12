from datetime import datetime, timezone
from decimal import Decimal

from .base import Bar, History, Quote, SymbolMatch, SymbolNotFound


class FakeProvider:
    """Deterministic in-memory provider for tests ONLY. Never registered in a
    normal deployment — the no-fabricated-data rule (PRD §10) applies to real
    use, while tests need controlled prices."""

    name = "fake"

    def __init__(self, prices: dict[str, str] | None = None):
        self.prices: dict[str, Decimal] = {
            k.upper(): Decimal(v) for k, v in (prices or {"TEST": "100"}).items()
        }

    def set_price(self, symbol: str, price: str) -> None:
        self.prices[symbol.upper()] = Decimal(price)

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        out = {}
        for s in symbols:
            key = s.upper()
            if key not in self.prices:
                raise SymbolNotFound(f"Unknown symbol: {s}")
            out[key] = Quote(
                symbol=key,
                price=self.prices[key],
                previous_close=self.prices[key],
                currency="USD",
                market_state="REGULAR",
                as_of=datetime.now(timezone.utc),
                provider=self.name,
            )
        return out

    def get_history(self, symbol: str, range_: str, interval: str) -> History:
        key = symbol.upper()
        if key not in self.prices:
            raise SymbolNotFound(f"Unknown symbol: {symbol}")
        now = int(datetime.now(timezone.utc).timestamp())
        price = float(self.prices[key])
        bars = [
            Bar(ts=now - 86400 * (30 - i), open=price, high=price, low=price, close=price, volume=0)
            for i in range(30)
        ]
        return History(
            symbol=key, range=range_, interval=interval, currency="USD",
            bars=bars, provider=self.name, fetched_at=datetime.now(timezone.utc),
        )

    def search(self, query: str) -> list[SymbolMatch]:
        q = query.upper()
        return [
            SymbolMatch(symbol=s, name=f"{s} Test Co", exchange="TEST", type="EQUITY")
            for s in self.prices
            if q in s
        ]
