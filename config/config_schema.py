"""
Pydantic configuration schema for the CTA backtesting framework.

All backtest parameters flow through BacktestConfig, which is validated
at startup so that configuration errors are caught before any data is read.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SlippageConfig(BaseModel):
    model: Literal["fixed_bps", "percentage", "zero"] = "fixed_bps"
    # fixed_bps: basis points applied to fill price
    bps: float = Field(default=2.0, ge=0)
    # percentage: fraction of price (e.g. 0.0002 = 2 bps)
    pct: float = Field(default=0.0002, ge=0)

    @model_validator(mode="after")
    def _check_params(self) -> "SlippageConfig":
        return self


class CommissionConfig(BaseModel):
    model: Literal["crypto_maker_taker", "zero"] = "crypto_maker_taker"
    maker_rate: float = Field(default=0.0002, ge=0, description="Maker fee rate")
    taker_rate: float = Field(default=0.0005, ge=0, description="Taker fee rate")


class DataConfig(BaseModel):
    source: Literal["csv", "ccxt"] = "csv"
    symbols: List[str] = Field(min_length=1)
    timeframe: str = "1h"
    start: datetime
    end: datetime
    # CSV-specific
    csv_dir: Optional[str] = None
    # CCXT-specific
    exchange: Optional[str] = None
    use_cache: bool = True
    cache_dir: str = ".cache/parquet"

    @field_validator("timeframe")
    @classmethod
    def _valid_timeframe(cls, v: str) -> str:
        from utils.timeframe import TIMEFRAME_TO_SECONDS

        if v not in TIMEFRAME_TO_SECONDS:
            raise ValueError(f"Unknown timeframe '{v}'")
        return v

    @model_validator(mode="after")
    def _end_after_start(self) -> "DataConfig":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class StrategyConfig(BaseModel):
    name: str
    params: Dict[str, Any] = Field(default_factory=dict)


class PortfolioConfig(BaseModel):
    initial_capital: float = Field(default=100_000.0, gt=0)
    position_sizing: Literal["fixed_fraction", "equal_weight"] = "fixed_fraction"
    risk_per_trade: float = Field(
        default=0.02, gt=0, le=1.0,
        description="Fraction of capital risked per trade (fixed_fraction mode)"
    )
    max_positions: int = Field(default=10, gt=0)
    allow_short: bool = True


class BacktestConfig(BaseModel):
    """Root configuration object. Load from YAML then validate."""

    name: str = "backtest"
    data: DataConfig
    strategy: StrategyConfig
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)
    commission: CommissionConfig = Field(default_factory=CommissionConfig)
    # Output
    output_dir: str = "results"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @classmethod
    def from_yaml(cls, path: str) -> "BacktestConfig":
        """Load and validate configuration from a YAML file."""
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return cls.model_validate(raw)
