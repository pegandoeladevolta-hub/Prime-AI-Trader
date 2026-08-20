from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.models import Candle


def candles_frame(candles: list[Candle]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume"])
    return pd.DataFrame({
        "time": [c.open_time for c in candles], "open": [c.open for c in candles],
        "high": [c.high for c in candles], "low": [c.low for c in candles],
        "close": [c.close for c in candles], "volume": [c.volume for c in candles],
        "quote_volume": [c.quote_volume for c in candles],
        "taker_buy_volume": [c.taker_buy_volume for c in candles],
    }).set_index("time")


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    return result.mask((avg_loss == 0) & (avg_gain == 0), 50.0)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(series, fast) - ema(series, slow)
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, signal_line, line - signal_line


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous = frame["close"].shift(1)
    return pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - previous).abs(),
        (frame["low"] - previous).abs(),
    ], axis=1).max(axis=1)


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(frame).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def bollinger(series: pd.Series, period: int = 20, deviations: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    return middle, middle + deviations * std, middle - deviations * std


def stochastic(frame: pd.DataFrame, period: int = 14, smooth: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest = frame["low"].rolling(period).min()
    highest = frame["high"].rolling(period).max()
    k = 100 * (frame["close"] - lowest) / (highest - lowest).replace(0, np.nan)
    return k, k.rolling(smooth).mean()


def adx(frame: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = frame["high"].diff()
    down = -frame["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=frame.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=frame.index)
    atr_values = atr(frame, period)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_values.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_values.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean(), plus_di, minus_di


def cci(frame: pd.DataFrame, period: int = 20) -> pd.Series:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3
    average = typical.rolling(period).mean()
    deviation = typical.rolling(period).apply(lambda values: np.mean(np.abs(values - np.mean(values))), raw=True)
    return (typical - average) / (0.015 * deviation.replace(0, np.nan))


def williams_r(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    highest = frame["high"].rolling(period).max()
    lowest = frame["low"].rolling(period).min()
    return -100 * (highest - frame["close"]) / (highest - lowest).replace(0, np.nan)


def obv(frame: pd.DataFrame) -> pd.Series:
    direction = np.sign(frame["close"].diff()).fillna(0)
    return (direction * frame["volume"]).cumsum()


def vwap(frame: pd.DataFrame) -> pd.Series:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3
    cumulative_volume = frame["volume"].cumsum()
    return (typical * frame["volume"]).cumsum() / cumulative_volume.replace(0, np.nan)


def calculate_all(frame: pd.DataFrame, periods_per_year: int = 365 * 24 * 12) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    for period in (9, 21, 50):
        result[f"ema_{period}"] = ema(result["close"], period)
    result["rsi_14"] = rsi(result["close"], 14)
    result["macd"], result["macd_signal"], result["macd_hist"] = macd(result["close"])
    result["atr_14"] = atr(result, 14)
    result["bb_middle"], result["bb_upper"], result["bb_lower"] = bollinger(result["close"])
    result["stoch_k"], result["stoch_d"] = stochastic(result)
    result["adx_14"], result["plus_di"], result["minus_di"] = adx(result)
    result["cci_20"] = cci(result)
    result["williams_r"] = williams_r(result)
    result["obv"] = obv(result)
    result["vwap"] = vwap(result)
    result["volume_mean_20"] = result["volume"].rolling(20).mean()
    result["volume_relative"] = result["volume"] / result["volume_mean_20"].replace(0, np.nan)
    result["amplitude_mean_14"] = (result["high"] - result["low"]).rolling(14).mean()
    returns = np.log(result["close"] / result["close"].shift(1))
    result["historical_volatility"] = returns.rolling(30).std(ddof=0) * np.sqrt(periods_per_year)
    result["return_1"] = result["close"].pct_change()
    result["body"] = (result["close"] - result["open"]).abs()
    result["upper_wick"] = result["high"] - result[["open", "close"]].max(axis=1)
    result["lower_wick"] = result[["open", "close"]].min(axis=1) - result["low"]
    span = (result["high"] - result["low"]).replace(0, np.nan)
    result["close_position"] = (result["close"] - result["low"]) / span
    result["ema_distance_9_21"] = (result["ema_9"] - result["ema_21"]) / result["close"]
    result["ema_distance_21_50"] = (result["ema_21"] - result["ema_50"]) / result["close"]
    return result.replace([np.inf, -np.inf], np.nan)

