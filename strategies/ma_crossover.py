"""
Moving Average Crossover strategy.

Generates LONG signal when fast MA crosses above slow MA,
SHORT signal (if allow_short=True) when fast crosses below slow,
and EXIT signal when the opposing crossover occurs.
"""
from __future__ import annotations

from typing import List

from core.event_queue import EventQueue
from core.events import MarketEvent, SignalDirection, SignalEvent
from core.strategy import Strategy


def _sma(values: List[float], period: int) -> float:
    """Simple moving average of the last `period` values."""
    if len(values) < period:
        return float("nan")
    return sum(values[-period:]) / period


class MACrossoverStrategy(Strategy):
    """
    Dual SMA crossover strategy.

    Parameters
    ----------
    fast_period : int
        Look-back period for the fast MA (default 20).
    slow_period : int
        Look-back period for the slow MA (default 50).
    allow_short : bool
        Emit SHORT signals on bearish crossovers (default True).
    """

    def __init__(
        self,
        symbols: List[str],
        event_queue: EventQueue,
        fast_period: int = 20,
        slow_period: int = 50,
        allow_short: bool = True,
        strategy_id: str = "ma_crossover",
    ) -> None:
        if fast_period >= slow_period:
            raise ValueError(
                f"fast_period ({fast_period}) must be < slow_period ({slow_period})"
            )
        super().__init__(symbols, event_queue)
        self._fast = fast_period
        self._slow = slow_period
        self._allow_short = allow_short
        self._strategy_id = strategy_id

        # Track last crossover direction per symbol to avoid duplicate signals
        self._last_cross: dict[str, str] = {}

    @property
    def warmup_period(self) -> int:
        return self._slow

    def calculate_signals(self, event: MarketEvent) -> List[SignalEvent]:
        symbol = event.symbol
        closes = self.closes(symbol)

        fast_ma = _sma(closes, self._fast)
        slow_ma = _sma(closes, self._slow)

        if fast_ma != fast_ma or slow_ma != slow_ma:  # NaN check
            return []

        signals: List[SignalEvent] = []
        last = self._last_cross.get(symbol)

        if fast_ma > slow_ma and last != "bull":
            # Bullish crossover
            self._last_cross[symbol] = "bull"
            if last == "bear":
                # Close existing short first
                signals.append(
                    SignalEvent(
                        symbol=symbol,
                        timestamp=event.timestamp,
                        direction=SignalDirection.EXIT,
                        strategy_id=self._strategy_id,
                    )
                )
            signals.append(
                SignalEvent(
                    symbol=symbol,
                    timestamp=event.timestamp,
                    direction=SignalDirection.LONG,
                    strategy_id=self._strategy_id,
                )
            )

        elif fast_ma < slow_ma and last != "bear":
            # Bearish crossover
            self._last_cross[symbol] = "bear"
            if last == "bull":
                signals.append(
                    SignalEvent(
                        symbol=symbol,
                        timestamp=event.timestamp,
                        direction=SignalDirection.EXIT,
                        strategy_id=self._strategy_id,
                    )
                )
            if self._allow_short:
                signals.append(
                    SignalEvent(
                        symbol=symbol,
                        timestamp=event.timestamp,
                        direction=SignalDirection.SHORT,
                        strategy_id=self._strategy_id,
                    )
                )

        return signals
