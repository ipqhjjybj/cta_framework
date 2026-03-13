"""
Priority-based event queue for the CTA backtesting engine.

Priority ordering ensures causally correct event processing:
  MARKET(4) > SIGNAL(3) > ORDER(2) > FILL(1)

Uses a min-heap with negated priority so highest-priority events
are dequeued first.
"""
from __future__ import annotations

import heapq
import itertools
from typing import Union

from core.events import FillEvent, MarketEvent, OrderEvent, SignalEvent

AnyEvent = Union[MarketEvent, SignalEvent, OrderEvent, FillEvent]


class EventQueue:
    """
    Thread-unsafe priority queue optimised for single-threaded backtesting.

    Items are stored as (-priority, sequence, event) tuples so that:
    - Higher-priority events are popped first (negated priority → min-heap).
    - Equal-priority events maintain insertion order (sequence counter).
    """

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, AnyEvent]] = []
        self._counter = itertools.count()

    def put(self, event: AnyEvent) -> None:
        """Enqueue an event. O(log n)."""
        seq = next(self._counter)
        heapq.heappush(self._heap, (-event.priority, seq, event))

    def get(self) -> AnyEvent:
        """
        Dequeue the highest-priority event. O(log n).
        Raises IndexError if the queue is empty.
        """
        _, _, event = heapq.heappop(self._heap)
        return event

    def empty(self) -> bool:
        """Return True if the queue has no pending events."""
        return len(self._heap) == 0

    def __len__(self) -> int:
        return len(self._heap)
