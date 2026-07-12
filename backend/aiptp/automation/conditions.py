"""Trigger AST evaluation — pure, data-driven, never eval()'d.

AST shape (ARCHITECTURE.md §5):
  {"all": [<node>, ...]} | {"any": [...]} | {"not": <node>} | leaf

Leaf conditions:
  {"price":          {"symbol": "AAPL", "op": "<", "value": 170}}
  {"pct_move":       {"symbol": "AAPL", "op": "<", "value": -3}}      # % vs previous close
  {"indicator":      {"symbol": "AAPL", "name": "RSI", "period": 14, "op": "<", "value": 30}}
  {"dividend_event": {"symbol": "AAPL", "within_days": 3}}            # dividend applied recently
  {"schedule":       {"at": "14:30", "days": ["MON","TUE",...]}}      # UTC, fires that minute
  {"allocation":     {"symbol": "AAPL", "op": ">", "value": 30}}      # % of portfolio value
  {"cash":           {"op": ">", "value": 1000}}                      # portfolio currency

`earnings_event` and `news_sentiment` parse as always-false placeholders until
a data source lands (documented deviation — no keyless earnings/news feed).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

OPS: dict[str, Callable[[float, float], bool]] = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}

KNOWN_LEAVES = {
    "price", "pct_move", "indicator", "dividend_event", "schedule",
    "allocation", "cash", "earnings_event", "news_sentiment",
}

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


class RuleContext:
    """Everything a rule may look at, assembled once per evaluation batch."""

    def __init__(
        self,
        prices: dict[str, Decimal],
        previous_closes: dict[str, Decimal],
        portfolio_view: dict[str, Any],
        indicator_fn: Callable[[str, str, int], float | None],
        recent_dividends: dict[str, datetime],
        now: datetime | None = None,
    ):
        self.prices = prices
        self.previous_closes = previous_closes
        self.portfolio = portfolio_view
        self.indicator_fn = indicator_fn
        self.recent_dividends = recent_dividends
        self.now = now or datetime.now(timezone.utc)


def validate_trigger(node: Any) -> None:
    """Raise ValueError on malformed ASTs so bad rules are rejected at save
    time rather than silently never firing."""
    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError("Each trigger node must be an object with exactly one key")
    key, value = next(iter(node.items()))
    if key in ("all", "any"):
        if not isinstance(value, list) or not value:
            raise ValueError(f"'{key}' requires a non-empty list of nodes")
        for child in value:
            validate_trigger(child)
        return
    if key == "not":
        validate_trigger(value)
        return
    if key not in KNOWN_LEAVES:
        raise ValueError(f"Unknown condition type: {key}")
    if not isinstance(value, dict):
        raise ValueError(f"'{key}' requires an object body")
    if key in ("price", "pct_move", "allocation"):
        if not value.get("symbol"):
            raise ValueError(f"'{key}' requires a symbol")
    if key in ("price", "pct_move", "allocation", "cash"):
        if value.get("op") not in OPS or "value" not in value:
            raise ValueError(f"'{key}' requires op (<,<=,>,>=) and value")
    if key == "indicator":
        if not value.get("symbol") or not value.get("name"):
            raise ValueError("'indicator' requires symbol and name")
        if value.get("op") not in OPS or "value" not in value:
            raise ValueError("'indicator' requires op and value")
        if not isinstance(value.get("period", 14), int) or value.get("period", 14) <= 0:
            raise ValueError("'indicator' period must be a positive integer")
    if key == "schedule":
        at = value.get("at", "")
        try:
            hh, mm = at.split(":")
            assert 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
        except (ValueError, AssertionError):
            raise ValueError("'schedule' requires at:\"HH:MM\" (UTC)")
        for d in value.get("days", []):
            if d not in DAYS:
                raise ValueError(f"'schedule' days must be from {DAYS}")
    if key == "dividend_event" and not value.get("symbol"):
        raise ValueError("'dividend_event' requires a symbol")


def referenced_symbols(node: dict) -> set[str]:
    key, value = next(iter(node.items()))
    if key in ("all", "any"):
        out: set[str] = set()
        for child in value:
            out |= referenced_symbols(child)
        return out
    if key == "not":
        return referenced_symbols(value)
    symbol = value.get("symbol") if isinstance(value, dict) else None
    return {symbol.upper()} if symbol else set()


def has_schedule(node: dict) -> bool:
    key, value = next(iter(node.items()))
    if key in ("all", "any"):
        return any(has_schedule(c) for c in value)
    if key == "not":
        return has_schedule(value)
    return key == "schedule"


def evaluate(node: dict, ctx: RuleContext) -> bool:
    key, value = next(iter(node.items()))
    if key == "all":
        return all(evaluate(child, ctx) for child in value)
    if key == "any":
        return any(evaluate(child, ctx) for child in value)
    if key == "not":
        return not evaluate(value, ctx)

    if key == "price":
        price = ctx.prices.get(value["symbol"].upper())
        if price is None:
            return False
        return OPS[value["op"]](float(price), float(value["value"]))

    if key == "pct_move":
        symbol = value["symbol"].upper()
        price = ctx.prices.get(symbol)
        prev = ctx.previous_closes.get(symbol)
        if price is None or not prev:
            return False
        move = (float(price) - float(prev)) / float(prev) * 100
        return OPS[value["op"]](move, float(value["value"]))

    if key == "indicator":
        result = ctx.indicator_fn(
            value["symbol"].upper(), value["name"], int(value.get("period", 14))
        )
        if result is None:
            return False
        return OPS[value["op"]](result, float(value["value"]))

    if key == "dividend_event":
        applied = ctx.recent_dividends.get(value["symbol"].upper())
        if applied is None:
            return False
        window = timedelta(days=int(value.get("within_days", 3)))
        return ctx.now - applied <= window

    if key == "schedule":
        hh, mm = value["at"].split(":")
        days = value.get("days") or DAYS
        return (
            ctx.now.hour == int(hh)
            and ctx.now.minute == int(mm)
            and DAYS[ctx.now.weekday()] in days
        )

    if key == "allocation":
        symbol = value["symbol"].upper()
        total = Decimal(ctx.portfolio["total_value"])
        if total <= 0:
            return False
        holding = next(
            (h for h in ctx.portfolio["holdings"] if h["symbol"] == symbol), None
        )
        mv = Decimal(holding["market_value"]) if holding and holding["market_value"] else Decimal("0")
        pct = float(mv / total * 100)
        return OPS[value["op"]](pct, float(value["value"]))

    if key == "cash":
        return OPS[value["op"]](
            float(Decimal(ctx.portfolio["cash_balance"])), float(value["value"])
        )

    if key in ("earnings_event", "news_sentiment"):
        return False  # awaiting a real data source; never fabricate

    raise ValueError(f"Unknown condition type: {key}")
