"""
BacktestEngine — the main event-dispatch loop.

Orchestrates:
  DataHandler → EventQueue → Strategy / Portfolio / ExecutionHandler

Event loop invariant:
  For each bar timestamp:
    1. Enqueue MarketEvents for all symbols.
    2. Drain the queue (MARKET → SIGNAL → ORDER → FILL) until empty.
    3. Call portfolio.on_market() to update floating P&L.
  Repeat for the next timestamp.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from core.data_handler import DataHandler
from core.event_queue import EventQueue
from core.events import FillEvent, MarketEvent, OrderEvent, SignalEvent
from core.execution_handler import ExecutionHandler
from core.portfolio import PortfolioManager
from core.strategy import Strategy
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestResult:
    """Summary result returned after a completed backtest."""

    name: str
    start: datetime
    end: datetime
    initial_capital: float
    final_equity: float
    total_bars: int
    total_trades: int
    total_commission: float
    elapsed_seconds: float
    equity_curve: List[tuple] = field(default_factory=list)

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.initial_capital - 1.0) * 100.0


class BacktestEngine:
    """
    Single-threaded, deterministic backtest engine.

    Usage:
        engine = BacktestEngine(
            name="my_backtest",
            data_handler=csv_handler,
            strategy=ma_strategy,
            portfolio=portfolio_mgr,
            execution_handler=sim_exec,
        )
        result = engine.run()
    """

    def __init__(
        self,
        name: str,
        data_handler: DataHandler,
        strategy: Strategy,
        portfolio: PortfolioManager,
        execution_handler: ExecutionHandler,
        event_queue: Optional[EventQueue] = None,
    ) -> None:
        self._name = name
        self._data = data_handler
        self._strategy = strategy
        self._portfolio = portfolio
        self._execution = execution_handler
        # NOTE: Do NOT use `event_queue or EventQueue()` — EventQueue has __len__,
        # so an empty queue is falsy, which would create a new queue by mistake.
        self._eq = event_queue if event_queue is not None else EventQueue()

        self._total_bars = 0
        self._total_trades = 0

    def run(self) -> BacktestResult:
        """Execute the backtest and return a BacktestResult."""
        logger.info("=== Backtest '%s' starting ===", self._name)
        t0 = time.perf_counter()

        for bar_list in self._data.iter_bars():
            # 1. Update price caches BEFORE draining so that
            #    portfolio.on_signal() can read current prices.
            for market_event in bar_list:
                self._execution.on_market(market_event)
                self._portfolio.on_market(market_event)

            # 2. Enqueue market events for strategy processing
            for market_event in bar_list:
                self._eq.put(market_event)

            # 3. Drain the event queue
            self._drain()

            self._total_bars += 1

        elapsed = time.perf_counter() - t0
        final_equity = self._portfolio.current_equity

        logger.info(
            "=== Backtest '%s' finished | bars=%d trades=%d "
            "equity=%.2f return=%.2f%% elapsed=%.2fs ===",
            self._name,
            self._total_bars,
            self._total_trades,
            final_equity,
            (final_equity / self._portfolio.initial_capital - 1) * 100,
            elapsed,
        )

        return BacktestResult(
            name=self._name,
            start=self._data.start,
            end=self._data.end,
            initial_capital=self._portfolio.initial_capital,
            final_equity=final_equity,
            total_bars=self._total_bars,
            total_trades=self._total_trades,
            total_commission=self._portfolio._total_commission,
            elapsed_seconds=elapsed,
            equity_curve=list(self._portfolio.equity_curve),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _drain(self) -> None:
        """Process all events in the queue until it is empty."""
        while not self._eq.empty():
            event = self._eq.get()

            if isinstance(event, MarketEvent):
                self._strategy.on_market(event)

            elif isinstance(event, SignalEvent):
                self._portfolio.on_signal(event)

            elif isinstance(event, OrderEvent):
                self._execution.on_order(event)

            elif isinstance(event, FillEvent):
                self._portfolio.on_fill(event)
                self._strategy.on_fill(event)
                self._total_trades += 1

            else:
                logger.warning("Unknown event type: %s", type(event))
