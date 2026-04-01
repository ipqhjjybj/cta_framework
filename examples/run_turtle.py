"""
Example: Run the Turtle Trading System backtest.

Usage:
    cd cta_framework
    python examples/run_turtle.py

Custom params:
    python examples/run_turtle.py --entry 20 --exit 10 --trend 200 --no-short
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

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
from strategies.turtle import TurtleStrategy
from utils.logger import configure_root_logger, get_logger

configure_root_logger(level=logging.INFO)
logger = get_logger(__name__)


def run(
    csv_dir: str = "tests/fixtures",
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start: datetime = datetime(2023, 1, 1),
    end: datetime = datetime(2023, 12, 31, 23),
    initial_capital: float = 100_000.0,
    entry_period: int = 12,
    exit_period: int = 10,
    atr_period: int = 14,
    atr_stop_mult: float = 2.0,
    trend_period: int = 100,
    risk_per_trade: float = 0.01,    # 1% equity risked per ATR unit (ATR-based sizing)
    max_drawdown_pct: float = 0.20,  # circuit-breaker: stop new entries beyond -20% DD
    peak_lookback_bars: int = 6048,  # rolling peak window: 252 days × 24h; 0 = all-time peak
    adx_period: int = 0,             # ADX filter period (0 = disabled; 336 = 14 days on 1h)
    adx_min: float = 20.0,           # minimum ADX to allow new entries
    allow_short: bool = True,
    slippage_bps: float = 3.0,
    taker_rate: float = 0.0005,
    output_dir: str = "results/turtle",
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    eq = EventQueue()

    data = CSVDataHandler(
        csv_dir=csv_dir, symbols=[symbol], timeframe=timeframe, start=start, end=end
    )

    strategy = TurtleStrategy(
        symbols=[symbol],
        event_queue=eq,
        entry_period=entry_period,
        exit_period=exit_period,
        atr_period=atr_period,
        atr_stop_mult=atr_stop_mult,
        trend_period=trend_period,
        adx_period=adx_period,
        adx_min=adx_min,
        allow_short=allow_short,
    )

    portfolio = PortfolioManager(
        initial_capital=initial_capital,
        event_queue=eq,
        risk_per_trade=risk_per_trade,
        max_positions=1,
        allow_short=allow_short,
        max_drawdown_pct=max_drawdown_pct,
        peak_lookback_bars=peak_lookback_bars,
    )

    execution = SimulatedExecutionHandler(
        event_queue=eq,
        slippage_model=FixedBpsSlippage(bps=slippage_bps),
        commission_model=CryptoMakerTakerCommission(taker_rate=taker_rate),
    )

    trade_collector = TradeStatsCollector()
    _orig = portfolio.on_fill

    def _patched(fill):
        _orig(fill)
        trade_collector.on_fill(fill)

    portfolio.on_fill = _patched  # type: ignore[method-assign]

    engine = BacktestEngine(
        name=f"Turtle_{entry_period}_{exit_period}_{symbol.replace('/', '')}",
        data_handler=data,
        strategy=strategy,
        portfolio=portfolio,
        execution_handler=execution,
        event_queue=eq,
    )

    result = engine.run()

    metrics = PerformanceAnalyzer(result.equity_curve, bars_per_year=8760.0).analyze()
    ConsoleReporter().report(result, metrics, trade_collector)

    equity_path = os.path.join(output_dir, "equity_curve.png")
    try:
        plot_equity_curve(
            result.equity_curve, output_path=equity_path,
            title=f"Turtle {entry_period}/{exit_period} — {symbol}",
            initial_capital=initial_capital,
        )
        plot_monthly_returns(
            result.equity_curve,
            output_path=os.path.join(output_dir, "monthly_returns.png"),
        )
    except Exception as e:
        logger.warning("Chart failed: %s", e)
        equity_path = None

    HTMLReporter().report(
        result, metrics,
        output_path=os.path.join(output_dir, "report.html"),
        trade_collector=trade_collector,
        equity_img=equity_path,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Turtle Trading System backtest")
    parser.add_argument("--csv-dir",   default="tests/fixtures")
    parser.add_argument("--symbol",    default="BTC/USDT")
    parser.add_argument("--start",     default="2023-01-01")
    parser.add_argument("--end",       default="2023-12-31")
    parser.add_argument("--capital",   type=float, default=100_000.0)
    parser.add_argument("--entry",     type=int,   default=12)
    parser.add_argument("--exit",      type=int,   default=10)
    parser.add_argument("--atr",       type=int,   default=14)
    parser.add_argument("--atr-mult",  type=float, default=2.0)
    parser.add_argument("--trend",     type=int,   default=100,
                        help="SMA trend filter period (0 = disable)")
    parser.add_argument("--risk",      type=float, default=0.01)
    parser.add_argument("--max-dd",    type=float, default=0.20,
                        help="Circuit-breaker max drawdown (0-1, default 0.20 = 20%%)")
    parser.add_argument("--peak-lookback", type=int, default=6048,
                        help="Rolling window bars for peak equity (default 6048 = 252 days on 1h; 0 = all-time peak, never resets)")
    parser.add_argument("--adx",       type=int,   default=0,
                        help="ADX filter period (0=disabled; 336=14days on 1h). Blocks new entries when ADX < adx-min.")
    parser.add_argument("--adx-min",   type=float, default=20.0,
                        help="Minimum ADX value to allow new entries (default 20; typical range 20-25)")
    parser.add_argument("--no-short",  action="store_true")
    parser.add_argument("--output-dir", default="results/turtle")
    args = parser.parse_args()

    run(
        csv_dir=args.csv_dir,
        symbol=args.symbol,
        start=datetime.fromisoformat(args.start),
        end=datetime.fromisoformat(args.end),
        initial_capital=args.capital,
        entry_period=args.entry,
        exit_period=args.exit,
        atr_period=args.atr,
        atr_stop_mult=args.atr_mult,
        trend_period=args.trend,
        allow_short=not args.no_short,
        risk_per_trade=args.risk,
        max_drawdown_pct=args.max_dd,
        peak_lookback_bars=args.peak_lookback,
        adx_period=args.adx,
        adx_min=args.adx_min,
        output_dir=args.output_dir,
    )
