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
    TRAILING_STOP = "TRAILING_STOP"


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
    SYSTEM = "SYSTEM"  # corporate actions applied by the platform
    DIVIDEND_REINVEST = "DIVIDEND_REINVEST"


class TransactionKind(str, enum.Enum):
    TRADE = "TRADE"
    DIVIDEND = "DIVIDEND"  # cash dividend credit
    SPLIT = "SPLIT"  # share-quantity adjustment, no cash movement


class PercentOf(str, enum.Enum):
    CASH = "CASH"
    PORTFOLIO ="PORTFOLIO"
    POSITION = "POSITION"  # sells: percentage of current holding


class Cadence(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


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
    dividend_reinvest: Mapped[bool] = mapped_column(default=False)
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
    trail_amount: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    trail_percent: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    watermark: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    percent: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    percent_of: Mapped[PercentOf | None] = mapped_column(Enum(PercentOf), nullable=True)
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
    kind: Mapped[TransactionKind] = mapped_column(
        Enum(TransactionKind), default=TransactionKind.TRADE
    )
    fx_rate: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("1"))
    quote_currency: Mapped[str] = mapped_column(String(8), default="USD")
    origin: Mapped[Origin] = mapped_column(Enum(Origin), default=Origin.MANUAL)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")


class RecurringPlan(Base):
    """Dollar-cost-averaging / recurring purchase plan. Executed by the
    scheduler when next_run_at passes; runs 24/7 in server mode."""

    __tablename__ = "recurring_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(DecimalStr)  # notional, portfolio currency
    cadence: Mapped[Cadence] = mapped_column(Enum(Cadence))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan", order_by="WatchlistItem.added_at"
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        Index("ix_watchlist_items_unique", "watchlist_id", "symbol", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    watchlist_id: Mapped[str] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class RuleActionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    REBALANCE = "REBALANCE"
    NOTIFY = "NOTIFY"


class AutomationRule(Base):
    """User-defined automation: a JSON trigger AST plus one action. Evaluated
    event-driven on price updates and on a schedule tick; never eval()'d code
    (ARCHITECTURE.md §5)."""

    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    trigger: Mapped[str] = mapped_column(Text)  # JSON AST
    action_type: Mapped[RuleActionType] = mapped_column(Enum(RuleActionType))
    action_params: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    enabled: Mapped[bool] = mapped_column(default=True)
    cooldown_seconds: Mapped[int] = mapped_column(default=3600)
    max_fires_per_day: Mapped[int] = mapped_column(default=5)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fire_count: Mapped[int] = mapped_column(default=0)
    armed: Mapped[bool] = mapped_column(default=True)  # edge-trigger state: re-arms when condition goes false
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fires: Mapped[list["RuleFire"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan", order_by="RuleFire.fired_at.desc()"
    )


class RuleFire(Base):
    __tablename__ = "rule_fires"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    rule_id: Mapped[str] = mapped_column(ForeignKey("automation_rules.id", ondelete="CASCADE"))
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    result: Mapped[str] = mapped_column(String(20))  # EXECUTED | NOTIFIED | REJECTED | ERROR
    detail: Mapped[str] = mapped_column(Text, default="")

    rule: Mapped[AutomationRule] = relationship(back_populates="fires")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(40))  # order_filled | rule_fired | dividend | ...
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    portfolio_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    """Server-mode account. M3 supports a single admin; roles/multi-user in M6."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderCredential(Base):
    """Encrypted-at-rest provider API keys (PRD §27). Values are Fernet
    ciphertext; the key file lives in the data directory with 0600 perms."""

    __tablename__ = "provider_credentials"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(80), default="local")
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppliedCorporateAction(Base):
    """Idempotency record: which dividend/split events have already been
    applied to which portfolio."""

    __tablename__ = "applied_corporate_actions"
    __table_args__ = (
        Index(
            "ix_applied_corp_unique", "portfolio_id", "symbol", "kind", "ex_ts", unique=True
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(16))  # DIVIDEND | SPLIT
    ex_ts: Mapped[int] = mapped_column()  # provider event timestamp (unix)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
