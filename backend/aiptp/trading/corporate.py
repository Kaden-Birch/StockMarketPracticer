"""Corporate action application: dividends and splits from real provider
data, applied idempotently per portfolio.

Position at ex-date is reconstructed by replaying the immutable transaction
log (buys - sells + split adjustments before the ex-date), so dividends land
only on shares actually held then."""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import CorporateAction, MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import (
    AppliedCorporateAction,
    Holding,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Origin,
    Portfolio,
    Transaction,
    TransactionKind,
)
from .accounting import total_quantity
from .engine import CASH_PLACES, QTY_PLACES, TradingError, place_order

log = logging.getLogger(__name__)


def quantity_at(session: Session, portfolio_id: str, symbol: str, when: datetime) -> Decimal:
    """Shares of `symbol` held by the portfolio just before `when`, from the
    transaction log."""
    txns = session.scalars(
        select(Transaction)
        .where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.symbol == symbol,
            Transaction.executed_at < when,
        )
        .order_by(Transaction.executed_at)
    ).all()
    qty = Decimal("0")
    for t in txns:
        if t.kind == TransactionKind.SPLIT:
            qty += t.quantity  # recorded as the share delta
        elif t.kind == TransactionKind.TRADE:
            qty += t.quantity if t.side == OrderSide.BUY else -t.quantity
    return qty


def _already_applied(session: Session, portfolio_id: str, action: CorporateAction) -> bool:
    return (
        session.scalar(
            select(AppliedCorporateAction).where(
                AppliedCorporateAction.portfolio_id == portfolio_id,
                AppliedCorporateAction.symbol == action.symbol,
                AppliedCorporateAction.kind == action.kind,
                AppliedCorporateAction.ex_ts == action.ex_ts,
            )
        )
        is not None
    )


def _mark_applied(session: Session, portfolio_id: str, action: CorporateAction) -> None:
    session.add(
        AppliedCorporateAction(
            portfolio_id=portfolio_id,
            symbol=action.symbol,
            kind=action.kind,
            ex_ts=action.ex_ts,
        )
    )


def apply_dividend(
    session: Session,
    portfolio: Portfolio,
    action: CorporateAction,
    market: MarketDataService,
) -> Transaction | None:
    ex_date = datetime.fromtimestamp(action.ex_ts, tz=timezone.utc)
    qty = quantity_at(session, portfolio.id, action.symbol, ex_date)
    if qty <= 0:
        _mark_applied(session, portfolio.id, action)
        return None
    quote = market.get_quote(action.symbol)
    fx = market.get_fx_rate(quote.currency, portfolio.currency)
    amount = (qty * action.amount * fx).quantize(CASH_PLACES)
    if amount <= 0:
        _mark_applied(session, portfolio.id, action)
        return None
    portfolio.cash_balance = (portfolio.cash_balance + amount).quantize(CASH_PLACES)
    txn = Transaction(
        portfolio_id=portfolio.id,
        symbol=action.symbol,
        side=OrderSide.BUY,  # unused for dividends; kind is authoritative
        quantity=qty,
        price=action.amount,
        amount=amount,
        kind=TransactionKind.DIVIDEND,
        fx_rate=fx,
        quote_currency=quote.currency,
        origin=Origin.SYSTEM,
        executed_at=datetime.now(timezone.utc),
    )
    session.add(txn)
    _mark_applied(session, portfolio.id, action)

    if portfolio.dividend_reinvest:
        try:
            place_order(
                session,
                portfolio,
                symbol=action.symbol,
                side=OrderSide.BUY,
                type_=OrderType.MARKET,
                notional=amount,
                origin=Origin.DIVIDEND_REINVEST,
                current_price=quote.price,
                fx_rate=fx,
                quote_currency=quote.currency,
            )
        except TradingError as exc:
            log.info("Dividend reinvest skipped for %s: %s", action.symbol, exc)
    return txn


def apply_split(
    session: Session, portfolio: Portfolio, action: CorporateAction
) -> Transaction | None:
    holding = session.scalar(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id, Holding.symbol == action.symbol
        )
    )
    if holding is None or holding.quantity <= 0:
        _mark_applied(session, portfolio.id, action)
        return None
    before = holding.quantity
    for lot in holding.lots:
        if lot.quantity_remaining > 0:
            lot.quantity_remaining = (lot.quantity_remaining * action.ratio).quantize(QTY_PLACES)
            lot.unit_cost = lot.unit_cost / action.ratio
    holding.quantity = total_quantity(holding.lots)
    delta = holding.quantity - before
    txn = Transaction(
        portfolio_id=portfolio.id,
        symbol=action.symbol,
        side=OrderSide.BUY if delta >= 0 else OrderSide.SELL,
        quantity=delta,
        price=Decimal("0"),
        amount=Decimal("0"),
        kind=TransactionKind.SPLIT,
        origin=Origin.SYSTEM,
        executed_at=datetime.now(timezone.utc),
    )
    session.add(txn)
    _mark_applied(session, portfolio.id, action)
    log.info("Applied %s split to %s: %s -> %s shares",
             action.ratio, action.symbol, before, holding.quantity)
    return txn


def run_corporate_actions_cycle(session_factory, market: MarketDataService, bus) -> None:
    """Scheduled job: fetch recent dividend/split events for all held symbols
    and apply any not yet applied. Idempotent."""
    with session_factory() as session:
        held = session.scalars(
            select(Holding.symbol).where(Holding.quantity > 0).distinct()
        ).all()
        for symbol in held:
            try:
                actions = market.get_corporate_actions(symbol, "3mo")
            except MarketDataError as exc:
                log.warning("Corporate action fetch failed for %s: %s", symbol, exc)
                continue
            if not actions:
                continue
            portfolios = session.scalars(
                select(Portfolio)
                .join(Holding, Holding.portfolio_id == Portfolio.id)
                .where(Holding.symbol == symbol, Holding.quantity > 0)
            ).unique().all()
            for portfolio in portfolios:
                for action in actions:
                    if _already_applied(session, portfolio.id, action):
                        continue
                    try:
                        if action.kind == "DIVIDEND":
                            txn = apply_dividend(session, portfolio, action, market)
                        else:
                            txn = apply_split(session, portfolio, action)
                    except MarketDataError as exc:
                        log.warning("Skipping %s %s on %s: %s",
                                    action.kind, symbol, portfolio.id, exc)
                        continue
                    if txn is not None and bus is not None:
                        bus.publish(
                            "corporate_action",
                            {
                                "portfolio_id": portfolio.id,
                                "symbol": symbol,
                                "kind": action.kind,
                                "amount": str(txn.amount),
                                "quantity": str(txn.quantity),
                            },
                            session=session,
                        )
        session.commit()
