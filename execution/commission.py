"""
Commission models for simulated order execution.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.events import OrderSide


class CommissionModel(ABC):
    """Abstract base for commission models."""

    @abstractmethod
    def calculate(self, quantity: float, fill_price: float, side: str) -> float:
        """Return the commission amount for a fill (in quote currency)."""
        ...


class ZeroCommission(CommissionModel):
    """No commission."""

    def calculate(self, quantity: float, fill_price: float, side: str) -> float:
        return 0.0


class CryptoMakerTakerCommission(CommissionModel):
    """
    Standard crypto exchange maker/taker model.

    Simulated market orders use the taker rate.
    (Limit orders would use maker rate — extended in subclasses.)
    """

    def __init__(self, maker_rate: float = 0.0002, taker_rate: float = 0.0005) -> None:
        if maker_rate < 0 or taker_rate < 0:
            raise ValueError("Commission rates must be >= 0")
        self._maker = maker_rate
        self._taker = taker_rate

    def calculate(self, quantity: float, fill_price: float, side: str) -> float:
        notional = quantity * fill_price
        # All simulated market orders are taker
        return notional * self._taker

    def calculate_maker(self, quantity: float, fill_price: float) -> float:
        return quantity * fill_price * self._maker


class FixedFeeCommission(CommissionModel):
    """Fixed fee per trade (useful for futures)."""

    def __init__(self, fee_per_trade: float = 0.5) -> None:
        self._fee = fee_per_trade

    def calculate(self, quantity: float, fill_price: float, side: str) -> float:
        return self._fee


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_commission_model(config: "CommissionConfig") -> CommissionModel:  # noqa: F821
    """Construct a CommissionModel from a CommissionConfig."""
    if config.model == "zero":
        return ZeroCommission()
    if config.model == "crypto_maker_taker":
        return CryptoMakerTakerCommission(
            maker_rate=config.maker_rate,
            taker_rate=config.taker_rate,
        )
    raise ValueError(f"Unknown commission model: {config.model}")
