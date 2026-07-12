from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError, SymbolNotFound
from ..marketdata.service import MarketDataService
from ..storage.models import Watchlist, WatchlistItem
from .deps import get_db, get_market
from .schemas import WatchlistCreate, WatchlistItemCreate

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def _watchlist_view(wl: Watchlist, market: MarketDataService) -> dict:
    symbols = [item.symbol for item in wl.items]
    quotes = {}
    errors: list[str] = []
    if symbols:
        try:
            quotes = market.get_quotes(symbols)
        except MarketDataError as exc:
            errors.append(str(exc))
    items = []
    for item in wl.items:
        q = quotes.get(item.symbol)
        change = change_pct = None
        if q and q.previous_close and q.previous_close > 0:
            change = str(q.price - q.previous_close)
            change_pct = str(
                round((q.price - q.previous_close) / q.previous_close * 100, 2)
            )
        items.append(
            {
                "symbol": item.symbol,
                "price": str(q.price) if q else None,
                "previous_close": str(q.previous_close) if q and q.previous_close else None,
                "change": change,
                "change_pct": change_pct,
                "currency": q.currency if q else None,
                "provider": q.provider if q else None,
            }
        )
    return {"id": wl.id, "name": wl.name, "items": items, "quote_errors": errors}


@router.post("", status_code=201)
def create_watchlist(
    body: WatchlistCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    wl = Watchlist(name=body.name)
    session.add(wl)
    session.commit()
    return _watchlist_view(wl, market)


@router.get("")
def list_watchlists(
    session: Session = Depends(get_db), market: MarketDataService = Depends(get_market)
):
    lists = session.scalars(select(Watchlist).order_by(Watchlist.created_at)).all()
    return [_watchlist_view(wl, market) for wl in lists]


@router.delete("/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: str, session: Session = Depends(get_db)):
    wl = session.get(Watchlist, watchlist_id)
    if wl is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    session.delete(wl)
    session.commit()


@router.post("/{watchlist_id}/items", status_code=201)
def add_item(
    watchlist_id: str,
    body: WatchlistItemCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    wl = session.get(Watchlist, watchlist_id)
    if wl is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    if any(i.symbol == body.symbol for i in wl.items):
        raise HTTPException(status_code=409, detail=f"{body.symbol} is already on this list")
    try:
        market.get_quote(body.symbol)
    except SymbolNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {body.symbol}")
    except MarketDataError:
        pass
    session.add(WatchlistItem(watchlist_id=wl.id, symbol=body.symbol))
    session.commit()
    session.refresh(wl)
    return _watchlist_view(wl, market)


@router.delete("/{watchlist_id}/items/{symbol}", status_code=204)
def remove_item(watchlist_id: str, symbol: str, session: Session = Depends(get_db)):
    item = session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol == symbol.upper(),
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Symbol not on this watchlist")
    session.delete(item)
    session.commit()
