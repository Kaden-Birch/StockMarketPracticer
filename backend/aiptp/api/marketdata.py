from fastapi import APIRouter, Depends, HTTPException, Request

from ..marketdata.base import RANGE_PRESETS, MarketDataError, SymbolNotFound
from ..marketdata.service import MarketDataService
from .deps import get_market

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@router.get("/quotes")
def get_quotes(symbols: str, market: MarketDataService = Depends(get_market)):
    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not wanted or len(wanted) > 50:
        raise HTTPException(status_code=422, detail="Provide 1-50 comma-separated symbols")
    try:
        quotes = market.get_quotes(wanted)
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        s: {
            "symbol": q.symbol,
            "price": str(q.price),
            "previous_close": str(q.previous_close) if q.previous_close is not None else None,
            "currency": q.currency,
            "market_state": q.market_state,
            "as_of": q.as_of.isoformat(),
            "provider": q.provider,
        }
        for s, q in quotes.items()
    }


@router.get("/history/{symbol}")
def get_history(
    symbol: str, range: str = "1M", market: MarketDataService = Depends(get_market)
):
    preset = RANGE_PRESETS.get(range.upper())
    if preset is None:
        raise HTTPException(
            status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}"
        )
    range_, interval = preset
    try:
        hist = market.get_history(symbol.upper(), range_, interval)
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        "symbol": hist.symbol,
        "range": range.upper(),
        "interval": hist.interval,
        "currency": hist.currency,
        "provider": hist.provider,
        "fetched_at": hist.fetched_at.isoformat() if hist.fetched_at else None,
        "bars": [
            {"ts": b.ts, "open": b.open, "high": b.high, "low": b.low,
             "close": b.close, "volume": b.volume}
            for b in hist.bars
        ],
    }


@router.get("/compare")
def compare(
    symbols: str, range: str = "1Y", market: MarketDataService = Depends(get_market)
):
    """Normalized price performance (first close = 100) for up to 8 symbols,
    plus simple stats per symbol."""
    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not 2 <= len(wanted) <= 8:
        raise HTTPException(status_code=422, detail="Provide 2-8 comma-separated symbols")
    preset = RANGE_PRESETS.get(range.upper())
    if preset is None:
        raise HTTPException(
            status_code=422, detail=f"range must be one of {sorted(RANGE_PRESETS)}"
        )
    range_, interval = preset
    series = []
    for symbol in wanted:
        try:
            hist = market.get_history(symbol, range_, interval)
        except SymbolNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except MarketDataError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        closes = [b.close for b in hist.bars if b.close]
        base = closes[0] if closes else None
        points = (
            [{"ts": b.ts, "value": round(b.close / base * 100, 3)}
             for b in hist.bars if b.close]
            if base
            else []
        )
        total_return = round((closes[-1] / closes[0] - 1) * 100, 2) if len(closes) > 1 else None
        # simple daily-return volatility, annualized %
        # (note: `range` here is the query param string, not the builtin)
        vol = None
        if len(closes) > 10:
            rets = [(b - a) / a for a, b in zip(closes, closes[1:]) if a]
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / len(rets)
            vol = round((var ** 0.5) * (252 ** 0.5) * 100, 2)
        series.append(
            {
                "symbol": symbol,
                "currency": hist.currency,
                "provider": hist.provider,
                "points": points,
                "total_return_pct": total_return,
                "volatility_pct": vol,
            }
        )
    return {"range": range.upper(), "series": series}


@router.get("/search")
def search(q: str, market: MarketDataService = Depends(get_market)):
    if not q.strip():
        return []
    try:
        matches = market.search(q.strip())
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return [
        {"symbol": m.symbol, "name": m.name, "exchange": m.exchange, "type": m.type}
        for m in matches
    ]


@router.get("/profile/{symbol}")
def get_profile(symbol: str, market: MarketDataService = Depends(get_market)):
    """Real company profile: sector, industry, description, key stats."""
    try:
        return market.get_profile(symbol.upper())
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/news/{symbol}")
def get_news(symbol: str, market: MarketDataService = Depends(get_market)):
    """Recent real news articles about the company."""
    try:
        return market.get_news(symbol.upper())
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/summary/{symbol}")
def ai_stock_summary(symbol: str, request: Request,
                     market: MarketDataService = Depends(get_market)):
    """Short AI summary of recent stock performance, grounded ONLY in real
    computed statistics and the real company profile — the model narrates
    verified numbers, it never invents them. 409 without a loaded model."""
    manager = request.app.state.model_manager
    if not manager.runtime.model_id:
        raise HTTPException(status_code=409,
                            detail="No AI model loaded — load one in AI Models")
    symbol = symbol.upper()
    try:
        bars = market.get_history(symbol, "1y", "1d").bars
        quote = market.get_quote(symbol)
        profile = None
        try:
            profile = market.get_profile(symbol)
        except MarketDataError:
            pass
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    closes = [b.close for b in bars if b.close]
    if len(closes) < 25:
        raise HTTPException(status_code=422, detail="Not enough history to summarize")

    def ret(days: int) -> float | None:
        if len(closes) <= days:
            return None
        return round((closes[-1] / closes[-days - 1] - 1) * 100, 1)

    high, low = max(closes), min(closes)
    facts = {
        "symbol": symbol,
        "price": str(quote.price),
        "currency": quote.currency,
        "return_1m_pct": ret(21),
        "return_6m_pct": ret(126),
        "return_1y_pct": round((closes[-1] / closes[0] - 1) * 100, 1),
        "pct_below_52w_high": round((1 - closes[-1] / high) * 100, 1),
        "pct_above_52w_low": round((closes[-1] / low - 1) * 100, 1),
    }
    if profile:
        facts["sector"] = profile.get("sector")
        facts["industry"] = profile.get("industry")
        facts["trailing_pe"] = profile.get("trailing_pe")
        facts["dividend_yield"] = profile.get("dividend_yield")
    system = (
        "You are an investing teacher in a paper-trading simulator. Write a "
        "3-5 sentence plain-language summary of this stock's recent "
        "performance using ONLY the verified statistics provided. Do not "
        "invent numbers, predictions, or price targets. Educational, never "
        "advice."
    )
    import json as _json

    text = manager.runtime.generate(system, _json.dumps(facts, indent=1),
                                    max_tokens=250).strip()
    return {"summary": text + "\n\n(AI-written from verified statistics — "
                              "educational, not financial advice.)",
            "facts": facts}
