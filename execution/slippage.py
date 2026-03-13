"""
Slippage models for simulated order execution.

All models implement the SlippageModel protocol:
  apply(price, side, quantity, bar) → adjusted_price
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.events import MarketEvent, OrderSide


class SlippageModel(ABC):
    """Abstract base for slippage models."""

    @abstractmethod
    def apply(
        self,
        price: float,
        side: str,
        quantity: float,
        bar: Optional[MarketEvent] = None,
    ) -> float:
        """
        Return the fill price after applying slippage.

        Args:
            price:    The reference price (e.g. bar close).
            side:     OrderSide.BUY or OrderSide.SELL.
            quantity: Order size in base currency.
            bar:      The current bar (used by volume-based models).
        """
        ...


class ZeroSlippage(SlippageModel):
    """No slippage — fill at reference price."""

    def apply(self, price: float, side: str, quantity: float,
              bar: Optional[MarketEvent] = None) -> float:
        return price


class FixedBpsSlippage(SlippageModel):
    """
    Fixed basis-point slippage applied symmetrically.

    BUY  → price * (1 + bps/10_000)
    SELL → price * (1 - bps/10_000)
    """

    def __init__(self, bps: float = 2.0) -> None:
        if bps < 0:
            raise ValueError(f"bps must be >= 0, got {bps}")
        self._factor = bps / 10_000.0

    def apply(self, price: float, side: str, quantity: float,
              bar: Optional[MarketEvent] = None) -> float:
        if side == OrderSide.BUY:
            return price * (1.0 + self._factor)
        return price * (1.0 - self._factor)


class PercentageSlippage(SlippageModel):
    """
    Percentage-based slippage (same as FixedBps but expressed as a fraction).

    pct=0.0002 is equivalent to bps=2.
    """

    def __init__(self, pct: float = 0.0002) -> None:
        if pct < 0:
            raise ValueError(f"pct must be >= 0, got {pct}")
        self._pct = pct

    def apply(self, price: float, side: str, quantity: float,
              bar: Optional[MarketEvent] = None) -> float:
        if side == OrderSide.BUY:
            return price * (1.0 + self._pct)
        return price * (1.0 - self._pct)


class VolumeBasedSlippage(SlippageModel):
    """
    Volume-proportional slippage: larger orders relative to bar volume
    incur higher slippage (square-root market impact model).

    impact = base_bps + impact_bps * sqrt(quantity / bar.volume)
    """

    def __init__(self, base_bps: float = 1.0, impact_bps: float = 5.0) -> None:
        self._base = base_bps / 10_000.0
        self._impact = impact_bps / 10_000.0

    def apply(self, price: float, side: str, quantity: float,
              bar: Optional[MarketEvent] = None) -> float:
        if bar is None or bar.volume <= 0:
            # Fallback to base slippage
            factor = self._base
        else:
            import math
            participation = quantity / bar.volume
            factor = self._base + self._impact * math.sqrt(participation)

        if side == OrderSide.BUY:
            return price * (1.0 + factor)
        return price * (1.0 - factor)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_slippage_model(config: "SlippageConfig") -> SlippageModel:  # noqa: F821
    """Construct a SlippageModel from a SlippageConfig."""
    if config.model == "zero":
        return ZeroSlippage()
    if config.model == "fixed_bps":
        return FixedBpsSlippage(bps=config.bps)
    if config.model == "percentage":
        return PercentageSlippage(pct=config.pct)
    raise ValueError(f"Unknown slippage model: {config.model}")
