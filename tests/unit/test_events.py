"""Unit tests for core/events.py"""
import pytest
from datetime import datetime

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


# ---------------------------------------------------------------------------
# MarketEvent
# ---------------------------------------------------------------------------

class TestMarketEvent:
    def test_creates_valid_event(self):
        e = MarketEvent(
            symbol="BTC/USDT",
            timestamp=NOW,
            open=29000.0,
            high=30000.0,
            low=28500.0,
            close=29800.0,
            volume=1500.0,
        )
        assert e.symbol == "BTC/USDT"
        assert e.priority == EventPriority.MARKET

    def test_immutable(self):
        e = MarketEvent(symbol="BTC/USDT", timestamp=NOW, high=100.0, low=90.0)
        with pytest.raises((AttributeError, TypeError)):
            e.close = 99.0  # type: ignore[misc]

    def test_requires_symbol(self):
        with pytest.raises(ValueError, match="symbol"):
            MarketEvent(symbol="", timestamp=NOW)

    def test_requires_timestamp(self):
        with pytest.raises(ValueError, match="timestamp"):
            MarketEvent(symbol="BTC/USDT", timestamp=None)

    def test_high_must_be_gte_low(self):
        with pytest.raises(ValueError, match="high"):
            MarketEvent(symbol="BTC/USDT", timestamp=NOW, high=100.0, low=200.0)


# ---------------------------------------------------------------------------
# SignalEvent
# ---------------------------------------------------------------------------

class TestSignalEvent:
    def test_creates_long_signal(self):
        e = SignalEvent(
            symbol="ETH/USDT",
            timestamp=NOW,
            direction=SignalDirection.LONG,
            strength=0.8,
            strategy_id="ma_cross",
        )
        assert e.priority == EventPriority.SIGNAL
        assert e.direction == "LONG"

    def test_invalid_direction(self):
        with pytest.raises(ValueError, match="direction"):
            SignalEvent(symbol="BTC/USDT", timestamp=NOW, direction="INVALID")

    def test_strength_out_of_range(self):
        with pytest.raises(ValueError, match="strength"):
            SignalEvent(symbol="BTC/USDT", timestamp=NOW, strength=1.5)

    def test_exit_direction(self):
        e = SignalEvent(symbol="BTC/USDT", timestamp=NOW, direction=SignalDirection.EXIT)
        assert e.direction == "EXIT"


# ---------------------------------------------------------------------------
# OrderEvent
# ---------------------------------------------------------------------------

class TestOrderEvent:
    def test_market_order(self):
        e = OrderEvent(
            symbol="BTC/USDT",
            timestamp=NOW,
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=0.5,
        )
        assert e.priority == EventPriority.ORDER
        assert e.price is None

    def test_limit_order_requires_price(self):
        with pytest.raises(ValueError, match="price"):
            OrderEvent(
                symbol="BTC/USDT",
                timestamp=NOW,
                order_type=OrderType.LIMIT,
                side=OrderSide.BUY,
                quantity=0.5,
                price=None,
            )

    def test_limit_order_with_price(self):
        e = OrderEvent(
            symbol="BTC/USDT",
            timestamp=NOW,
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=0.5,
            price=29000.0,
        )
        assert e.price == 29000.0

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValueError, match="quantity"):
            OrderEvent(symbol="BTC/USDT", timestamp=NOW, quantity=0.0)


# ---------------------------------------------------------------------------
# FillEvent
# ---------------------------------------------------------------------------

class TestFillEvent:
    def _make_fill(self, **kwargs):
        defaults = dict(
            symbol="BTC/USDT",
            timestamp=NOW,
            side=OrderSide.BUY,
            quantity=0.5,
            fill_price=29500.0,
            commission=2.95,
            slippage=0.59,
        )
        defaults.update(kwargs)
        return FillEvent(**defaults)

    def test_notional(self):
        e = self._make_fill(quantity=1.0, fill_price=30000.0)
        assert e.notional == 30000.0

    def test_total_cost_buy(self):
        e = self._make_fill(quantity=1.0, fill_price=30000.0, commission=15.0, slippage=0.0)
        assert e.total_cost == 30015.0

    def test_total_cost_sell(self):
        e = self._make_fill(
            side=OrderSide.SELL, quantity=1.0, fill_price=30000.0,
            commission=15.0, slippage=0.0,
        )
        assert e.total_cost == -30000.0 + 15.0

    def test_negative_commission_rejected(self):
        with pytest.raises(ValueError, match="commission"):
            self._make_fill(commission=-1.0)

    def test_zero_fill_price_rejected(self):
        with pytest.raises(ValueError, match="fill_price"):
            self._make_fill(fill_price=0.0)

    def test_priority(self):
        e = self._make_fill()
        assert e.priority == EventPriority.FILL


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

class TestEventPriorities:
    def test_market_highest(self):
        assert EventPriority.MARKET > EventPriority.SIGNAL
        assert EventPriority.SIGNAL > EventPriority.ORDER
        assert EventPriority.ORDER > EventPriority.FILL
