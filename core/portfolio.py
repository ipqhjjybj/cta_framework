"""
PortfolioManager — translates SignalEvents into sized OrderEvents
and tracks P&L, positions, and equity curve.

Design decisions:
- PortfolioState is immutable (frozen dataclass); each update returns a new state.
- Position sizing: fixed-fraction of equity (risk_per_trade fraction).
- Supports LONG, SHORT, and EXIT directions.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Dict, List, Optional

from core.event_queue import EventQueue
from core.events import (
    FillEvent,
    MarketEvent,
    OrderEvent,
    OrderSide,
    OrderType,
    SignalDirection,
    SignalEvent,
)
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Position:
    """Immutable representation of a single open position."""

    symbol: str
    side: str  # "LONG" | "SHORT"
    quantity: float
    avg_entry_price: float
    realized_pnl: float = 0.0

    def market_value(self, current_price: float) -> float:
        if self.side == "LONG":
            return self.quantity * current_price
        else:  # SHORT
            return -self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        if self.side == "LONG":
            return self.quantity * (current_price - self.avg_entry_price)
        else:
            return self.quantity * (self.avg_entry_price - current_price)


@dataclass(frozen=True)
class PortfolioState:
    """Immutable snapshot of the portfolio at a single point in time."""

    timestamp: datetime
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    equity: float = 0.0  # cash + sum(market values)
    total_commission: float = 0.0

    def with_equity(self, equity: float) -> "PortfolioState":
        return replace(self, equity=equity)


class PortfolioManager:
    """
    Translates signals → orders and tracks portfolio state.

    State is stored as a list of PortfolioState snapshots (append-only),
    enabling full historical reconstruction.
    """

    def __init__(
        self,
        initial_capital: float,
        event_queue: EventQueue,
        risk_per_trade: float = 0.02,
        max_positions: int = 10,
        allow_short: bool = True,
    ) -> None:
        self._eq = event_queue
        self._risk_per_trade = risk_per_trade
        self._max_positions = max_positions
        self._allow_short = allow_short

        # Current mutable state (positions dict rebuilt on each fill)
        self._cash = initial_capital
        self._initial_capital = initial_capital
        self._positions: Dict[str, Position] = {}
        self._total_commission = 0.0

        # Equity history: list of (timestamp, equity)
        self.equity_curve: List[tuple[datetime, float]] = []
        # All portfolio state snapshots
        self.history: List[PortfolioState] = []

        # Latest market prices (updated on MarketEvent)
        self._prices: Dict[str, float] = {}

        self._snapshot(datetime.utcnow())

    # ------------------------------------------------------------------
    # Framework hooks
    # ------------------------------------------------------------------

    def on_market(self, event: MarketEvent) -> None:
        """Update current price; recalculate equity."""
        self._prices[event.symbol] = event.close
        self._record_equity(event.timestamp)

    def on_signal(self, event: SignalEvent) -> None:
        """Convert a signal into a sized order."""
        symbol = event.symbol
        direction = event.direction
        current_price = self._prices.get(symbol)

        if current_price is None:
            logger.warning("No price for %s; ignoring signal", symbol)
            return

        # EXIT: close existing position
        if direction == SignalDirection.EXIT:
            pos = self._positions.get(symbol)
            if pos is None:
                return
            side = OrderSide.SELL if pos.side == "LONG" else OrderSide.BUY
            self._eq.put(
                OrderEvent(
                    symbol=symbol,
                    timestamp=event.timestamp,
                    order_type=OrderType.MARKET,
                    side=side,
                    quantity=pos.quantity,
                )
            )
            return

        # Check position limits
        if len(self._positions) >= self._max_positions:
            if symbol not in self._positions:
                logger.debug("Max positions reached; ignoring signal for %s", symbol)
                return

        # LONG / SHORT: size the order
        if direction == SignalDirection.SHORT and not self._allow_short:
            return

        equity = self._current_equity()
        notional = equity * self._risk_per_trade
        quantity = notional / current_price
        if quantity <= 0:
            return

        order_side = OrderSide.BUY if direction == SignalDirection.LONG else OrderSide.SELL

        # Close opposite position first if it exists
        existing = self._positions.get(symbol)
        if existing and existing.side != direction:
            close_side = OrderSide.SELL if existing.side == "LONG" else OrderSide.BUY
            self._eq.put(
                OrderEvent(
                    symbol=symbol,
                    timestamp=event.timestamp,
                    order_type=OrderType.MARKET,
                    side=close_side,
                    quantity=existing.quantity,
                )
            )

        self._eq.put(
            OrderEvent(
                symbol=symbol,
                timestamp=event.timestamp,
                order_type=OrderType.MARKET,
                side=order_side,
                quantity=round(quantity, 8),
            )
        )

    def on_fill(self, event: FillEvent) -> None:
        """Update cash and positions from a fill."""
        symbol = event.symbol
        qty = event.quantity
        price = event.fill_price
        commission = event.commission

        self._total_commission += commission

        existing = self._positions.get(symbol)

        if event.side == OrderSide.BUY:
            # Opening or adding to a LONG, or covering a SHORT
            if existing and existing.side == "SHORT":
                # Covering short: pay to buy back at fill price.
                # Cash already contains the original short-sale proceeds,
                # so we simply deduct the buyback cost + commission.
                # Net P&L = (short_price - cover_price) * qty is implicit.
                pnl = qty * (existing.avg_entry_price - price)
                new_qty = existing.quantity - qty
                if new_qty <= 1e-10:
                    self._positions.pop(symbol, None)
                else:
                    self._positions[symbol] = replace(
                        existing,
                        quantity=new_qty,
                        realized_pnl=existing.realized_pnl + pnl,
                    )
                self._cash -= qty * price + commission
            else:
                # Opening / adding to LONG
                self._cash -= qty * price + commission
                if existing:
                    new_qty = existing.quantity + qty
                    new_avg = (
                        (existing.avg_entry_price * existing.quantity + price * qty)
                        / new_qty
                    )
                    self._positions[symbol] = replace(
                        existing, quantity=new_qty, avg_entry_price=new_avg
                    )
                else:
                    self._positions[symbol] = Position(
                        symbol=symbol,
                        side="LONG",
                        quantity=qty,
                        avg_entry_price=price,
                    )

        else:  # SELL
            if existing and existing.side == "LONG":
                # Closing LONG
                pnl = qty * (price - existing.avg_entry_price)
                new_qty = existing.quantity - qty
                self._cash += qty * price - commission
                if new_qty <= 1e-10:
                    self._positions.pop(symbol, None)
                else:
                    self._positions[symbol] = replace(
                        existing,
                        quantity=new_qty,
                        realized_pnl=existing.realized_pnl + pnl,
                    )
            else:
                # Opening SHORT
                self._cash += qty * price - commission
                if existing:
                    new_qty = existing.quantity + qty
                    new_avg = (
                        (existing.avg_entry_price * existing.quantity + price * qty)
                        / new_qty
                    )
                    self._positions[symbol] = replace(
                        existing, quantity=new_qty, avg_entry_price=new_avg
                    )
                else:
                    self._positions[symbol] = Position(
                        symbol=symbol,
                        side="SHORT",
                        quantity=qty,
                        avg_entry_price=price,
                    )

        self._record_equity(event.timestamp)
        logger.debug(
            "Fill processed: %s %s %.4f @ %.2f | cash=%.2f equity=%.2f",
            event.side, symbol, qty, price, self._cash, self._current_equity(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_equity(self) -> float:
        equity = self._cash
        for symbol, pos in self._positions.items():
            price = self._prices.get(symbol, pos.avg_entry_price)
            equity += pos.market_value(price)
        return equity

    def _record_equity(self, timestamp: datetime) -> None:
        equity = self._current_equity()
        self.equity_curve.append((timestamp, equity))

    def _snapshot(self, timestamp: datetime) -> None:
        equity = self._current_equity()
        self.history.append(
            PortfolioState(
                timestamp=timestamp,
                cash=self._cash,
                positions=dict(self._positions),
                equity=equity,
                total_commission=self._total_commission,
            )
        )

    @property
    def current_equity(self) -> float:
        return self._current_equity()

    @property
    def initial_capital(self) -> float:
        return self._initial_capital
