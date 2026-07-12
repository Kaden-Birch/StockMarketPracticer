from datetime import datetime, timezone
from decimal import Decimal

from .base import Bar, Capability, CorporateAction, History, Quote, SymbolMatch, SymbolNotFound


class FakeProvider:
    """Deterministic in-memory provider for tests ONLY. Never registered in a
    normal deployment — the no-fabricated-data rule (PRD §10) applies to real
    use, while tests need controlled prices."""

    name = "fake"
    capabilities = {
        Capability.QUOTES,
        Capability.HISTORY,
        Capability.SEARCH,
        Capability.CORPORATE_ACTIONS,
        Capability.FX,
    }

    def __init__(self, prices: dict[str, str] | None = None):
        self.prices: dict[str, Decimal] = {
            k.upper(): Decimal(v) for k, v in (prices or {"TEST": "100"}).items()
        }
        self.currencies: dict[str, str] = {}
        self.fx_rates: dict[tuple[str, str], Decimal] = {}
        self.corporate_actions: dict[str, list[CorporateAction]] = {}
        self.history_bars: dict[str, list[Bar]] = {}

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
                currency=self.currencies.get(key, "USD"),
                market_state="REGULAR",
                as_of=datetime.now(timezone.utc),
                provider=self.name,
            )
        return out

    def get_history(self, symbol: str, range_: str, interval: str) -> History:
        key = symbol.upper()
        if key not in self.prices:
            raise SymbolNotFound(f"Unknown symbol: {symbol}")
        bars = self.history_bars.get(key)
        if bars is None:
            now = int(datetime.now(timezone.utc).timestamp())
            price = float(self.prices[key])
            bars = [
                Bar(ts=now - 86400 * (30 - i), open=price, high=price, low=price,
                    close=price, volume=0)
                for i in range(30)
            ]
        return History(
            symbol=key, range=range_, interval=interval,
            currency=self.currencies.get(key, "USD"),
            bars=bars, provider=self.name, fetched_at=datetime.now(timezone.utc),
        )

    def get_corporate_actions(self, symbol: str, range_: str = "3mo") -> list[CorporateAction]:
        return self.corporate_actions.get(symbol.upper(), [])

    def get_fx_rate(self, from_ccy: str, to_ccy: str) -> Decimal:
        if from_ccy == to_ccy:
            return Decimal("1")
        try:
            return self.fx_rates[(from_ccy, to_ccy)]
        except KeyError:
            raise SymbolNotFound(f"No FX rate for {from_ccy}/{to_ccy}")

    def search(self, query: str) -> list[SymbolMatch]:
        q = query.upper()
        return [
            SymbolMatch(symbol=s, name=f"{s} Test Co", exchange="TEST", type="EQUITY")
            for s in self.prices
            if q in s
        ]
