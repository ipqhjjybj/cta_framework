"""Abstract ExecutionHandler base class."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.events import MarketEvent, OrderEvent


class ExecutionHandler(ABC):
    """
    Abstract interface for order execution.

    Receives OrderEvents, simulates (or sends) the trade, and places
    FillEvents back on the event queue.
    """

    @abstractmethod
    def on_order(self, event: OrderEvent) -> None:
        """Process an order and generate a FillEvent."""
        ...

    def on_market(self, event: MarketEvent) -> None:
        """
        Optional: called on each new bar so the handler can update
        its internal price reference for limit/stop order checking.
        """
