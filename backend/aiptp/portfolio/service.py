"""Portfolio valuation: combines holdings/lots with live MDAL quotes."""

from decimal import Decimal
from typing import Any

from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import Portfolio
from ..trading.accounting import average_cost, cost_basis

TWO = Decimal("0.01")


def value_portfolio(portfolio: Portfolio, market: MarketDataService) -> dict[str, Any]:
    symbols = [h.symbol for h in portfolio.holdings if h.quantity > 0]
    quotes = {}
    fx: dict[str, Decimal] = {}
    quote_errors: list[str] = []
    if symbols:
        try:
            quotes = market.get_quotes(symbols)
            for s, q in quotes.items():
                try:
                    fx[s] = market.get_fx_rate(q.currency, portfolio.currency)
                except MarketDataError as exc:
                    quote_errors.append(f"FX unavailable for {s}: {exc}")
                    fx[s] = Decimal("1")
        except MarketDataError as exc:
            quote_errors.append(str(exc))

    holdings_out = []
    total_market_value = Decimal("0")
    total_cost = Decimal("0")
    day_change = Decimal("0")
    for holding in portfolio.holdings:
        if holding.quantity <= 0:
            continue
        basis = cost_basis(holding.lots)
        avg = average_cost(holding.lots)
        quote = quotes.get(holding.symbol)
        entry: dict[str, Any] = {
            "symbol": holding.symbol,
            "quantity": str(holding.quantity),
            "avg_cost": str(avg.quantize(TWO)) if avg is not None else None,
            "cost_basis": str(basis.quantize(TWO)),
            "price": None,
            "market_value": None,
            "unrealized_pnl": None,
            "day_change": None,
            "quote_as_of": None,
            "provider": None,
        }
        if quote:
            rate = fx.get(holding.symbol, Decimal("1"))
            mv = (holding.quantity * quote.price * rate).quantize(TWO)
            entry.update(
                price=str(quote.price),
                market_value=str(mv),
                unrealized_pnl=str((mv - basis).quantize(TWO)),
                quote_as_of=quote.as_of.isoformat(),
                provider=quote.provider,
            )
            total_market_value += mv
            if quote.previous_close:
                dc = (
                    holding.quantity * (quote.price - quote.previous_close) * rate
                ).quantize(TWO)
                entry["day_change"] = str(dc)
                day_change += dc
        total_cost += basis
        holdings_out.append(entry)

    total_value = portfolio.cash_balance + total_market_value
    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "description": portfolio.description,
        "currency": portfolio.currency,
        "starting_balance": str(portfolio.starting_balance),
        "cash_balance": str(portfolio.cash_balance),
        "cost_basis_method": portfolio.cost_basis_method.value,
        "dividend_reinvest": portfolio.dividend_reinvest,
        "notes": portfolio.notes,
        "created_at": portfolio.created_at.isoformat(),
        "holdings": holdings_out,
        "market_value": str(total_market_value.quantize(TWO)),
        "total_value": str(total_value.quantize(TWO)),
        "total_cost_basis": str(total_cost.quantize(TWO)),
        "unrealized_pnl": str((total_market_value - total_cost).quantize(TWO)),
        "day_change": str(day_change.quantize(TWO)),
        "lifetime_return": str((total_value - portfolio.starting_balance).quantize(TWO)),
        "quote_errors": quote_errors,
    }
