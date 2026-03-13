"""
Timeframe utility functions for the CTA backtesting framework.
"""
from __future__ import annotations

from datetime import timedelta


# Mapping from common string representations to pandas offset aliases
TIMEFRAME_TO_PANDAS: dict[str, str] = {
    "1m": "1min",
    "3m": "3min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1D",
    "3d": "3D",
    "1w": "1W",
    "1M": "1ME",
}

TIMEFRAME_TO_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
}


def to_timedelta(timeframe: str) -> timedelta:
    """Convert a timeframe string (e.g. '1h') to a timedelta."""
    seconds = TIMEFRAME_TO_SECONDS.get(timeframe)
    if seconds is None:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. "
            f"Supported: {sorted(TIMEFRAME_TO_SECONDS)}"
        )
    return timedelta(seconds=seconds)


def to_pandas_freq(timeframe: str) -> str:
    """Convert a timeframe string to a pandas frequency alias."""
    freq = TIMEFRAME_TO_PANDAS.get(timeframe)
    if freq is None:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. "
            f"Supported: {sorted(TIMEFRAME_TO_PANDAS)}"
        )
    return freq


def bars_per_year(timeframe: str) -> float:
    """Return the approximate number of bars in a year for a given timeframe."""
    seconds_per_year = 365.25 * 24 * 3600
    return seconds_per_year / TIMEFRAME_TO_SECONDS[timeframe]
