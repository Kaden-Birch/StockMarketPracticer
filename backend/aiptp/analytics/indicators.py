"""Technical indicators over daily closes. One implementation shared by
chart overlays, automation conditions, and (M5) backtests."""

from ..marketdata.service import MarketDataService


def sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period or period <= 0:
        return None
    return sum(closes[-period:]) / period


def ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    value = sum(closes[:period]) / period
    for close in closes[period:]:
        value = close * k + value * (1 - k)
    return value


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1 or period <= 0:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains += max(delta, 0)
        losses += max(-delta, 0)
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


INDICATORS = {"SMA": sma, "EMA": ema, "RSI": rsi}


def compute_indicator(
    market: MarketDataService, symbol: str, name: str, period: int
) -> float | None:
    """Compute an indicator from real daily history (1y window)."""
    fn = INDICATORS.get(name.upper())
    if fn is None:
        raise ValueError(f"Unknown indicator: {name}")
    hist = market.get_history(symbol, "1y", "1d")
    closes = [b.close for b in hist.bars if b.close is not None]
    return fn(closes, period)
