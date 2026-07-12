import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, DecimalStr


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CostBasisMethod(str, enum.Enum):
    FIFO = "FIFO"
    LIFO = "LIFO"
    AVERAGE = "AVERAGE"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Origin(str, enum.Enum):
    """Provenance of an order/transaction. AI and automation variants exist
    from day one so AI-assisted trades are distinguishable at the data layer
    forever (PRD §17); M1 only produces MANUAL."""

    MANUAL = "MANUAL"
    AUTOMATION = "AUTOMATION"
    AI_ASSISTED = "AI_ASSISTED"
    AI_AUTO = "AI_AUTO"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    starting_balance: Mapped[Decimal] = mapped_column(DecimalStr)
    cash_balance: Mapped[Decimal] = mapped_column(DecimalStr)
    cost_basis_method: Mapped[CostBasisMethod] = mapped_column(
        Enum(CostBasisMethod), default=CostBasisMethod.FIFO
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (Index("ix_holdings_portfolio_symbol", "portfolio_id", "symbol", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("0"))

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")
    lots: Mapped[list["Lot"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan", order_by="Lot.acquired_at"
    )


class Lot(Base):
    """A tax lot. Lot-level tracking makes FIFO/LIFO/Average exact, including
    fractional shares and partial sales."""

    __tablename__ = "lots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    holding_id: Mapped[str] = mapped_column(ForeignKey("holdings.id", ondelete="CASCADE"))
    quantity_remaining: Mapped[Decimal] = mapped_column(DecimalStr)
    unit_cost: Mapped[Decimal] = mapped_column(DecimalStr)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    holding: Mapped[Holding] = relationship(back_populates="lots")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_status_symbol", "status", "symbol"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    type: Mapped[OrderType] = mapped_column(Enum(OrderType))
    quantity: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    notional: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    limit_price: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    stop_triggered: Mapped[bool] = mapped_column(default=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.PENDING)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[Origin] = mapped_column(Enum(Origin), default=Origin.MANUAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="orders")


class Transaction(Base):
    """Immutable, append-only record of every fill. Never updated or deleted;
    corrections are compensating entries."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    quantity: Mapped[Decimal] = mapped_column(DecimalStr)
    price: Mapped[Decimal] = mapped_column(DecimalStr)
    amount: Mapped[Decimal] = mapped_column(DecimalStr)
    fees: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("0"))
    realized_pnl: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    origin: Mapped[Origin] = mapped_column(Enum(Origin), default=Origin.MANUAL)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")
