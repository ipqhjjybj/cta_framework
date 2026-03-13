"""
Event dataclasses for the CTA backtesting framework.

All events are immutable (frozen=True) to prevent state pollution.
Priority ordering: MARKET(4) > SIGNAL(3) > ORDER(2) > FILL(1)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Literal


class EventPriority(IntEnum):
    FILL = 1
    ORDER = 2
    SIGNAL = 3
    MARKET = 4


class OrderType(str):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderSide(str):
    BUY = "BUY"
    SELL = "SELL"


class SignalDirection(str):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"


@dataclass(frozen=True)
class MarketEvent:
    """
    Fired by DataHandler for each new bar of OHLCV data.
    One event per symbol per timestamp.
    """

    priority: int = EventPriority.MARKET
    symbol: str = ""
    timestamp: datetime = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("MarketEvent requires a non-empty symbol")
        if self.timestamp is None:
            raise ValueError("MarketEvent requires a timestamp")
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")


@dataclass(frozen=True)
class SignalEvent:
    """
    Fired by Strategy when a trade signal is generated.
    Contains the raw signal before position sizing.
    """

    priority: int = EventPriority.SIGNAL
    symbol: str = ""
    timestamp: datetime = None
    direction: str = SignalDirection.LONG  # LONG | SHORT | EXIT
    strength: float = 1.0  # 0.0 – 1.0, used for position sizing
    strategy_id: str = ""

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("SignalEvent requires a non-empty symbol")
        if self.timestamp is None:
            raise ValueError("SignalEvent requires a timestamp")
        if self.direction not in (
            SignalDirection.LONG,
            SignalDirection.SHORT,
            SignalDirection.EXIT,
        ):
            raise ValueError(f"Invalid signal direction: {self.direction}")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"strength must be in [0, 1], got {self.strength}")


@dataclass(frozen=True)
class OrderEvent:
    """
    Fired by Portfolio after translating a signal into a sized order.
    """

    priority: int = EventPriority.ORDER
    symbol: str = ""
    timestamp: datetime = None
    order_type: str = OrderType.MARKET  # MARKET | LIMIT | STOP
    side: str = OrderSide.BUY  # BUY | SELL
    quantity: float = 0.0
    price: float | None = None  # None for MARKET orders

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("OrderEvent requires a non-empty symbol")
        if self.timestamp is None:
            raise ValueError("OrderEvent requires a timestamp")
        if self.quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {self.quantity}")
        if self.order_type in (OrderType.LIMIT, OrderType.STOP) and self.price is None:
            raise ValueError(f"{self.order_type} order requires a price")


@dataclass(frozen=True)
class FillEvent:
    """
    Fired by ExecutionHandler after an order is simulated/executed.
    Represents the actual fill including costs.
    """

    priority: int = EventPriority.FILL
    symbol: str = ""
    timestamp: datetime = None
    side: str = OrderSide.BUY  # BUY | SELL
    quantity: float = 0.0
    fill_price: float = 0.0  # price after slippage
    commission: float = 0.0  # total commission paid
    slippage: float = 0.0  # slippage cost (informational)
    order_ref: str = ""  # reference back to the originating order

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("FillEvent requires a non-empty symbol")
        if self.timestamp is None:
            raise ValueError("FillEvent requires a timestamp")
        if self.quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {self.quantity}")
        if self.fill_price <= 0:
            raise ValueError(f"fill_price must be > 0, got {self.fill_price}")
        if self.commission < 0:
            raise ValueError(f"commission must be >= 0, got {self.commission}")

    @property
    def notional(self) -> float:
        """Total notional value of the fill (excluding costs)."""
        return self.quantity * self.fill_price

    @property
    def total_cost(self) -> float:
        """Total cash impact: notional + commission + slippage."""
        sign = 1 if self.side == OrderSide.BUY else -1
        return sign * self.notional + self.commission
