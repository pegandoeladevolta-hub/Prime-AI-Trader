from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators.technical import calculate_all


FEATURE_COLUMNS = [
    "rsi_14", "macd", "macd_signal", "macd_hist", "ema_distance_9_21", "ema_distance_21_50",
    "atr_pct", "bb_position", "adx_14", "plus_di", "minus_di", "stoch_k", "stoch_d",
    "cci_20", "williams_r", "vwap_distance", "obv_change", "volume_relative", "return_1",
    "historical_volatility", "body_pct", "upper_wick_pct", "lower_wick_pct", "close_position",
    "hour_sin", "hour_cos", "day_sin", "day_cos", "distance_support", "distance_resistance",
    "fib_distance", "trend_code",
]

FEATURE_SCHEMA_VERSION = 2


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = calculate_all(frame)
    if data.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS, index=data.index)
    close = data["close"].replace(0, np.nan)
    output = data[[
        "rsi_14", "macd", "macd_signal", "macd_hist", "ema_distance_9_21", "ema_distance_21_50",
        "adx_14", "plus_di", "minus_di", "stoch_k", "stoch_d", "cci_20", "williams_r",
        "volume_relative", "return_1", "historical_volatility", "close_position",
    ]].copy()
    output["atr_pct"] = data["atr_14"] / close
    output["bb_position"] = (data["close"] - data["bb_lower"]) / (data["bb_upper"] - data["bb_lower"]).replace(0, np.nan)
    output["vwap_distance"] = (data["close"] - data["vwap"]) / close
    output["obv_change"] = data["obv"].pct_change().replace([np.inf, -np.inf], np.nan)
    output["body_pct"] = data["body"] / close
    output["upper_wick_pct"] = data["upper_wick"] / close
    output["lower_wick_pct"] = data["lower_wick"] / close
    hours = pd.Series(data.index.hour, index=data.index)
    days = pd.Series(data.index.dayofweek, index=data.index)
    output["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    output["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    output["day_sin"] = np.sin(2 * np.pi * days / 7)
    output["day_cos"] = np.cos(2 * np.pi * days / 7)
    # Proxies causais e vetorizadas. A implementação antiga executava análise
    # estrutural e Fibonacci 500 vezes por atualização, monopolizando a CPU.
    # Estas séries preservam apenas dados presentes/passados e ficam dezenas de
    # vezes mais rápidas sem introduzir look-ahead no treino ou backtest.
    rolling_low = data["low"].rolling(120, min_periods=9).min()
    rolling_high = data["high"].rolling(120, min_periods=9).max()
    swing = (rolling_high - rolling_low).replace(0, np.nan)
    output["distance_support"] = (data["close"] - rolling_low) / close
    output["distance_resistance"] = (rolling_high - data["close"]) / close
    fib_distances = []
    for ratio in (0.236, 0.382, 0.5, 0.618, 0.786):
        level = rolling_low + swing * ratio
        fib_distances.append((data["close"] - level).abs() / close)
    output["fib_distance"] = pd.concat(fib_distances, axis=1).min(axis=1)
    aligned_up = (data["ema_9"] > data["ema_21"]) & (data["ema_21"] > data["ema_50"])
    aligned_down = (data["ema_9"] < data["ema_21"]) & (data["ema_21"] < data["ema_50"])
    output["trend_code"] = np.select([aligned_up, aligned_down], [1.0, -1.0], default=0.0)
    return output.reindex(columns=FEATURE_COLUMNS).replace([np.inf, -np.inf], np.nan)


def build_labels(close: pd.Series, horizon_candles: int, threshold: float) -> pd.Series:
    future_return = close.shift(-horizon_candles) / close - 1
    labels = pd.Series(np.where(future_return > threshold, 1, np.where(future_return < -threshold, -1, 0)), index=close.index, dtype="float")
    labels.iloc[-horizon_candles:] = np.nan
    return labels


def build_time_labels(feature_index: pd.DatetimeIndex, base_close: pd.Series,
                      horizon_minutes: int, threshold: float) -> pd.Series:
    """Cria labels no horizonte exato usando o primeiro preço-base no/além do alvo temporal."""
    if base_close.empty:
        return pd.Series(np.nan, index=feature_index, dtype="float")
    base = base_close.sort_index()
    base_times = base.index.view("int64")
    values = base.to_numpy(dtype=float)
    result = []
    for when in feature_index:
        current_pos = int(np.searchsorted(base_times, when.value, side="left"))
        target_value = (when + pd.Timedelta(minutes=horizon_minutes)).value
        future_pos = int(np.searchsorted(base_times, target_value, side="left"))
        if current_pos >= len(values) or future_pos >= len(values):
            result.append(np.nan)
            continue
        change = values[future_pos] / values[current_pos] - 1
        result.append(1.0 if change > threshold else -1.0 if change < -threshold else 0.0)
    return pd.Series(result, index=feature_index, dtype="float")
