"""
CCXT-based DataHandler for fetching historical OHLCV data from exchanges.

Features:
  - Automatic pagination for large date ranges
  - Parquet caching to avoid redundant API calls
  - Configurable exchange and timeframe
  - Proxy support via explicit config or environment variables
    (http_proxy / https_proxy / all_proxy)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

import pandas as pd

from core.data_handler import DataHandler
from core.events import MarketEvent
from data.cache import ParquetCache
from utils.logger import get_logger
from utils.timeframe import TIMEFRAME_TO_SECONDS

logger = get_logger(__name__)

_MS_PER_SECOND = 1000


def _build_proxies(proxy: Optional[str] = None) -> Optional[dict]:
    """
    Build a requests-style proxy dict.

    Priority:
      1. Explicit `proxy` argument (applied to both http and https).
      2. Environment variables: https_proxy / http_proxy / all_proxy.
      3. None (no proxy).
    """
    if proxy:
        return {"http": proxy, "https": proxy}

    https = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    http  = os.environ.get("http_proxy")  or os.environ.get("HTTP_PROXY")
    socks = os.environ.get("all_proxy")   or os.environ.get("ALL_PROXY")

    result: dict = {}
    if https:
        result["https"] = https
    if http:
        result["http"] = http
    # all_proxy / socks5 fallback for both protocols
    if socks and not result:
        result = {"http": socks, "https": socks}

    return result if result else None


class CCXTDataHandler(DataHandler):
    """
    Fetch historical OHLCV bars from any CCXT-supported exchange.

    Requires:  pip install ccxt

    Args:
        exchange_id:     CCXT exchange id (e.g. 'binance', 'bybit').
        symbols:         List of trading pairs (e.g. ['BTC/USDT']).
        timeframe:       Bar interval string (e.g. '1h').
        start:           UTC start datetime.
        end:             UTC end datetime.
        use_cache:       Cache fetched data as Parquet (default True).
        cache_dir:       Directory for Parquet cache files.
        proxy:           Explicit proxy URL, e.g. 'http://127.0.0.1:8889'.
                         Falls back to http_proxy / https_proxy env vars.
        exchange_kwargs: Extra kwargs forwarded to ccxt exchange constructor.
    """

    def __init__(
        self,
        exchange_id: str,
        symbols: List[str],
        timeframe: str,
        start: datetime,
        end: datetime,
        use_cache: bool = True,
        cache_dir: str = ".cache/parquet",
        proxy: Optional[str] = None,
        exchange_kwargs: Optional[dict] = None,
    ) -> None:
        try:
            import ccxt
        except ImportError:
            raise ImportError("ccxt is required: pip install ccxt")

        self._symbols = sorted(symbols)
        self._timeframe = timeframe
        self._start = start
        self._end = end
        self._cache = ParquetCache(cache_dir) if use_cache else None

        proxies = _build_proxies(proxy)
        kwargs: dict = dict(exchange_kwargs or {})
        if proxies:
            kwargs["proxies"] = proxies
            logger.info("Using proxy: %s", proxies)

        exchange_cls = getattr(ccxt, exchange_id)
        self._exchange = exchange_cls(kwargs)

        self._data: Dict[str, pd.DataFrame] = {}
        self._aligned_index: pd.DatetimeIndex = pd.DatetimeIndex([])
        self._fetch_all()

    # ------------------------------------------------------------------
    # DataHandler interface
    # ------------------------------------------------------------------

    @property
    def symbols(self) -> List[str]:
        return list(self._symbols)

    @property
    def start(self) -> datetime:
        return self._aligned_index[0].to_pydatetime()

    @property
    def end(self) -> datetime:
        return self._aligned_index[-1].to_pydatetime()

    def iter_bars(self) -> Iterator[List[MarketEvent]]:
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

    def _fetch_all(self) -> None:
        all_indices = []
        for symbol in self._symbols:
            df = self._get_or_fetch(symbol)
            self._data[symbol] = df
            all_indices.append(df.index)

        combined = all_indices[0]
        for idx in all_indices[1:]:
            combined = combined.union(idx)
        self._aligned_index = combined.sort_values()

        for symbol in self._symbols:
            self._data[symbol] = (
                self._data[symbol].reindex(self._aligned_index).ffill()
            )

    def _get_or_fetch(self, symbol: str) -> pd.DataFrame:
        if self._cache:
            cached = self._cache.get(symbol, self._timeframe, self._start, self._end)
            if cached is not None:
                logger.info("Cache hit for %s %s", symbol, self._timeframe)
                return cached

        df = self._fetch_paginated(symbol)

        if self._cache:
            self._cache.set(symbol, self._timeframe, self._start, self._end, df)

        return df

    def _fetch_paginated(self, symbol: str) -> pd.DataFrame:
        """Fetch all bars for a symbol by paginating through the API."""
        bar_ms = TIMEFRAME_TO_SECONDS[self._timeframe] * _MS_PER_SECOND
        since_ms = int(self._start.replace(tzinfo=timezone.utc).timestamp() * _MS_PER_SECOND)
        until_ms = int(self._end.replace(tzinfo=timezone.utc).timestamp() * _MS_PER_SECOND)

        all_rows = []
        batch_limit = 1000

        while since_ms < until_ms:
            logger.debug("Fetching %s from %s", symbol, pd.Timestamp(since_ms, unit="ms"))
            ohlcv = self._exchange.fetch_ohlcv(
                symbol, self._timeframe, since=since_ms, limit=batch_limit
            )
            if not ohlcv:
                break
            all_rows.extend(ohlcv)
            since_ms = ohlcv[-1][0] + bar_ms
            if len(ohlcv) < batch_limit:
                break

        if not all_rows:
            raise ValueError(f"No data returned for {symbol}")

        df = pd.DataFrame(
            all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["timestamp"] = df["timestamp"].dt.tz_localize(None)
        df = df.set_index("timestamp").sort_index()

        # Trim to requested range
        df = df[df.index >= pd.Timestamp(self._start)]
        df = df[df.index <= pd.Timestamp(self._end)]

        logger.info("Fetched %d bars for %s %s", len(df), symbol, self._timeframe)
        return df
