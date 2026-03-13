"""
Trade-level statistics.

A TradeRecord captures a complete round-trip (open → close).
TradeStatsCollector converts FillEvent streams into TradeRecords.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from core.events import FillEvent, OrderSide


@dataclass
class TradeRecord:
    """Represents a completed round-trip trade."""

    symbol: str
    side: str  # "LONG" | "SHORT"
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    commission: float

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.commission

    @property
    def duration_hours(self) -> float:
        delta = self.exit_time - self.entry_time
        return delta.total_seconds() / 3600.0

    @property
    def return_pct(self) -> float:
        cost_basis = self.entry_price * self.quantity
        if cost_basis == 0:
            return 0.0
        return self.net_pnl / cost_basis * 100.0


@dataclass
class _OpenTrade:
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    quantity: float
    commission: float


class TradeStatsCollector:
    """
    Converts a sequence of FillEvents into TradeRecords.

    Call `on_fill(fill)` for each fill; completed trades are stored in
    `self.trades`.
    """

    def __init__(self) -> None:
        self._open: Dict[str, _OpenTrade] = {}
        self.trades: List[TradeRecord] = []

    def on_fill(self, fill: FillEvent) -> None:
        symbol = fill.symbol

        if fill.side == OrderSide.BUY:
            if symbol in self._open and self._open[symbol].side == "SHORT":
                # Closing a short
                open_trade = self._open.pop(symbol)
                gross_pnl = fill.quantity * (open_trade.entry_price - fill.fill_price)
                self.trades.append(TradeRecord(
                    symbol=symbol,
                    side="SHORT",
                    entry_time=open_trade.entry_time,
                    exit_time=fill.timestamp,
                    entry_price=open_trade.entry_price,
                    exit_price=fill.fill_price,
                    quantity=fill.quantity,
                    gross_pnl=gross_pnl,
                    commission=open_trade.commission + fill.commission,
                ))
            else:
                # Opening a long
                self._open[symbol] = _OpenTrade(
                    symbol=symbol,
                    side="LONG",
                    entry_time=fill.timestamp,
                    entry_price=fill.fill_price,
                    quantity=fill.quantity,
                    commission=fill.commission,
                )

        else:  # SELL
            if symbol in self._open and self._open[symbol].side == "LONG":
                # Closing a long
                open_trade = self._open.pop(symbol)
                gross_pnl = fill.quantity * (fill.fill_price - open_trade.entry_price)
                self.trades.append(TradeRecord(
                    symbol=symbol,
                    side="LONG",
                    entry_time=open_trade.entry_time,
                    exit_time=fill.timestamp,
                    entry_price=open_trade.entry_price,
                    exit_price=fill.fill_price,
                    quantity=fill.quantity,
                    gross_pnl=gross_pnl,
                    commission=open_trade.commission + fill.commission,
                ))
            else:
                # Opening a short
                self._open[symbol] = _OpenTrade(
                    symbol=symbol,
                    side="SHORT",
                    entry_time=fill.timestamp,
                    entry_price=fill.fill_price,
                    quantity=fill.quantity,
                    commission=fill.commission,
                )

    def summary(self) -> dict:
        if not self.trades:
            return {"total_trades": 0}
        pnls = [t.net_pnl for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        return {
            "total_trades": len(self.trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate_pct": len(wins) / len(self.trades) * 100 if self.trades else 0,
            "avg_win": sum(wins) / len(wins) if wins else 0,
            "avg_loss": sum(losses) / len(losses) if losses else 0,
            "profit_factor": (
                abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float("inf")
            ),
            "total_net_pnl": sum(pnls),
            "avg_duration_hours": sum(t.duration_hours for t in self.trades) / len(self.trades),
        }
