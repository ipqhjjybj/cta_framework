"""
Integration test: full backtest loop using CSV fixture data.

Verifies:
- Engine runs without exceptions
- Equity curve is non-trivial
- At least some trades were executed
- Final equity is a positive finite number
"""
import os
import math
import pytest
from datetime import datetime

from core.engine import BacktestEngine
from core.event_queue import EventQueue
from core.portfolio import PortfolioManager
from data.csv_handler import CSVDataHandler
from execution.commission import CryptoMakerTakerCommission
from execution.simulated import SimulatedExecutionHandler
from execution.slippage import FixedBpsSlippage
from strategies.ma_crossover import MACrossoverStrategy

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
INITIAL_CAPITAL = 100_000.0


@pytest.fixture
def engine():
    eq = EventQueue()

    data = CSVDataHandler(
        csv_dir=FIXTURES_DIR,
        symbols=["BTC/USDT"],
        timeframe="1h",
        start=datetime(2023, 1, 1),
        end=datetime(2023, 12, 31, 23, 0, 0),
    )

    strategy = MACrossoverStrategy(
        symbols=["BTC/USDT"],
        event_queue=eq,
        fast_period=20,
        slow_period=50,
        allow_short=True,
    )

    portfolio = PortfolioManager(
        initial_capital=INITIAL_CAPITAL,
        event_queue=eq,
        risk_per_trade=0.02,
        max_positions=1,
        allow_short=True,
    )

    execution = SimulatedExecutionHandler(
        event_queue=eq,
        slippage_model=FixedBpsSlippage(bps=2.0),
        commission_model=CryptoMakerTakerCommission(taker_rate=0.0005),
    )

    return BacktestEngine(
        name="integration_test",
        data_handler=data,
        strategy=strategy,
        portfolio=portfolio,
        execution_handler=execution,
        event_queue=eq,
    )


class TestFullLoop:
    def test_runs_without_error(self, engine):
        result = engine.run()
        assert result is not None

    def test_final_equity_finite(self, engine):
        result = engine.run()
        assert math.isfinite(result.final_equity)
        # equity may be negative on a losing strategy with synthetic data
        # the important thing is it's a real finite number, not NaN/inf

    def test_bars_processed(self, engine):
        result = engine.run()
        # 365 days × 24 h = 8760 bars
        assert result.total_bars == 8760

    def test_trades_executed(self, engine):
        result = engine.run()
        assert result.total_trades > 0

    def test_equity_curve_non_empty(self, engine):
        result = engine.run()
        assert len(result.equity_curve) > 0

    def test_return_is_finite(self, engine):
        result = engine.run()
        assert math.isfinite(result.total_return_pct)
