"""Unit tests for core/portfolio.py"""
import pytest
from datetime import datetime

from core.event_queue import EventQueue
from core.events import FillEvent, MarketEvent, OrderSide, SignalDirection, SignalEvent
from core.portfolio import PortfolioManager, Position

NOW = datetime(2023, 6, 1, 12, 0, 0)
CAPITAL = 100_000.0


def make_market(symbol="BTC/USDT", price=30000.0, ts=NOW):
    return MarketEvent(
        symbol=symbol, timestamp=ts,
        open=price, high=price * 1.01, low=price * 0.99, close=price, volume=100.0
    )


def make_fill(symbol="BTC/USDT", side=OrderSide.BUY, qty=1.0, price=30000.0,
              commission=15.0, ts=NOW):
    return FillEvent(
        symbol=symbol, timestamp=ts,
        side=side, quantity=qty, fill_price=price, commission=commission
    )


class TestPortfolioManager:
    @pytest.fixture
    def pm(self):
        eq = EventQueue()
        return PortfolioManager(
            initial_capital=CAPITAL,
            event_queue=eq,
            risk_per_trade=0.02,
            max_positions=5,
            allow_short=True,
        )

    def test_initial_equity(self, pm):
        assert pm.current_equity == CAPITAL

    def test_buy_fill_reduces_cash(self, pm):
        pm.on_market(make_market(price=30000.0))
        pm.on_fill(make_fill(qty=1.0, price=30000.0, commission=15.0))
        # cash should decrease by qty*price + commission
        expected_cash = CAPITAL - 30000.0 - 15.0
        assert abs(pm._cash - expected_cash) < 0.01

    def test_equity_stable_after_buy_at_same_price(self, pm):
        pm.on_market(make_market(price=30000.0))
        pm.on_fill(make_fill(qty=1.0, price=30000.0, commission=0.0))
        assert abs(pm.current_equity - CAPITAL) < 0.01

    def test_sell_fill_closes_long(self, pm):
        pm.on_market(make_market(price=30000.0))
        pm.on_fill(make_fill(qty=1.0, price=30000.0, commission=0.0))
        pm.on_market(make_market(price=31000.0))
        # Sell at higher price
        pm.on_fill(make_fill(side=OrderSide.SELL, qty=1.0, price=31000.0, commission=0.0))
        assert "BTC/USDT" not in pm._positions
        assert abs(pm._cash - (CAPITAL + 1000.0)) < 0.01

    def test_on_signal_emits_order(self, pm):
        eq = pm._eq
        pm.on_market(make_market(price=30000.0))
        pm.on_signal(SignalEvent(
            symbol="BTC/USDT", timestamp=NOW, direction=SignalDirection.LONG
        ))
        assert not eq.empty()

    def test_equity_curve_grows(self, pm):
        pm.on_market(make_market(price=30000.0))
        pm.on_market(make_market(price=31000.0))
        assert len(pm.equity_curve) >= 2

    def test_position_created_on_buy(self, pm):
        pm.on_market(make_market(price=30000.0))
        pm.on_fill(make_fill(qty=0.5, price=30000.0, commission=0.0))
        pos = pm._positions.get("BTC/USDT")
        assert pos is not None
        assert pos.side == "LONG"
        assert abs(pos.quantity - 0.5) < 1e-8

    def test_max_positions_respected(self, pm):
        """Should not emit an order when max positions reached for a new symbol."""
        # Fill 5 different symbols
        for i in range(5):
            sym = f"TOKEN{i}/USDT"
            pm._prices[sym] = 100.0
            from core.portfolio import Position
            pm._positions[sym] = Position(
                symbol=sym, side="LONG", quantity=1.0, avg_entry_price=100.0
            )
        # 6th signal for new symbol should be ignored
        pm._prices["NEW/USDT"] = 100.0
        pm.on_signal(SignalEvent(
            symbol="NEW/USDT", timestamp=NOW, direction=SignalDirection.LONG
        ))
        assert pm._eq.empty()
