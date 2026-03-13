"""Unit tests for core/event_queue.py"""
import pytest
from datetime import datetime

from core.event_queue import EventQueue
from core.events import (
    EventPriority,
    FillEvent,
    MarketEvent,
    OrderEvent,
    OrderSide,
    OrderType,
    SignalDirection,
    SignalEvent,
)

NOW = datetime(2023, 6, 1, 12, 0, 0)


def make_market():
    return MarketEvent(symbol="BTC/USDT", timestamp=NOW, high=100.0, low=90.0)


def make_signal():
    return SignalEvent(symbol="BTC/USDT", timestamp=NOW, direction=SignalDirection.LONG)


def make_order():
    return OrderEvent(
        symbol="BTC/USDT", timestamp=NOW, side=OrderSide.BUY, quantity=1.0
    )


def make_fill():
    return FillEvent(
        symbol="BTC/USDT",
        timestamp=NOW,
        side=OrderSide.BUY,
        quantity=1.0,
        fill_price=99.0,
        commission=0.05,
    )


class TestEventQueue:
    def test_empty_on_creation(self):
        q = EventQueue()
        assert q.empty()
        assert len(q) == 0

    def test_put_and_get(self):
        q = EventQueue()
        m = make_market()
        q.put(m)
        assert not q.empty()
        assert len(q) == 1
        assert q.get() is m

    def test_priority_order(self):
        """MARKET should be dequeued before SIGNAL, ORDER, FILL."""
        q = EventQueue()
        fill = make_fill()
        order = make_order()
        signal = make_signal()
        market = make_market()

        # Put in reverse priority order
        q.put(fill)
        q.put(order)
        q.put(signal)
        q.put(market)

        assert q.get().priority == EventPriority.MARKET
        assert q.get().priority == EventPriority.SIGNAL
        assert q.get().priority == EventPriority.ORDER
        assert q.get().priority == EventPriority.FILL

    def test_fifo_within_same_priority(self):
        """Equal-priority events must come out in insertion order."""
        q = EventQueue()
        m1 = MarketEvent(symbol="BTC/USDT", timestamp=NOW, high=100.0, low=90.0)
        m2 = MarketEvent(symbol="ETH/USDT", timestamp=NOW, high=2000.0, low=1900.0)
        q.put(m1)
        q.put(m2)
        assert q.get() is m1
        assert q.get() is m2

    def test_get_raises_on_empty(self):
        q = EventQueue()
        with pytest.raises(IndexError):
            q.get()

    def test_len_tracks_size(self):
        q = EventQueue()
        assert len(q) == 0
        q.put(make_market())
        assert len(q) == 1
        q.put(make_signal())
        assert len(q) == 2
        q.get()
        assert len(q) == 1
