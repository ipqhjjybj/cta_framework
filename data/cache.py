"""
Parquet-based caching layer for OHLCV data.

Saves/loads DataFrames as Parquet files keyed by (symbol, timeframe, date-range).
Used by CCXTDataHandler to avoid redundant API calls.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)


def _cache_key(symbol: str, timeframe: str, start: datetime, end: datetime) -> str:
    raw = f"{symbol}|{timeframe}|{start.isoformat()}|{end.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


class ParquetCache:
    """
    Simple file-based Parquet cache for OHLCV DataFrames.

    Each cached dataset is stored as:
      <cache_dir>/<safe_symbol>_<timeframe>_<hash>.parquet
    """

    def __init__(self, cache_dir: str = ".cache/parquet") -> None:
        self._dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> str:
        key = _cache_key(symbol, timeframe, start, end)
        fname = f"{_safe_symbol(symbol)}_{timeframe}_{key}.parquet"
        return os.path.join(self._dir, fname)

    def get(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Optional[pd.DataFrame]:
        """Return cached DataFrame or None if not found."""
        path = self._path(symbol, timeframe, start, end)
        if not os.path.exists(path):
            return None
        logger.debug("Cache hit: %s", path)
        return pd.read_parquet(path)

    def set(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        df: pd.DataFrame,
    ) -> None:
        """Persist a DataFrame to the cache."""
        path = self._path(symbol, timeframe, start, end)
        df.to_parquet(path, index=True)
        logger.debug("Cached %d rows → %s", len(df), path)

    def invalidate(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> bool:
        """Remove a cached entry.  Returns True if a file was deleted."""
        path = self._path(symbol, timeframe, start, end)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
