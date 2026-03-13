"""
CSV-based DataHandler for the CTA backtesting framework.

Expected CSV format (one file per symbol):
  timestamp,open,high,low,close,volume
  2023-01-01 00:00:00,16500.0,16600.0,16450.0,16550.0,1200.5
  ...

File naming convention:
  <SYMBOL_SAFE>_<TIMEFRAME>.csv
  e.g.  BTC_USDT_1h.csv  (slashes replaced with underscores)
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Iterator, List, Optional

import pandas as pd

from core.data_handler import DataHandler
from core.events import MarketEvent
from utils.logger import get_logger

logger = get_logger(__name__)


def _symbol_to_filename(symbol: str, timeframe: str) -> str:
    """Convert 'BTC/USDT' + '1h' → 'BTC_USDT_1h.csv'."""
    safe = symbol.replace("/", "_")
    return f"{safe}_{timeframe}.csv"


class CSVDataHandler(DataHandler):
    """
    Loads OHLCV data from CSV files for one or more symbols.

    Timestamps across all symbols are aligned using an outer join;
    missing bars for a symbol at a given timestamp are forward-filled.
    """

    _REQUIRED_COLS = {"open", "high", "low", "close", "volume"}

    def __init__(
        self,
        csv_dir: str,
        symbols: List[str],
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> None:
        self._csv_dir = csv_dir
        self._symbols = sorted(symbols)
        self._timeframe = timeframe
        self._start = start
        self._end = end
        self._data: Dict[str, pd.DataFrame] = {}
        self._aligned_index: pd.DatetimeIndex = pd.DatetimeIndex([])
        self._load()

    # ------------------------------------------------------------------
    # DataHandler interface
    # ------------------------------------------------------------------

    @property
    def symbols(self) -> List[str]:
        return list(self._symbols)

    @property
    def start(self) -> datetime:
        if len(self._aligned_index) == 0:
            raise RuntimeError("No data loaded")
        return self._aligned_index[0].to_pydatetime()

    @property
    def end(self) -> datetime:
        if len(self._aligned_index) == 0:
            raise RuntimeError("No data loaded")
        return self._aligned_index[-1].to_pydatetime()

    def iter_bars(self) -> Iterator[List[MarketEvent]]:
        """Yield one list of MarketEvents per aligned timestamp."""
        for ts in self._aligned_index:
            events: List[MarketEvent] = []
            for symbol in self._symbols:
                df = self._data[symbol]
                if ts not in df.index:
                    continue
                row = df.loc[ts]
                events.append(
                    MarketEvent(
                        symbol=symbol,
                        timestamp=ts.to_pydatetime(),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
            if events:
                yield events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Read CSV files and align timestamps."""
        frames: Dict[str, pd.DataFrame] = {}
        for symbol in self._symbols:
            fname = _symbol_to_filename(symbol, self._timeframe)
            fpath = os.path.join(self._csv_dir, fname)
            if not os.path.exists(fpath):
                raise FileNotFoundError(
                    f"CSV file not found for symbol '{symbol}': {fpath}"
                )
            df = self._read_csv(fpath, symbol)
            frames[symbol] = df

        # Build aligned index (intersection keeps only timestamps where
        # ALL symbols have data; use 'outer' + ffill for partial bars)
        all_indices = [df.index for df in frames.values()]
        combined = all_indices[0]
        for idx in all_indices[1:]:
            combined = combined.union(idx)

        # Apply date range filter
        if self._start:
            combined = combined[combined >= pd.Timestamp(self._start)]
        if self._end:
            combined = combined[combined <= pd.Timestamp(self._end)]

        self._aligned_index = combined.sort_values()

        # Reindex each symbol dataframe and forward-fill gaps
        for symbol, df in frames.items():
            df = df.reindex(self._aligned_index).ffill()
            self._data[symbol] = df

        total_bars = len(self._aligned_index)
        logger.info(
            "CSVDataHandler loaded %d symbols × %d bars (timeframe=%s)",
            len(self._symbols),
            total_bars,
            self._timeframe,
        )

    def _read_csv(self, fpath: str, symbol: str) -> pd.DataFrame:
        df = pd.read_csv(fpath, parse_dates=["timestamp"])
        df = df.rename(columns=str.lower)

        missing = self._REQUIRED_COLS - set(df.columns)
        if missing:
            raise ValueError(
                f"CSV for '{symbol}' is missing columns: {missing}"
            )

        df = df.set_index("timestamp").sort_index()
        df = df[list(self._REQUIRED_COLS)].astype(float)
        return df
