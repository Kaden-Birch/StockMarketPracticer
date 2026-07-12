"""Lot-level cost-basis accounting.

Invariants (property-tested in tests/test_accounting.py):
- Sum of remaining lot quantities always equals the holding quantity.
- Under AVERAGE, remaining basis == remaining_qty * average unit cost, which
  proportional lot reduction preserves exactly.
"""

from decimal import Decimal

from ..storage.models import CostBasisMethod, Lot

QTY_EPSILON = Decimal("1e-9")  # below this a lot is considered fully consumed


def total_quantity(lots: list[Lot]) -> Decimal:
    return sum((lot.quantity_remaining for lot in lots), Decimal("0"))


def cost_basis(lots: list[Lot]) -> Decimal:
    return sum((lot.quantity_remaining * lot.unit_cost for lot in lots), Decimal("0"))


def average_cost(lots: list[Lot]) -> Decimal | None:
    qty = total_quantity(lots)
    if qty == 0:
        return None
    return cost_basis(lots) / qty


def consume_lots(
    lots: list[Lot], quantity: Decimal, sell_price: Decimal, method: CostBasisMethod
) -> Decimal:
    """Reduce lot quantities for a sale of `quantity` shares and return the
    realized P&L. Caller must have verified quantity <= total_quantity(lots).

    FIFO/LIFO consume whole lots in acquisition order; AVERAGE reduces every
    lot proportionally so the remaining basis stays at average cost.
    """
    if quantity <= 0:
        raise ValueError("Sell quantity must be positive")
    held = total_quantity(lots)
    if quantity > held:
        raise ValueError(f"Cannot sell {quantity}: only {held} held")

    if method == CostBasisMethod.AVERAGE:
        avg = cost_basis(lots) / held
        factor = (held - quantity) / held
        for lot in lots:
            lot.quantity_remaining *= factor
        realized = quantity * (sell_price - avg)
    else:
        ordered = sorted(lots, key=lambda lot: lot.acquired_at)
        if method == CostBasisMethod.LIFO:
            ordered = list(reversed(ordered))
        remaining = quantity
        realized = Decimal("0")
        for lot in ordered:
            if remaining <= 0:
                break
            take = min(lot.quantity_remaining, remaining)
            if take <= 0:
                continue
            lot.quantity_remaining -= take
            realized += take * (sell_price - lot.unit_cost)
            remaining -= take

    for lot in lots:
        if lot.quantity_remaining < QTY_EPSILON:
            lot.quantity_remaining = Decimal("0")
    return realized
