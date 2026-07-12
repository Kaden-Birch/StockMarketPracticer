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
