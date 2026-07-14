from datetime import datetime, timezone
from decimal import Decimal

import httpx

from .base import (
    Bar,
    Capability,
    CorporateAction,
    History,
    MarketDataError,
    Quote,
    SymbolMatch,
    SymbolNotFound,
)

_BASE = "https://query1.finance.yahoo.com"
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AIPTP/0.1"}


class YahooProvider:
    """Keyless Yahoo Finance adapter (chart + search endpoints). Quotes are
    real-time or exchange-delayed depending on the venue; provenance is
    recorded on every value returned."""

    name = "yahoo"
    capabilities = {
        Capability.QUOTES,
        Capability.HISTORY,
        Capability.SEARCH,
        Capability.CORPORATE_ACTIONS,
        Capability.FX,
    }

    def __init__(self, timeout: float = 10.0):
        self._client = httpx.Client(base_url=_BASE, headers=_HEADERS, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _chart(self, symbol: str, range_: str, interval: str, events: str = "",
               period1: int | None = None, period2: int | None = None) -> dict:
        params: dict[str, str] = {"interval": interval}
        if period1 is not None and period2 is not None:
            # Explicit unix window — how historical-scenario replays (M8.2)
            # get daily bars from decades ago, where `range` only gives
            # coarse granularity.
            params["period1"] = str(period1)
            params["period2"] = str(period2)
        else:
            params["range"] = range_
        if events:
            params["events"] = events
        try:
            resp = self._client.get(f"/v8/finance/chart/{symbol}", params=params)
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Yahoo unreachable: {exc}") from exc
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

    def get_history_window(self, symbol: str, start_ts: int, end_ts: int) -> History:
        """Real daily bars for an explicit historical window (roadmap 8.2)."""
        result = self._chart(symbol, "", "1d", period1=start_ts, period2=end_ts)
        return self._history_from(result, symbol, f"{start_ts}-{end_ts}", "1d")

    def get_history(self, symbol: str, range_: str, interval: str) -> History:
        result = self._chart(symbol, range_, interval)
        return self._history_from(result, symbol, range_, interval)

    def _history_from(self, result: dict, symbol: str, range_: str,
                      interval: str) -> History:
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

    def get_corporate_actions(self, symbol: str, range_: str = "3mo") -> list[CorporateAction]:
        result = self._chart(symbol, range_, "1d", events="div|split")
        events = result.get("events", {})
        actions: list[CorporateAction] = []
        for ts, div in (events.get("dividends") or {}).items():
            if div.get("amount"):
                actions.append(
                    CorporateAction(
                        symbol=symbol.upper(),
                        kind="DIVIDEND",
                        ex_ts=int(div.get("date", ts)),
                        amount=Decimal(str(div["amount"])),
                        provider=self.name,
                    )
                )
        for ts, split in (events.get("splits") or {}).items():
            num, den = split.get("numerator"), split.get("denominator")
            if num and den:
                actions.append(
                    CorporateAction(
                        symbol=symbol.upper(),
                        kind="SPLIT",
                        ex_ts=int(split.get("date", ts)),
                        ratio=Decimal(str(num)) / Decimal(str(den)),
                        provider=self.name,
                    )
                )
        actions.sort(key=lambda a: a.ex_ts)
        return actions

    def get_fx_rate(self, from_ccy: str, to_ccy: str) -> Decimal:
        if from_ccy == to_ccy:
            return Decimal("1")
        # GBp (pence) quirk: Yahoo quotes LSE equities in pence.
        scale = Decimal("1")
        if from_ccy == "GBp":
            from_ccy, scale = "GBP", Decimal("0.01")
        pair = f"{to_ccy}=X" if from_ccy == "USD" else f"{from_ccy}{to_ccy}=X"
        result = self._chart(pair, "1d", "1d")
        price = result["meta"].get("regularMarketPrice")
        if price is None:
            raise MarketDataError(f"No FX rate for {from_ccy}/{to_ccy}")
        return Decimal(str(price)) * scale

    def search(self, query: str) -> list[SymbolMatch]:
        try:
            resp = self._client.get(
                "/v1/finance/search",
                params={"q": query, "quotesCount": 10, "newsCount": 0, "listsCount": 0},
            )
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Yahoo unreachable: {exc}") from exc
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
