"""
Example: Run a complete MA Crossover backtest and print results.

Usage:
    cd cta_framework
    python examples/run_ma_crossover.py

Or with a custom config:
    python examples/run_ma_crossover.py --config config/example_btc_ma.yaml
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from analytics.performance import PerformanceAnalyzer
from analytics.reporter import ConsoleReporter, HTMLReporter
from analytics.trade_stats import TradeStatsCollector
from analytics.visualizer import plot_equity_curve, plot_monthly_returns
from core.engine import BacktestEngine
from core.event_queue import EventQueue
from core.portfolio import PortfolioManager
from data.csv_handler import CSVDataHandler
from execution.commission import CryptoMakerTakerCommission
from execution.simulated import SimulatedExecutionHandler
from execution.slippage import FixedBpsSlippage
from strategies.ma_crossover import MACrossoverStrategy
from utils.logger import configure_root_logger, get_logger

import logging

configure_root_logger(level=logging.INFO)
logger = get_logger(__name__)


def run_backtest(
    csv_dir: str = "tests/fixtures",
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start: datetime = datetime(2023, 1, 1),
    end: datetime = datetime(2023, 12, 31, 23, 0, 0),
    initial_capital: float = 100_000.0,
    fast_period: int = 20,
    slow_period: int = 50,
    risk_per_trade: float = 0.02,
    slippage_bps: float = 2.0,
    taker_rate: float = 0.0005,
    output_dir: str = "results",
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    eq = EventQueue()

    # --- Data ---
    data = CSVDataHandler(
        csv_dir=csv_dir,
        symbols=[symbol],
        timeframe=timeframe,
        start=start,
        end=end,
    )

    # --- Strategy ---
    strategy = MACrossoverStrategy(
        symbols=[symbol],
        event_queue=eq,
        fast_period=fast_period,
        slow_period=slow_period,
        allow_short=True,
    )

    # --- Portfolio ---
    portfolio = PortfolioManager(
        initial_capital=initial_capital,
        event_queue=eq,
        risk_per_trade=risk_per_trade,
        max_positions=1,
        allow_short=True,
    )

    # --- Execution ---
    execution = SimulatedExecutionHandler(
        event_queue=eq,
        slippage_model=FixedBpsSlippage(bps=slippage_bps),
        commission_model=CryptoMakerTakerCommission(taker_rate=taker_rate),
    )

    # --- Trade collector (wired to fills) ---
    trade_collector = TradeStatsCollector()
    _orig_on_fill = portfolio.on_fill

    def _on_fill_with_stats(fill):
        _orig_on_fill(fill)
        trade_collector.on_fill(fill)

    portfolio.on_fill = _on_fill_with_stats  # type: ignore[method-assign]

    # --- Engine ---
    engine = BacktestEngine(
        name=f"MA_{fast_period}_{slow_period}_{symbol.replace('/', '')}",
        data_handler=data,
        strategy=strategy,
        portfolio=portfolio,
        execution_handler=execution,
        event_queue=eq,
    )

    result = engine.run()

    # --- Analytics ---
    analyzer = PerformanceAnalyzer(
        equity_curve=result.equity_curve,
        bars_per_year=8760.0,
    )
    metrics = analyzer.analyze()

    # --- Console report ---
    ConsoleReporter().report(result, metrics, trade_collector)

    # --- Charts ---
    equity_path = os.path.join(output_dir, "equity_curve.png")
    monthly_path = os.path.join(output_dir, "monthly_returns.png")
    try:
        plot_equity_curve(
            result.equity_curve,
            output_path=equity_path,
            title=f"Equity Curve — {result.name}",
            initial_capital=initial_capital,
        )
        plot_monthly_returns(result.equity_curve, output_path=monthly_path)
        logger.info("Charts saved to %s/", output_dir)
    except Exception as exc:
        logger.warning("Chart generation failed: %s", exc)
        equity_path = None

    # --- HTML report ---
    html_path = os.path.join(output_dir, "report.html")
    HTMLReporter().report(
        result,
        metrics,
        output_path=html_path,
        trade_collector=trade_collector,
        equity_img=equity_path,
    )
    logger.info("HTML report saved to %s", html_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MA Crossover backtest")
    parser.add_argument("--csv-dir", default="tests/fixtures")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    parser.add_argument("--risk", type=float, default=0.02)
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    run_backtest(
        csv_dir=args.csv_dir,
        symbol=args.symbol,
        start=datetime.fromisoformat(args.start),
        end=datetime.fromisoformat(args.end),
        initial_capital=args.capital,
        fast_period=args.fast,
        slow_period=args.slow,
        risk_per_trade=args.risk,
        output_dir=args.output_dir,
    )
