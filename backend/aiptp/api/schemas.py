from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from ..storage.models import (
    Cadence,
    CostBasisMethod,
    GameMode,
    OrderSide,
    OrderStatus,
    OrderType,
    Origin,
    PercentOf,
    TransactionKind,
)


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    currency: str = Field(default="USD", max_length=8)
    starting_balance: Decimal = Field(gt=0)
    cost_basis_method: CostBasisMethod = CostBasisMethod.FIFO
    mode: GameMode = GameMode.CLASSIC
    preset: str = Field(default="ACADEMY", pattern="^(LEARNING|ACADEMY|PROFESSIONAL)$")
    ends_at: datetime | None = None
    notes: str = ""

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    notes: str | None = None
    cost_basis_method: CostBasisMethod | None = None
    dividend_reinvest: bool | None = None
    # Leaderboards are strictly opt-in (roadmap 7.3 / PRD privacy).
    public_on_leaderboard: bool | None = None


class OrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: OrderSide
    type: OrderType
    quantity: Decimal | None = Field(default=None, gt=0)
    notional: Decimal | None = Field(default=None, gt=0)
    percent: Decimal | None = Field(default=None, gt=0, le=100)
    percent_of: PercentOf | None = None
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)
    trail_amount: Decimal | None = Field(default=None, gt=0)
    trail_percent: Decimal | None = Field(default=None, gt=0, lt=100)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class BatchOrderCreate(BaseModel):
    orders: list[OrderCreate] = Field(min_length=1, max_length=50)


class RebalanceRequest(BaseModel):
    targets: dict[str, Decimal]  # symbol -> target weight %
    execute: bool = False


class RecurringPlanCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    cadence: Cadence
    start_at: datetime | None = None  # defaults to now (first run immediate)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class RecurringPlanUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    cadence: Cadence | None = None
    enabled: bool | None = None


class RecurringPlanOut(BaseModel):
    id: str
    portfolio_id: str
    symbol: str
    amount: Decimal
    cadence: Cadence
    next_run_at: datetime
    enabled: bool
    last_run_at: datetime | None
    run_count: int

    model_config = {"from_attributes": True}


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class OrderOut(BaseModel):
    id: str
    portfolio_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal | None
    notional: Decimal | None
    percent: Decimal | None
    percent_of: PercentOf | None
    limit_price: Decimal | None
    stop_price: Decimal | None
    trail_amount: Decimal | None
    trail_percent: Decimal | None
    watermark: Decimal | None
    stop_triggered: bool
    status: OrderStatus
    reject_reason: str
    origin: Origin
    created_at: datetime
    filled_at: datetime | None

    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    id: str
    portfolio_id: str
    order_id: str | None
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    amount: Decimal
    fees: Decimal
    realized_pnl: Decimal | None
    kind: TransactionKind
    fx_rate: Decimal
    quote_currency: str
    origin: Origin
    executed_at: datetime

    model_config = {"from_attributes": True}
