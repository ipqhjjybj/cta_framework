"""
Turtle Trading System — a classic trend-following strategy.

Original rules (Richard Dennis, 1983), adapted for crypto:

  Entry:
    LONG  when close breaks above the highest high of the last `entry_period` bars
    SHORT when close breaks below the lowest low  of the last `entry_period` bars

  Trend filter (optional but recommended):
    Only go LONG  when close > SMA(trend_period)
    Only go SHORT when close < SMA(trend_period)

  Exit:
    Close LONG  when close < lowest low   of the last `exit_period` bars
    Close SHORT when close > highest high of the last `exit_period` bars

  Hard ATR stop:
    LONG  stops out if close falls more than `atr_stop_mult * ATR` below entry
    SHORT stops out if close rises more than `atr_stop_mult * ATR` above entry

Historical context:
  - The original Turtle System returned ~80% CAGR during 1983–1988 on commodities.
  - Crypto (BTC) exhibits strong trending behaviour, making trend-following rational.

IMPORTANT: Past performance does not guarantee future results.
           Always validate on out-of-sample real data before trading live.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from core.event_queue import EventQueue
from core.events import FillEvent, MarketEvent, OrderSide, SignalDirection, SignalEvent
from core.strategy import Strategy


def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _atr(bars: list, period: int) -> Optional[float]:
    """Average True Range over the last `period` bars."""
    if len(bars) < period + 1:
        return None
    true_ranges = []
    for i in range(-period, 0):
        bar  = bars[i]
        prev = bars[i - 1]
        tr = max(
            bar.high - bar.low,
            abs(bar.high - prev.close),
            abs(bar.low  - prev.close),
        )
        true_ranges.append(tr)
    return sum(true_ranges) / period


def _adx(bars: list, period: int) -> Optional[float]:
    """
    Directional strength indicator (ADX proxy, O(period) stateless version).

    Computes +DI and -DI over the last `period` bars using simple sums,
    then returns DX = 100 * |+DI - -DI| / (+DI + -DI).
    Values > 25 indicate a trending market; < 20 indicate ranging/choppy.
    """
    if len(bars) < period + 1:
        return None
    pdm_sum = mdm_sum = tr_sum = 0.0
    for i in range(-period, 0):
        bar  = bars[i]
        prev = bars[i - 1]
        up   = bar.high - prev.high
        down = prev.low  - bar.low
        pdm_sum += up   if (up   > down and up   > 0) else 0.0
        mdm_sum += down if (down > up   and down > 0) else 0.0
        tr_sum  += max(
            bar.high - bar.low,
            abs(bar.high - prev.close),
            abs(bar.low  - prev.close),
        )
    if tr_sum == 0:
        return None
    pdi   = 100.0 * pdm_sum / tr_sum
    mdi   = 100.0 * mdm_sum / tr_sum
    denom = pdi + mdi
    if denom == 0:
        return None
    return 100.0 * abs(pdi - mdi) / denom


class TurtleStrategy(Strategy):
    """
    Turtle Trading System.

    Parameters
    ----------
    entry_period  : Breakout look-back for entries (default 20 bars).
    exit_period   : Breakout look-back for exits   (default 10 bars).
    atr_period    : ATR period for hard-stop calc  (default 14).
    atr_stop_mult : Hard stop = atr_stop_mult × ATR (default 2.0).
    trend_period  : SMA period for trend filter    (default 200; 0 = disable).
    adx_period    : ADX look-back for trend-strength filter (default 0 = disable).
                    Typical: 14 (on daily bars) or 336 (14 days on 1h bars).
    adx_min       : Minimum ADX to allow new entries (default 20).
                    Entry signals are blocked when ADX < adx_min (ranging/choppy market).
                    Exits and hard stops are still executed regardless of ADX.
    allow_short   : Enable short trades            (default True).
    strategy_id   : Identifier string on every signal.
    """

    def __init__(
        self,
        symbols: List[str],
        event_queue: EventQueue,
        entry_period: int = 20,
        exit_period: int = 10,
        atr_period: int = 14,
        atr_stop_mult: float = 2.0,
        trend_period: int = 200,
        adx_period: int = 0,
        adx_min: float = 20.0,
        allow_short: bool = True,
        strategy_id: str = "turtle",
    ) -> None:
        if exit_period >= entry_period:
            raise ValueError("exit_period must be < entry_period")
        super().__init__(symbols, event_queue)
        self._entry        = entry_period
        self._exit         = exit_period
        self._atr_period   = atr_period
        self._atr_mult     = atr_stop_mult
        self._trend        = trend_period
        self._adx_period   = adx_period
        self._adx_min      = adx_min
        self._allow_short  = allow_short
        self._strategy_id  = strategy_id

        # Per-symbol runtime state
        self._position:    Dict[str, Optional[str]]   = {}
        self._stop_price:  Dict[str, Optional[float]] = {}
        self._last_atr:    Dict[str, Optional[float]] = {}

    @property
    def warmup_period(self) -> int:
        return max(
            self._entry,
            self._trend if self._trend else 0,
            self._atr_period + 1,
            self._adx_period + 1 if self._adx_period else 0,
        )

    # ------------------------------------------------------------------
    # FillEvent callback — keep stop price in sync with actual fill
    # ------------------------------------------------------------------

    def on_fill(self, event: FillEvent) -> None:
        symbol = event.symbol
        atr    = self._last_atr.get(symbol)

        if event.side == OrderSide.BUY:
            if self._position.get(symbol) == "SHORT":
                # Covering short → flat
                self._position[symbol]   = None
                self._stop_price[symbol] = None
            else:
                # Opening long
                self._position[symbol]   = "LONG"
                self._stop_price[symbol] = (
                    event.fill_price - self._atr_mult * atr if atr else None
                )
        else:  # SELL
            if self._position.get(symbol) == "LONG":
                # Closing long → flat
                self._position[symbol]   = None
                self._stop_price[symbol] = None
            else:
                # Opening short
                self._position[symbol]   = "SHORT"
                self._stop_price[symbol] = (
                    event.fill_price + self._atr_mult * atr if atr else None
                )

    # ------------------------------------------------------------------
    # Signal calculation — called each bar after warmup
    # ------------------------------------------------------------------

    def calculate_signals(self, event: MarketEvent) -> List[SignalEvent]:
        symbol = event.symbol
        bars   = list(self.bars(symbol))
        closes = [b.close for b in bars]
        close  = event.close

        # Update ATR cache every bar
        atr = _atr(bars, self._atr_period)
        self._last_atr[symbol] = atr

        # Trend filter
        if self._trend:
            sma        = _sma(closes, self._trend)
            trend_up   = sma is not None and close > sma
            trend_down = sma is not None and close < sma
        else:
            trend_up = trend_down = True

        # Need enough history for entry channel
        if len(bars) < self._entry + 1:
            return []

        # Entry channel: N-bar high/low excluding the current bar
        entry_highs  = [b.high for b in bars[-(self._entry + 1):-1]]
        entry_lows   = [b.low  for b in bars[-(self._entry + 1):-1]]
        channel_high = max(entry_highs)
        channel_low  = min(entry_lows)

        # Exit channel: narrower
        if len(bars) < self._exit + 1:
            return []
        exit_highs = [b.high for b in bars[-(self._exit + 1):-1]]
        exit_lows  = [b.low  for b in bars[-(self._exit + 1):-1]]
        exit_high  = max(exit_highs)
        exit_low   = min(exit_lows)

        current_pos = self._position.get(symbol)
        hard_stop   = self._stop_price.get(symbol)
        signals: List[SignalEvent] = []

        # ---- 1. Hard ATR stop (highest priority, always executes) ----
        if current_pos == "LONG" and hard_stop is not None and close < hard_stop:
            signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            self._position[symbol] = None
            return signals

        if current_pos == "SHORT" and hard_stop is not None and close > hard_stop:
            signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            self._position[symbol] = None
            return signals

        # ---- 2. Channel exits (always execute regardless of ADX) ----
        if current_pos == "LONG" and close < exit_low:
            signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            self._position[symbol] = None
            return signals

        if current_pos == "SHORT" and close > exit_high:
            signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            self._position[symbol] = None
            return signals

        # ---- 3. ADX trend-strength filter (gates new entries only) ----
        # ADX < adx_min means the market is ranging/choppy → skip new breakout entries
        if self._adx_period and current_pos is None:
            adx_val = _adx(bars, self._adx_period)
            if adx_val is not None and adx_val < self._adx_min:
                return []

        # ---- 4. Entry breakouts ----
        if close > channel_high and current_pos != "LONG" and trend_up:
            if current_pos == "SHORT":
                signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            signals.append(self._sig(symbol, event, SignalDirection.LONG, atr))
            self._position[symbol] = "LONG"

        elif (
            close < channel_low
            and current_pos != "SHORT"
            and trend_down
            and self._allow_short
        ):
            if current_pos == "LONG":
                signals.append(self._sig(symbol, event, SignalDirection.EXIT))
            signals.append(self._sig(symbol, event, SignalDirection.SHORT, atr))
            self._position[symbol] = "SHORT"

        return signals

    def _sig(
        self,
        symbol: str,
        event: MarketEvent,
        direction: str,
        atr: float | None = None,
    ) -> SignalEvent:
        # Encode ATR-based stop distance as strength = stop_distance / price
        # Portfolio decodes this to compute quantity = risk_$ / stop_distance_$
        if atr is not None and event.close > 0:
            stop_dist_ratio = min((self._atr_mult * atr) / event.close, 0.99)
        else:
            stop_dist_ratio = 1.0  # fallback: flat notional sizing

        return SignalEvent(
            symbol=symbol,
            timestamp=event.timestamp,
            direction=direction,
            strength=stop_dist_ratio,
            strategy_id=self._strategy_id,
        )
