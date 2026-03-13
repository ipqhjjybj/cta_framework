"""
Abstract Strategy base class.

A Strategy receives MarketEvents and FillEvents, maintains internal
indicator state, and emits SignalEvents via the event queue.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from core.event_queue import EventQueue
from core.events import FillEvent, MarketEvent, SignalEvent


class Strategy(ABC):
    """
    Base class for all CTA strategies.

    Subclasses must implement:
      - calculate_signals(event) → list of SignalEvents (may be empty)
      - warmup_period → int (number of bars needed before signals are valid)

    The base class manages:
      - Bar history per symbol (deque with maxlen = warmup_period * 2)
      - Warm-up bar counting per symbol
      - Routing of on_fill callbacks
    """

    def __init__(self, symbols: List[str], event_queue: EventQueue) -> None:
        self._symbols = symbols
        self._eq = event_queue
        self._bars: Dict[str, Deque[MarketEvent]] = defaultdict(
            lambda: deque(maxlen=self.warmup_period * 2 + 10)
        )
        self._bar_count: Dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def warmup_period(self) -> int:
        """Minimum number of bars required before emitting signals."""
        ...

    @abstractmethod
    def calculate_signals(self, event: MarketEvent) -> List[SignalEvent]:
        """
        Process a new bar and return any new SignalEvents.
        Called AFTER the bar has been appended to self._bars[symbol].
        Return an empty list if no signal should be emitted.
        """
        ...

    # ------------------------------------------------------------------
    # Framework hooks (called by BacktestEngine)
    # ------------------------------------------------------------------

    def on_market(self, event: MarketEvent) -> None:
        """
        Entry point called by the engine for every MarketEvent.
        Appends the bar, increments counters, and delegates to
        calculate_signals once warmed up.
        """
        symbol = event.symbol
        self._bars[symbol].append(event)
        self._bar_count[symbol] += 1

        if self._bar_count[symbol] <= self.warmup_period:
            return  # still warming up

        signals = self.calculate_signals(event)
        for sig in signals:
            self._eq.put(sig)

    def on_fill(self, event: FillEvent) -> None:
        """
        Called when a fill is confirmed.  Override in subclasses to
        update position tracking or strategy state.
        """

    # ------------------------------------------------------------------
    # Convenience helpers for subclasses
    # ------------------------------------------------------------------

    def bars(self, symbol: str) -> Deque[MarketEvent]:
        """Return the bar history deque for a symbol."""
        return self._bars[symbol]

    def closes(self, symbol: str, n: Optional[int] = None) -> List[float]:
        """Return the last n closing prices for a symbol."""
        history = list(self._bars[symbol])
        closes = [b.close for b in history]
        return closes if n is None else closes[-n:]

    def is_warmed_up(self, symbol: str) -> bool:
        return self._bar_count[symbol] > self.warmup_period
