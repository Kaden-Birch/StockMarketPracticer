"""Stooq adapter — keyless CSV endpoints, daily data (delayed quotes).
Used as a failover behind Yahoo for quotes and daily history."""

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from .base import Bar, Capability, History, MarketDataError, Quote, SymbolNotFound

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AIPTP/0.2"}


def _stooq_symbol(symbol: str) -> str:
    # Stooq uses exchange suffixes; plain US tickers get ".us".
    s = symbol.lower()
    return s if "." in s else f"{s}.us"


class StooqProvider:
    name = "stooq"
    capabilities = {Capability.QUOTES, Capability.HISTORY}

    def __init__(self, timeout: float = 10.0):
        self._client = httpx.Client(headers=_HEADERS, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        joined = "+".join(_stooq_symbol(s) for s in symbols)
        resp = self._client.get(
            "https://stooq.com/q/l/", params={"s": joined, "f": "sd2t2ohlcv", "h": "", "e": "csv"}
        )
        if resp.status_code != 200:
            raise MarketDataError(f"Stooq quote endpoint returned {resp.status_code}")
        out: dict[str, Quote] = {}
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        for symbol, row in zip(symbols, rows):
            close = row.get("Close")
            if not close or close == "N/D":
                raise SymbolNotFound(f"Unknown symbol on Stooq: {symbol}")
            out[symbol.upper()] = Quote(
                symbol=symbol.upper(),
                price=Decimal(close),
                previous_close=None,
                currency="USD",  # Stooq .us universe; other venues use suffixes
                market_state="DELAYED",
                as_of=datetime.now(timezone.utc),
                provider=self.name,
            )
        return out

    def get_history(self, symbol: str, range_: str, interval: str) -> History:
        if interval not in ("1d", "1wk", "1mo"):
            raise MarketDataError("Stooq only provides daily/weekly/monthly history")
        stooq_interval = {"1d": "d", "1wk": "w", "1mo": "m"}[interval]
        resp = self._client.get(
            "https://stooq.com/q/d/l/",
            params={"s": _stooq_symbol(symbol), "i": stooq_interval},
        )
        if resp.status_code != 200 or resp.text.strip().lower().startswith("no data"):
            raise SymbolNotFound(f"No Stooq history for {symbol}")
        bars: list[Bar] = []
        for row in csv.DictReader(io.StringIO(resp.text)):
            try:
                ts = int(
                    datetime.strptime(row["Date"], "%Y-%m-%d")
                    .replace(tzinfo=timezone.utc)
                    .timestamp()
                )
                bars.append(
                    Bar(
                        ts=ts,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(float(row["Volume"])) if row.get("Volume") else None,
                    )
                )
            except (KeyError, ValueError):
                continue
        # Stooq returns full history; trim client-side to the requested range.
        approx_days = {
            "1d": 1, "5d": 5, "1mo": 31, "3mo": 93, "6mo": 186,
            "1y": 366, "5y": 1830, "max": 100000,
        }.get(range_, 366)
        cutoff = datetime.now(timezone.utc).timestamp() - approx_days * 86400
        bars = [b for b in bars if b.ts >= cutoff]
        return History(
            symbol=symbol.upper(), range=range_, interval=interval, currency="USD",
            bars=bars, provider=self.name, fetched_at=datetime.now(timezone.utc),
        )
