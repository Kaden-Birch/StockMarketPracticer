"""Cost-basis accounting unit tests — the highest-risk correctness area."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from aiptp.storage.models import CostBasisMethod, Lot
from aiptp.trading.accounting import average_cost, consume_lots, cost_basis, total_quantity


def lot(qty: str, cost: str, days_ago: int) -> Lot:
    return Lot(
        quantity_remaining=Decimal(qty),
        unit_cost=Decimal(cost),
        acquired_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def three_lots() -> list[Lot]:
    # oldest -> newest: 10 @ 100, 10 @ 120, 10 @ 140
    return [lot("10", "100", 30), lot("10", "120", 20), lot("10", "140", 10)]


def test_fifo_consumes_oldest_first():
    lots = three_lots()
    realized = consume_lots(lots, Decimal("15"), Decimal("150"), CostBasisMethod.FIFO)
    # 10 @ (150-100) + 5 @ (150-120) = 500 + 150 = 650
    assert realized == Decimal("650")
    assert total_quantity(lots) == Decimal("15")
    assert lots[0].quantity_remaining == 0
    assert lots[1].quantity_remaining == Decimal("5")
    assert lots[2].quantity_remaining == Decimal("10")


def test_lifo_consumes_newest_first():
    lots = three_lots()
    realized = consume_lots(lots, Decimal("15"), Decimal("150"), CostBasisMethod.LIFO)
    # 10 @ (150-140) + 5 @ (150-120) = 100 + 150 = 250
    assert realized == Decimal("250")
    assert lots[2].quantity_remaining == 0
    assert lots[1].quantity_remaining == Decimal("5")
    assert lots[0].quantity_remaining == Decimal("10")


def test_average_realizes_at_avg_and_preserves_avg_basis():
    lots = three_lots()  # avg cost = 120
    realized = consume_lots(lots, Decimal("15"), Decimal("150"), CostBasisMethod.AVERAGE)
    # 15 @ (150-120) = 450
    assert realized == Decimal("450")
    assert total_quantity(lots) == Decimal("15")
    # remaining basis must still average 120
    assert average_cost(lots) == Decimal("120")
    assert cost_basis(lots) == Decimal("1800")


def test_sell_everything_leaves_zero():
    for method in CostBasisMethod:
        lots = three_lots()
        consume_lots(lots, Decimal("30"), Decimal("100"), method)
        assert total_quantity(lots) == 0


def test_fractional_shares():
    lots = [lot("0.5", "100", 2), lot("0.25", "200", 1)]
    realized = consume_lots(lots, Decimal("0.6"), Decimal("300"), CostBasisMethod.FIFO)
    # 0.5 @ (300-100) + 0.1 @ (300-200) = 100 + 10 = 110
    assert realized == Decimal("110")
    assert total_quantity(lots) == Decimal("0.15")


def test_oversell_raises():
    lots = three_lots()
    with pytest.raises(ValueError):
        consume_lots(lots, Decimal("31"), Decimal("100"), CostBasisMethod.FIFO)


def test_quantity_conservation_across_methods():
    """Invariant: any sequence of partial sells conserves total quantity."""
    for method in CostBasisMethod:
        lots = three_lots()
        sold = Decimal("0")
        for chunk in [Decimal("7"), Decimal("0.123456"), Decimal("11.5")]:
            consume_lots(lots, chunk, Decimal("133.33"), method)
            sold += chunk
            assert total_quantity(lots) == Decimal("30") - sold


def test_realized_pnl_sums_to_total_gain_regardless_of_method():
    """Selling the entire position realizes the same total P&L under every
    method — methods only change the timing, never the total."""
    price = Decimal("150")
    totals = set()
    for method in CostBasisMethod:
        lots = three_lots()
        realized = consume_lots(lots, Decimal("12"), price, method)
        realized += consume_lots(lots, Decimal("18"), price, method)
        totals.add(realized)
    # total basis 3600, proceeds 30*150=4500 -> gain 900
    assert totals == {Decimal("900")}
