"""
PerformanceAnalyzer — computes standard quantitative finance metrics
from an equity curve.

Metrics:
  - Total Return, CAGR
  - Sharpe Ratio (annualised)
  - Sortino Ratio (annualised)
  - Calmar Ratio
  - Maximum Drawdown (absolute & %)
  - Value at Risk (95% & 99%, historical)
  - Volatility (annualised)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class PerformanceMetrics:
    """Container for all computed performance metrics."""

    # Returns
    total_return_pct: float
    cagr_pct: float
    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    # Drawdown
    max_drawdown_pct: float
    max_drawdown_abs: float
    # Volatility
    annual_volatility_pct: float
    # VaR (negative = loss)
    var_95_pct: float
    var_99_pct: float
    # Meta
    start: datetime
    end: datetime
    duration_days: float
    bars_per_year: float


class PerformanceAnalyzer:
    """
    Computes performance metrics from an equity curve.

    Args:
        equity_curve: List of (timestamp, equity) tuples, sorted ascending.
        risk_free_rate: Annual risk-free rate (default 0.0).
        bars_per_year: Number of bars in a year for annualisation (default 8760 for 1h).
    """

    def __init__(
        self,
        equity_curve: List[Tuple[datetime, float]],
        risk_free_rate: float = 0.0,
        bars_per_year: float = 8760.0,
    ) -> None:
        if len(equity_curve) < 2:
            raise ValueError("Need at least 2 data points to compute metrics")
        self._curve = sorted(equity_curve, key=lambda x: x[0])
        self._rfr = risk_free_rate
        self._bars_per_year = bars_per_year

    def analyze(self) -> PerformanceMetrics:
        timestamps = [t for t, _ in self._curve]
        equities = np.array([e for _, e in self._curve], dtype=float)

        returns = np.diff(equities) / equities[:-1]  # bar-level returns

        start = timestamps[0]
        end = timestamps[-1]
        duration_days = (end - start).total_seconds() / 86400.0
        years = duration_days / 365.25

        # Total return
        total_ret = (equities[-1] / equities[0] - 1.0) * 100.0

        # CAGR (undefined when final equity is negative)
        if years > 0 and equities[-1] > 0 and equities[0] > 0:
            cagr = ((equities[-1] / equities[0]) ** (1.0 / years) - 1.0) * 100.0
        elif years > 0:
            # Approximate CAGR via total return sign
            cagr = (total_ret / 100.0 / years) * 100.0
        else:
            cagr = 0.0

        # Annualised volatility
        vol = float(np.std(returns, ddof=1)) * math.sqrt(self._bars_per_year) * 100.0

        # Sharpe
        excess = returns - self._rfr / self._bars_per_year
        sharpe = (
            float(np.mean(excess) / np.std(excess, ddof=1)) * math.sqrt(self._bars_per_year)
            if np.std(excess, ddof=1) > 0
            else 0.0
        )

        # Sortino (downside deviation)
        downside = returns[returns < 0]
        downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 1e-9
        sortino = (
            float(np.mean(excess)) / downside_std * math.sqrt(self._bars_per_year)
            if downside_std > 0
            else 0.0
        )

        # Maximum drawdown
        peak = np.maximum.accumulate(equities)
        dd = (equities - peak) / peak
        max_dd_pct = float(np.min(dd)) * 100.0
        max_dd_abs = float(np.min(equities - peak))

        # Calmar (CAGR / |MaxDD|) — undefined when drawdown is 0
        calmar = (cagr / abs(max_dd_pct)) if max_dd_pct != 0 else 0.0
        calmar = 0.0 if not math.isfinite(calmar) else calmar

        # VaR (historical, 1-bar horizon)
        var_95 = float(np.percentile(returns, 5)) * 100.0
        var_99 = float(np.percentile(returns, 1)) * 100.0

        return PerformanceMetrics(
            total_return_pct=round(total_ret, 4),
            cagr_pct=round(cagr, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            calmar_ratio=round(calmar, 4),
            max_drawdown_pct=round(max_dd_pct, 4),
            max_drawdown_abs=round(max_dd_abs, 2),
            annual_volatility_pct=round(vol, 4),
            var_95_pct=round(var_95, 4),
            var_99_pct=round(var_99, 4),
            start=start,
            end=end,
            duration_days=round(duration_days, 2),
            bars_per_year=self._bars_per_year,
        )
