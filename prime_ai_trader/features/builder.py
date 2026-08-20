from __future__ import annotations

import numpy as np
import pandas as pd

from ..fibonacci.auto import automatic_fibonacci
from ..indicators.technical import calculate_all
from ..priceaction.structure import analyze_structure


FEATURE_COLUMNS = [
    "rsi_14", "macd", "macd_signal", "macd_hist", "ema_distance_9_21", "ema_distance_21_50",
    "atr_pct", "bb_position", "adx_14", "plus_di", "minus_di", "stoch_k", "stoch_d",
    "cci_20", "williams_r", "vwap_distance", "obv_change", "volume_relative", "return_1",
    "historical_volatility", "body_pct", "upper_wick_pct", "lower_wick_pct", "close_position",
    "hour_sin", "hour_cos", "day_sin", "day_cos", "distance_support", "distance_resistance",
    "fib_distance", "trend_code",
]


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
    support_distance, resistance_distance, fib_distance, trend_codes = [], [], [], []
    for end in range(len(data)):
        window = data.iloc[max(0, end - 120):end + 1]
        atr_value = float(data["atr_14"].iloc[end]) if pd.notna(data["atr_14"].iloc[end]) else None
        structure = analyze_structure(window, atr_value)
        current = float(data["close"].iloc[end])
        support_distance.append((current - structure.support_zones[0].midpoint) / current if structure.support_zones else np.nan)
        resistance_distance.append((structure.resistance_zones[0].midpoint - current) / current if structure.resistance_zones else np.nan)
        fib = automatic_fibonacci(window)
        fib_distance.append(fib.distance_pct / 100 if fib else np.nan)
        trend_codes.append({"BAIXA": -1.0, "LATERAL": 0.0, "ALTA": 1.0}.get(structure.trend, 0.0))
    output["distance_support"] = support_distance
    output["distance_resistance"] = resistance_distance
    output["fib_distance"] = fib_distance
    output["trend_code"] = trend_codes
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
