"""
Abstract DataHandler base class.

A DataHandler is responsible for:
  1. Loading and aligning OHLCV bars for one or more symbols.
  2. Yielding one timestamp's worth of MarketEvents per iteration.

Concrete subclasses: CSVDataHandler, CCXTDataHandler.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator, List

from core.events import MarketEvent


class DataHandler(ABC):
    """
    Abstract interface for market data sources.

    Subclasses must implement `iter_bars`, which yields lists of
    MarketEvent objects — one per symbol — for each aligned timestamp.
    """

    @abstractmethod
    def iter_bars(self) -> Iterator[List[MarketEvent]]:
        """
        Yield a list of MarketEvents for each bar timestamp.

        Each yielded list contains one MarketEvent per active symbol
        for the same timestamp, sorted by symbol name for determinism.

        Yields:
            List[MarketEvent]: All symbol bars for a single timestamp.
        """
        ...

    @property
    @abstractmethod
    def symbols(self) -> List[str]:
        """Return the list of symbols this handler provides data for."""
        ...

    @property
    @abstractmethod
    def start(self) -> datetime:
        """Return the first timestamp in the dataset."""
        ...

    @property
    @abstractmethod
    def end(self) -> datetime:
        """Return the last timestamp in the dataset."""
        ...
