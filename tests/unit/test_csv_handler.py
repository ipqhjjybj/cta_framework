"""Unit tests for data/csv_handler.py"""
import os
import pytest
import pandas as pd
from datetime import datetime

from data.csv_handler import CSVDataHandler, _symbol_to_filename
from core.events import MarketEvent

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


class TestSymbolToFilename:
    def test_slash_replaced(self):
        assert _symbol_to_filename("BTC/USDT", "1h") == "BTC_USDT_1h.csv"

    def test_no_slash(self):
        assert _symbol_to_filename("BTCUSDT", "4h") == "BTCUSDT_4h.csv"


class TestCSVDataHandler:
    @pytest.fixture
    def handler(self):
        return CSVDataHandler(
            csv_dir=FIXTURES_DIR,
            symbols=["BTC/USDT"],
            timeframe="1h",
            start=datetime(2023, 1, 1),
            end=datetime(2023, 1, 31, 23, 0, 0),
        )

    def test_symbols(self, handler):
        assert handler.symbols == ["BTC/USDT"]

    def test_start_end(self, handler):
        assert handler.start == datetime(2023, 1, 1, 0, 0, 0)
        assert handler.end == datetime(2023, 1, 31, 23, 0, 0)

    def test_iter_bars_yields_market_events(self, handler):
        bars = list(handler.iter_bars())
        assert len(bars) > 0
        first = bars[0]
        assert isinstance(first, list)
        assert len(first) == 1
        event = first[0]
        assert isinstance(event, MarketEvent)
        assert event.symbol == "BTC/USDT"

    def test_bar_count(self, handler):
        # Jan 2023 has 31 days × 24 hours = 744 bars
        bars = list(handler.iter_bars())
        assert len(bars) == 31 * 24

    def test_ohlcv_values(self, handler):
        first_bar = list(handler.iter_bars())[0][0]
        assert first_bar.open > 0
        assert first_bar.high >= first_bar.low
        assert first_bar.volume >= 0

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            CSVDataHandler(
                csv_dir=FIXTURES_DIR,
                symbols=["XYZ/USDT"],
                timeframe="1h",
            )
