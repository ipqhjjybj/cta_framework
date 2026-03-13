"""
Supertrend Strategy — adaptive ATR-based trend following.

The Supertrend indicator places a dynamic support/resistance band around price
using ATR.  The direction flips only when price closes on the opposite side of
the band, making it robust against short-term noise.

Entry rules:
    LONG  when price crosses above the Supertrend band (trend flips UP)
    SHORT when price crosses below the Supertrend band (trend flips DOWN)

Exit rules:
    When the Supertrend itself flips to the opposite direction.
    No separate stop needed — the band acts as a trailing stop.

Optional trend filter:
    Long-term SMA (e.g. 4800 bars = 200 days on 1h) ensures trades are
    only taken in the direction of the macro trend.

Parameters
----------
atr_period   : ATR smoothing window  (default 14)
multiplier   : Band width = multiplier × ATR  (default 3.0)
trend_period : Long-term SMA filter period; 0 = disabled  (default 0)
allow_short  : Enable short trades  (default True)
strategy_id  : Identifier string on signals.

Best parameters for 1-hour crypto data
---------------------------------------
atr_period=14, multiplier=3.0 works well out-of-the-box.
For a slower, more conservative system use atr_period=48, multiplier=3.5.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from core.event_queue import EventQueue
from core.events import FillEvent, MarketEvent, OrderSide, SignalDirection, SignalEvent
from core.strategy import Strategy


def _atr(bars: list, period: int) -> Optional[float]:
    """Simple (non-EMA) ATR over the last *period* completed bars."""
    if len(bars) < period + 1:
        return None
    true_ranges = []
    for i in range(-period, 0):
        bar  = bars[i]
        prev = bars[i - 1]
        tr = max(
            bar.high - bar.low,
            abs(bar.high - prev.close),
            abs(bar.low  - prev.close),
        )
        true_ranges.append(tr)
    return sum(true_ranges) / period


def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


class SupertrendStrategy(Strategy):
    """
    Supertrend trend-following strategy.

    State tracked per symbol:
        _st_upper / _st_lower : Final (sticky) upper / lower bands
        _st_dir               : Current trend direction ("UP" | "DOWN" | None)
    """

    def __init__(
        self,
        symbols: List[str],
        event_queue: EventQueue,
        atr_period: int = 14,
        multiplier: float = 3.0,
        trend_period: int = 0,
        allow_short: bool = True,
        strategy_id: str = "supertrend",
    ) -> None:
        super().__init__(symbols, event_queue)
        self._atr_period  = atr_period
        self._mult        = multiplier
        self._trend       = trend_period
        self._allow_short = allow_short
        self._strategy_id = strategy_id

        # Per-symbol Supertrend state
        self._st_upper: Dict[str, Optional[float]] = {}
        self._st_lower: Dict[str, Optional[float]] = {}
        self._st_dir:   Dict[str, Optional[str]]   = {}

        # Strategy-level position tracking (separate from portfolio)
        self._position:   Dict[str, Optional[str]]   = {}
        self._last_atr:   Dict[str, Optional[float]] = {}

    @property
    def warmup_period(self) -> int:
        return max(self._atr_period + 1, self._trend if self._trend else 0)

    # ------------------------------------------------------------------
    # FillEvent — keep position state in sync with actual fills
    # ------------------------------------------------------------------

    def on_fill(self, event: FillEvent) -> None:
        symbol = event.symbol
        if event.side == OrderSide.BUY:
            if self._position.get(symbol) == "SHORT":
                self._position[symbol] = None
            else:
                self._position[symbol] = "LONG"
        else:
            if self._position.get(symbol) == "LONG":
                self._position[symbol] = None
            else:
                self._position[symbol] = "SHORT"

    # ------------------------------------------------------------------
    # Signal calculation — called each bar after warmup
    # ------------------------------------------------------------------

    def calculate_signals(self, event: MarketEvent) -> List[SignalEvent]:
        symbol = event.symbol
        bars   = list(self.bars(symbol))
        close  = event.close
        closes = [b.close for b in bars]

        # Need at least atr_period+2 bars so we have a "previous" bar
        if len(bars) < self._atr_period + 2:
            return []

        atr = _atr(bars, self._atr_period)
        if atr is None:
            return []
        self._last_atr[symbol] = atr

        # ---- Compute Supertrend bands ----
        current_bar = bars[-1]
        prev_bar    = bars[-2]
        midprice    = (current_bar.high + current_bar.low) / 2.0

        basic_upper = midprice + self._mult * atr
        basic_lower = midprice - self._mult * atr

        prev_upper = self._st_upper.get(symbol)
        prev_lower = self._st_lower.get(symbol)
        prev_close = prev_bar.close

        # Final Upper Band (sticky upward — only tightens when price is below it)
        if prev_upper is None:
            final_upper = basic_upper
        elif basic_upper < prev_upper or prev_close > prev_upper:
            final_upper = basic_upper
        else:
            final_upper = prev_upper

        # Final Lower Band (sticky downward — only rises when price is above it)
        if prev_lower is None:
            final_lower = basic_lower
        elif basic_lower > prev_lower or prev_close < prev_lower:
            final_lower = basic_lower
        else:
            final_lower = prev_lower

        # ---- Determine new trend direction ----
        prev_dir = self._st_dir.get(symbol)

        if prev_dir is None:
            # Initialise based on which side of the bands price is on
            if close > final_upper:
                new_dir = "UP"
            elif close < final_lower:
                new_dir = "DOWN"
            else:
                new_dir = None
        elif prev_dir == "UP":
            new_dir = "DOWN" if close < final_lower else "UP"
        else:  # prev_dir == "DOWN"
            new_dir = "UP"   if close > final_upper else "DOWN"

        # Update state
        self._st_upper[symbol] = final_upper
        self._st_lower[symbol] = final_lower
        self._st_dir[symbol]   = new_dir

        if new_dir is None or prev_dir == new_dir:
            return []  # No trend change this bar

        # ---- Trend flip detected ----
        # Optional macro trend filter
        if self._trend:
            sma = _sma(closes, self._trend)
            if new_dir == "UP"   and (sma is None or close < sma):
                return []
            if new_dir == "DOWN" and (sma is None or close > sma):
                return []

        current_pos = self._position.get(symbol)
        signals: List[SignalEvent] = []

        if new_dir == "UP":
            if not self._allow_short and current_pos == "SHORT":
                signals.append(self._sig(symbol, event, SignalDirection.EXIT))
                self._position[symbol] = None
            elif current_pos == "SHORT":
                signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            if current_pos != "LONG":
                signals.append(self._sig(symbol, event, SignalDirection.LONG, atr))
                self._position[symbol] = "LONG"

        elif new_dir == "DOWN" and self._allow_short:
            if current_pos == "LONG":
                signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            if current_pos != "SHORT":
                signals.append(self._sig(symbol, event, SignalDirection.SHORT, atr))
                self._position[symbol] = "SHORT"

        elif new_dir == "DOWN" and not self._allow_short:
            if current_pos == "LONG":
                signals.append(self._sig(symbol, event, SignalDirection.EXIT))
                self._position[symbol] = None

        return signals

    def _sig(
        self,
        symbol: str,
        event: MarketEvent,
        direction: str,
        atr: float | None = None,
    ) -> SignalEvent:
        # Encode ATR stop distance as strength for portfolio position sizing
        if atr is not None and event.close > 0:
            stop_dist_ratio = min((self._mult * atr) / event.close, 0.99)
        else:
            stop_dist_ratio = 1.0
        return SignalEvent(
            symbol=symbol,
            timestamp=event.timestamp,
            direction=direction,
            strength=stop_dist_ratio,
            strategy_id=self._strategy_id,
        )
