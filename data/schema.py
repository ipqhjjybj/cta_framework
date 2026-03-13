"""
Pydantic schema for OHLCV bar data validation.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class OHLCVBar(BaseModel):
    """A single OHLCV candlestick bar."""

    symbol: str
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _high_gte_low(self) -> "OHLCVBar":
        if self.high < self.low:
            raise ValueError(
                f"[{self.symbol} @ {self.timestamp}] "
                f"high ({self.high}) must be >= low ({self.low})"
            )
        return self

    @model_validator(mode="after")
    def _ohlc_in_range(self) -> "OHLCVBar":
        for field in ("open", "close"):
            val = getattr(self, field)
            if not (self.low <= val <= self.high):
                raise ValueError(
                    f"[{self.symbol}] {field}={val} is outside [low={self.low}, high={self.high}]"
                )
        return self
