"""
Bollinger Band Mean Reversion strategy.

Generates LONG when price closes below the lower band (oversold),
SHORT when price closes above the upper band (overbought).
Exits when price reverts to the middle band (SMA).
"""
from __future__ import annotations

import math
from typing import List

from core.event_queue import EventQueue
from core.events import MarketEvent, SignalDirection, SignalEvent
from core.strategy import Strategy


def _bollinger(closes: List[float], period: int, num_std: float):
    """Returns (middle, upper, lower) bands."""
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return mid, mid + num_std * std, mid - num_std * std


class MeanReversionStrategy(Strategy):
    """
    Bollinger Band mean reversion strategy.

    Parameters
    ----------
    period : int
        Look-back window for the Bollinger Band (default 20).
    num_std : float
        Number of standard deviations for band width (default 2.0).
    allow_short : bool
        Emit SHORT on upper-band touches (default True).
    """

    def __init__(
        self,
        symbols: List[str],
        event_queue: EventQueue,
        period: int = 20,
        num_std: float = 2.0,
        allow_short: bool = True,
        strategy_id: str = "mean_reversion",
    ) -> None:
        super().__init__(symbols, event_queue)
        self._period = period
        self._num_std = num_std
        self._allow_short = allow_short
        self._strategy_id = strategy_id
        self._position: dict[str, str | None] = {}

    @property
    def warmup_period(self) -> int:
        return self._period

    def calculate_signals(self, event: MarketEvent) -> List[SignalEvent]:
        symbol = event.symbol
        closes = self.closes(symbol)
        middle, upper, lower = _bollinger(closes, self._period, self._num_std)

        if middle is None:
            return []

        close = event.close
        current_pos = self._position.get(symbol)
        signals: List[SignalEvent] = []

        if close < lower and current_pos != "LONG":
            # Oversold: go long
            if current_pos == "SHORT":
                signals.append(self._signal(symbol, event, SignalDirection.EXIT))
            signals.append(self._signal(symbol, event, SignalDirection.LONG))
            self._position[symbol] = "LONG"

        elif close > upper and current_pos != "SHORT":
            # Overbought: go short
            if current_pos == "LONG":
                signals.append(self._signal(symbol, event, SignalDirection.EXIT))
            if self._allow_short:
                signals.append(self._signal(symbol, event, SignalDirection.SHORT))
                self._position[symbol] = "SHORT"
            else:
                self._position[symbol] = None

        elif current_pos == "LONG" and close >= middle:
            # Mean reversion complete: exit long
            signals.append(self._signal(symbol, event, SignalDirection.EXIT))
            self._position[symbol] = None

        elif current_pos == "SHORT" and close <= middle:
            # Mean reversion complete: exit short
            signals.append(self._signal(symbol, event, SignalDirection.EXIT))
            self._position[symbol] = None

        return signals

    def _signal(self, symbol: str, event: MarketEvent, direction: str) -> SignalEvent:
        return SignalEvent(
            symbol=symbol,
            timestamp=event.timestamp,
            direction=direction,
            strategy_id=self._strategy_id,
        )
