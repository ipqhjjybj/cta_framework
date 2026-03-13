"""
Standalone CLI tool for pre-downloading OHLCV data from exchanges.

Usage:
    python -m data.data_fetcher \\
        --exchange binance \\
        --symbol BTC/USDT \\
        --timeframe 1h \\
        --start 2023-01-01 \\
        --end 2023-12-31 \\
        --output data/raw/BTC_USDT_1h.csv

Proxy (any of these work):
    # Via CLI flag:
    --proxy http://10.11.12.20:8889

    # Via environment variables (auto-detected):
    export https_proxy=http://10.11.12.20:8889
    export http_proxy=http://10.11.12.20:8889
    export all_proxy=socks5://10.11.12.20:8889
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime

import pandas as pd


def fetch_and_save(
    exchange_id: str,
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    output: str,
    use_cache: bool = True,
    cache_dir: str = ".cache/parquet",
    proxy: str | None = None,
) -> None:
    from data.ccxt_handler import CCXTDataHandler

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)

    handler = CCXTDataHandler(
        exchange_id=exchange_id,
        symbols=[symbol],
        timeframe=timeframe,
        start=start_dt,
        end=end_dt,
        use_cache=use_cache,
        cache_dir=cache_dir,
        proxy=proxy,
    )

    df = handler._data[symbol].copy()
    df.index.name = "timestamp"
    df.to_csv(output)
    print(f"Saved {len(df)} bars to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-download OHLCV data from exchanges",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Proxy examples:
  --proxy http://127.0.0.1:8889
  export https_proxy=http://10.11.12.20:8889  (auto-detected from env)
        """,
    )
    parser.add_argument("--exchange", required=True, help="CCXT exchange id (e.g. binance)")
    parser.add_argument("--symbol", required=True, help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", default="1h", help="Bar interval (default: 1h)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    parser.add_argument("--no-cache", action="store_true", help="Disable Parquet caching")
    parser.add_argument("--cache-dir", default=".cache/parquet", help="Cache directory")
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy URL, e.g. http://10.11.12.20:8889  "
             "(overrides env vars; env vars https_proxy/http_proxy/all_proxy also work)",
    )

    args = parser.parse_args()
    fetch_and_save(
        exchange_id=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        output=args.output,
        use_cache=not args.no_cache,
        cache_dir=args.cache_dir,
        proxy=args.proxy,
    )


if __name__ == "__main__":
    main()
