from datetime import datetime, timezone
from decimal import Decimal

import httpx

from .base import Bar, History, MarketDataError, Quote, SymbolMatch, SymbolNotFound

_BASE = "https://query1.finance.yahoo.com"
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AIPTP/0.1"}


class YahooProvider:
    """Keyless Yahoo Finance adapter (chart + search endpoints). Quotes are
    real-time or exchange-delayed depending on the venue; provenance is
    recorded on every value returned."""

    name = "yahoo"

    def __init__(self, timeout: float = 10.0):
        self._client = httpx.Client(base_url=_BASE, headers=_HEADERS, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _chart(self, symbol: str, range_: str, interval: str) -> dict:
        resp = self._client.get(
            f"/v8/finance/chart/{symbol}", params={"range": range_, "interval": interval}
        )
        if resp.status_code == 404:
            raise SymbolNotFound(f"Unknown symbol: {symbol}")
        if resp.status_code != 200:
            raise MarketDataError(f"Yahoo chart API returned {resp.status_code} for {symbol}")
        payload = resp.json().get("chart", {})
        if payload.get("error"):
            code = payload["error"].get("code", "")
            if code == "Not Found":
                raise SymbolNotFound(f"Unknown symbol: {symbol}")
            raise MarketDataError(f"Yahoo chart API error for {symbol}: {payload['error']}")
        results = payload.get("result") or []
        if not results:
            raise SymbolNotFound(f"No data for symbol: {symbol}")
        return results[0]

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        quotes: dict[str, Quote] = {}
        for symbol in symbols:
            result = self._chart(symbol, "1d", "1d")
            meta = result["meta"]
            price = meta.get("regularMarketPrice")
            if price is None:
                raise MarketDataError(f"No market price available for {symbol}")
            prev = meta.get("chartPreviousClose", meta.get("previousClose"))
            quotes[symbol.upper()] = Quote(
                symbol=meta.get("symbol", symbol).upper(),
                price=Decimal(str(price)),
                previous_close=Decimal(str(prev)) if prev is not None else None,
                currency=meta.get("currency", "USD"),
                market_state=meta.get("marketState", "UNKNOWN"),
                as_of=datetime.fromtimestamp(
                    meta.get("regularMarketTime", datetime.now(timezone.utc).timestamp()),
                    tz=timezone.utc,
                ),
                provider=self.name,
            )
        return quotes

    def get_history(self, symbol: str, range_: str, interval: str) -> History:
        result = self._chart(symbol, range_, interval)
        meta = result["meta"]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        bars = [
            Bar(ts=ts, open=o, high=h, low=lo, close=c, volume=v)
            for ts, o, h, lo, c, v in zip(timestamps, opens, highs, lows, closes, volumes)
            if c is not None and o is not None
        ]
        return History(
            symbol=meta.get("symbol", symbol).upper(),
            range=range_,
            interval=interval,
            currency=meta.get("currency", "USD"),
            bars=bars,
            provider=self.name,
            fetched_at=datetime.now(timezone.utc),
        )

    def search(self, query: str) -> list[SymbolMatch]:
        resp = self._client.get(
            "/v1/finance/search",
            params={"q": query, "quotesCount": 10, "newsCount": 0, "listsCount": 0},
        )
        if resp.status_code != 200:
            raise MarketDataError(f"Yahoo search API returned {resp.status_code}")
        matches = []
        for item in resp.json().get("quotes", []):
            if not item.get("symbol"):
                continue
            matches.append(
                SymbolMatch(
                    symbol=item["symbol"],
                    name=item.get("shortname") or item.get("longname") or "",
                    exchange=item.get("exchDisp") or item.get("exchange") or "",
                    type=item.get("quoteType", ""),
                )
            )
        return matches
