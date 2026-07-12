from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from ..storage.models import CostBasisMethod, OrderSide, OrderStatus, OrderType, Origin


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    currency: str = Field(default="USD", max_length=8)
    starting_balance: Decimal = Field(gt=0)
    cost_basis_method: CostBasisMethod = CostBasisMethod.FIFO
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


class OrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: OrderSide
    type: OrderType
    quantity: Decimal | None = Field(default=None, gt=0)
    notional: Decimal | None = Field(default=None, gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)

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
    limit_price: Decimal | None
    stop_price: Decimal | None
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
    origin: Origin
    executed_at: datetime

    model_config = {"from_attributes": True}
