"""
SimulatedExecutionHandler — fills orders against bar data with
configurable slippage and commission models.

Supported order types:
  - MARKET: filled immediately at close price ± slippage
  - LIMIT:  filled if close crosses the limit price
  - STOP:   filled if close crosses the stop price (stop-market)
"""
from __future__ import annotations

import uuid
from typing import Dict, Optional

from core.event_queue import EventQueue
from core.events import FillEvent, MarketEvent, OrderEvent, OrderSide, OrderType
from core.execution_handler import ExecutionHandler
from execution.commission import CommissionModel
from execution.slippage import SlippageModel
from utils.logger import get_logger

logger = get_logger(__name__)


class SimulatedExecutionHandler(ExecutionHandler):
    """
    Simulates order fills against OHLCV bar data.

    Market orders are filled on the same bar at close price.
    Limit and stop orders are queued and checked on subsequent bars.
    """

    def __init__(
        self,
        event_queue: EventQueue,
        slippage_model: SlippageModel,
        commission_model: CommissionModel,
    ) -> None:
        self._eq = event_queue
        self._slippage = slippage_model
        self._commission = commission_model
        # Pending non-market orders: order_ref → OrderEvent
        self._pending: Dict[str, OrderEvent] = {}
        # Latest bar per symbol
        self._bars: Dict[str, MarketEvent] = {}

    def on_market(self, event: MarketEvent) -> None:
        """Update current bar and check pending limit/stop orders."""
        self._bars[event.symbol] = event
        self._check_pending(event)

    def on_order(self, event: OrderEvent) -> None:
        """Route incoming order to the appropriate handler."""
        if event.order_type == OrderType.MARKET:
            self._fill_market_order(event)
        elif event.order_type in (OrderType.LIMIT, OrderType.STOP):
            order_ref = str(uuid.uuid4())[:8]
            self._pending[order_ref] = event
            logger.debug("Queued %s order: %s", event.order_type, order_ref)
        else:
            logger.warning("Unknown order type: %s", event.order_type)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fill_market_order(self, event: OrderEvent) -> None:
        bar = self._bars.get(event.symbol)
        if bar is None:
            logger.warning(
                "No bar data for %s; cannot fill market order", event.symbol
            )
            return

        ref_price = bar.close
        fill_price = self._slippage.apply(ref_price, event.side, event.quantity, bar)
        commission = self._commission.calculate(event.quantity, fill_price, event.side)
        slippage_cost = abs(fill_price - ref_price) * event.quantity

        fill = FillEvent(
            symbol=event.symbol,
            timestamp=event.timestamp,
            side=event.side,
            quantity=event.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage_cost,
        )
        self._eq.put(fill)
        logger.debug(
            "FILL %s %s %.4f @ %.4f (slip=%.4f comm=%.4f)",
            event.side, event.symbol, event.quantity,
            fill_price, slippage_cost, commission,
        )

    def _check_pending(self, bar: MarketEvent) -> None:
        """Check if any pending limit/stop orders should now be filled."""
        filled_refs = []
        for ref, order in self._pending.items():
            if order.symbol != bar.symbol:
                continue
            triggered = self._is_triggered(order, bar)
            if triggered:
                self._fill_market_order(order)
                filled_refs.append(ref)

        for ref in filled_refs:
            del self._pending[ref]

    def _is_triggered(self, order: OrderEvent, bar: MarketEvent) -> bool:
        """Return True if a limit or stop order is triggered by the bar."""
        price = order.price
        if price is None:
            return False

        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY:
                return bar.low <= price  # buy limit: fill if price dips to limit
            else:
                return bar.high >= price  # sell limit: fill if price rises to limit

        if order.order_type == OrderType.STOP:
            if order.side == OrderSide.BUY:
                return bar.high >= price  # buy stop: fill on breakout above
            else:
                return bar.low <= price  # sell stop: fill on breakdown below

        return False
