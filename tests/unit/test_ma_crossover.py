"""Unit tests for strategies/ma_crossover.py"""
import pytest
from datetime import datetime, timedelta

from core.event_queue import EventQueue
from core.events import MarketEvent, SignalDirection
from strategies.ma_crossover import MACrossoverStrategy, _sma


def make_market(symbol, close, ts):
    return MarketEvent(
        symbol=symbol, timestamp=ts,
        open=close, high=close * 1.001, low=close * 0.999, close=close, volume=100.0
    )


class TestSma:
    def test_exact_window(self):
        assert _sma([1.0, 2.0, 3.0, 4.0, 5.0], 5) == 3.0

    def test_larger_list(self):
        assert _sma([1.0, 2.0, 3.0, 4.0, 5.0], 3) == 4.0

    def test_insufficient_data(self):
        result = _sma([1.0, 2.0], 5)
        assert result != result  # NaN


class TestMACrossoverStrategy:
    @pytest.fixture
    def setup(self):
        eq = EventQueue()
        strategy = MACrossoverStrategy(
            symbols=["BTC/USDT"],
            event_queue=eq,
            fast_period=3,
            slow_period=5,
            allow_short=True,
        )
        return strategy, eq

    def _feed_bars(self, strategy, prices, symbol="BTC/USDT"):
        """Feed a list of prices as market events."""
        base = datetime(2023, 1, 1)
        for i, price in enumerate(prices):
            event = make_market(symbol, price, base + timedelta(hours=i))
            strategy.on_market(event)

    def test_fast_must_be_less_than_slow(self):
        with pytest.raises(ValueError):
            MACrossoverStrategy(["BTC/USDT"], EventQueue(), fast_period=10, slow_period=5)

    def test_no_signal_during_warmup(self, setup):
        strategy, eq = setup
        # Feed slow_period bars (exactly warmup)
        self._feed_bars(strategy, [100.0] * 5)
        assert eq.empty()

    def test_bullish_crossover_emits_long(self, setup):
        strategy, eq = setup
        # Feed warmup bars flat, then spike up
        prices = [100.0] * 10 + [110.0, 112.0, 115.0, 118.0, 120.0]
        self._feed_bars(strategy, prices)
        signals = []
        while not eq.empty():
            signals.append(eq.get())
        long_signals = [s for s in signals if s.direction == SignalDirection.LONG]
        assert len(long_signals) >= 1

    def test_bearish_crossover_emits_exit_then_short(self, setup):
        strategy, eq = setup
        # First trigger a bullish crossover
        prices = [100.0] * 10 + [110.0, 115.0, 120.0, 125.0, 130.0]
        self._feed_bars(strategy, prices)
        # Drain queue
        while not eq.empty():
            eq.get()
        # Now trigger bearish crossover
        more_prices = [90.0, 85.0, 80.0, 75.0, 70.0]
        self._feed_bars(strategy, more_prices)
        signals = []
        while not eq.empty():
            signals.append(eq.get())
        directions = [s.direction for s in signals]
        assert SignalDirection.EXIT in directions
        assert SignalDirection.SHORT in directions

    def test_no_short_when_disabled(self):
        eq = EventQueue()
        strategy = MACrossoverStrategy(
            symbols=["BTC/USDT"],
            event_queue=eq,
            fast_period=3,
            slow_period=5,
            allow_short=False,
        )
        prices = [100.0] * 10 + [110.0, 115.0, 120.0, 125.0, 130.0]
        base = datetime(2023, 1, 1)
        for i, p in enumerate(prices):
            strategy.on_market(make_market("BTC/USDT", p, base + timedelta(hours=i)))
        while not eq.empty():
            eq.get()
        # Force bearish
        bear_prices = [90.0, 85.0, 80.0, 75.0, 70.0]
        for i, p in enumerate(bear_prices):
            ts = base + timedelta(hours=len(prices) + i)
            strategy.on_market(make_market("BTC/USDT", p, ts))
        signals = []
        while not eq.empty():
            signals.append(eq.get())
        assert all(s.direction != SignalDirection.SHORT for s in signals)
