"""
Donchian Channel Breakout strategy.

Generates LONG when close exceeds the highest high of the last N bars,
SHORT when close breaks below the lowest low.
Uses a narrower exit channel to close positions.
"""
from __future__ import annotations

from typing import List

from core.event_queue import EventQueue
from core.events import MarketEvent, SignalDirection, SignalEvent
from core.strategy import Strategy


class BreakoutStrategy(Strategy):
    """
    Donchian Channel breakout strategy.

    Parameters
    ----------
    entry_period : int
        Look-back window for entry channel (default 20).
    exit_period : int
        Look-back window for exit channel (default 10).  Must be < entry_period.
    allow_short : bool
        Emit SHORT on downside breakouts (default True).
    """

    def __init__(
        self,
        symbols: List[str],
        event_queue: EventQueue,
        entry_period: int = 20,
        exit_period: int = 10,
        allow_short: bool = True,
        strategy_id: str = "breakout",
    ) -> None:
        if exit_period >= entry_period:
            raise ValueError("exit_period must be < entry_period")
        super().__init__(symbols, event_queue)
        self._entry = entry_period
        self._exit = exit_period
        self._allow_short = allow_short
        self._strategy_id = strategy_id
        self._position: dict[str, str | None] = {}  # symbol → "LONG"|"SHORT"|None

    @property
    def warmup_period(self) -> int:
        return self._entry

    def calculate_signals(self, event: MarketEvent) -> List[SignalEvent]:
        symbol = event.symbol
        bars = list(self.bars(symbol))
        if len(bars) < self._entry:
            return []

        highs = [b.high for b in bars[-self._entry:]]
        lows = [b.low for b in bars[-self._entry:]]
        exit_highs = [b.high for b in bars[-self._exit:]]
        exit_lows = [b.low for b in bars[-self._exit:]]

        channel_high = max(highs[:-1])  # exclude current bar
        channel_low = min(lows[:-1])
        exit_high = max(exit_highs[:-1])
        exit_low = min(exit_lows[:-1])

        current_pos = self._position.get(symbol)
        close = event.close
        signals: List[SignalEvent] = []

        # Entry signals
        if close > channel_high and current_pos != "LONG":
            if current_pos == "SHORT":
                signals.append(self._signal(symbol, event, SignalDirection.EXIT))
            signals.append(self._signal(symbol, event, SignalDirection.LONG))
            self._position[symbol] = "LONG"

        elif close < channel_low and current_pos != "SHORT":
            if current_pos == "LONG":
                signals.append(self._signal(symbol, event, SignalDirection.EXIT))
            if self._allow_short:
                signals.append(self._signal(symbol, event, SignalDirection.SHORT))
                self._position[symbol] = "SHORT"
            else:
                self._position[symbol] = None

        # Exit signals (narrow channel)
        elif current_pos == "LONG" and close < exit_low:
            signals.append(self._signal(symbol, event, SignalDirection.EXIT))
            self._position[symbol] = None

        elif current_pos == "SHORT" and close > exit_high:
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
