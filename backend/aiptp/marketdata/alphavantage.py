"""Alpha Vantage adapter — user-supplied API key (AIPTP_ALPHAVANTAGE_KEY).
Free tier: 25 requests/day, so this sits behind keyless providers in the
failover chain unless the user promotes it."""

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from .base import Bar, Capability, History, MarketDataError, Quote, SymbolNotFound

_BASE = "https://www.alphavantage.co/query"


class AlphaVantageProvider:
    name = "alphavantage"
    capabilities = {Capability.QUOTES, Capability.HISTORY, Capability.FX}

    def __init__(self, api_key: str, timeout: float = 15.0):
        if not api_key:
            raise ValueError("Alpha Vantage requires an API key")
        self._key = api_key
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _get(self, params: dict) -> dict:
        try:
            resp = self._client.get(_BASE, params={**params, "apikey": self._key})
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Alpha Vantage unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise MarketDataError(f"Alpha Vantage returned {resp.status_code}")
        data = resp.json()
        if "Error Message" in data:
            raise SymbolNotFound(data["Error Message"])
        if "Note" in data or "Information" in data:
            raise MarketDataError("Alpha Vantage rate limit reached")
        return data

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        out: dict[str, Quote] = {}
        for symbol in symbols:
            data = self._get({"function": "GLOBAL_QUOTE", "symbol": symbol})
            q = data.get("Global Quote") or {}
            price = q.get("05. price")
            if not price:
                raise SymbolNotFound(f"Unknown symbol on Alpha Vantage: {symbol}")
            prev = q.get("08. previous close")
            out[symbol.upper()] = Quote(
                symbol=symbol.upper(),
                price=Decimal(price),
                previous_close=Decimal(prev) if prev else None,
                currency="USD",
                market_state="DELAYED",
                as_of=datetime.now(timezone.utc),
                provider=self.name,
            )
        return out

    def get_history(self, symbol: str, range_: str, interval: str) -> History:
        if interval not in ("1d", "1wk", "1mo"):
            raise MarketDataError("Alpha Vantage adapter provides daily+ history only")
        function = {
            "1d": "TIME_SERIES_DAILY",
            "1wk": "TIME_SERIES_WEEKLY",
            "1mo": "TIME_SERIES_MONTHLY",
        }[interval]
        outputsize = "full" if range_ in ("5y", "max") else "compact"
        data = self._get({"function": function, "symbol": symbol, "outputsize": outputsize})
        series_key = next((k for k in data if "Time Series" in k), None)
        if not series_key:
            raise SymbolNotFound(f"No Alpha Vantage history for {symbol}")
        bars: list[Bar] = []
        for date_str, row in sorted(data[series_key].items()):
            ts = int(
                datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
            )
            bars.append(
                Bar(
                    ts=ts,
                    open=float(row["1. open"]),
                    high=float(row["2. high"]),
                    low=float(row["3. low"]),
                    close=float(row["4. close"]),
                    volume=int(float(row.get("5. volume", 0))) or None,
                )
            )
        approx_days = {
            "1mo": 31, "3mo": 93, "6mo": 186, "1y": 366, "5y": 1830, "max": 100000,
        }.get(range_, 366)
        cutoff = datetime.now(timezone.utc).timestamp() - approx_days * 86400
        bars = [b for b in bars if b.ts >= cutoff]
        return History(
            symbol=symbol.upper(), range=range_, interval=interval, currency="USD",
            bars=bars, provider=self.name, fetched_at=datetime.now(timezone.utc),
        )

    def get_fx_rate(self, from_ccy: str, to_ccy: str) -> Decimal:
        if from_ccy == to_ccy:
            return Decimal("1")
        data = self._get(
            {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_ccy,
                "to_currency": to_ccy,
            }
        )
        rate = (data.get("Realtime Currency Exchange Rate") or {}).get("5. Exchange Rate")
        if not rate:
            raise MarketDataError(f"No FX rate for {from_ccy}/{to_ccy}")
        return Decimal(rate)
