from fastapi import APIRouter, Depends, HTTPException

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
