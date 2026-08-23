from __future__ import annotations

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from ..core.models import Market
from ..indicators.technical import calculate_all


FEATURE_COLUMNS = [
    "rsi_14", "macd", "macd_signal", "macd_hist", "ema_distance_9_21", "ema_distance_21_50",
    "atr_pct", "bb_position", "adx_14", "plus_di", "minus_di", "stoch_k", "stoch_d",
    "cci_20", "williams_r", "vwap_distance", "obv_change", "volume_relative", "return_1",
    "historical_volatility", "body_pct", "upper_wick_pct", "lower_wick_pct", "close_position",
    "hour_sin", "hour_cos", "day_sin", "day_cos", "distance_support", "distance_resistance",
    "fib_distance", "trend_code",
    "return_3", "return_12", "ema_50_slope", "atr_regime", "trend_efficiency",
    "macd_acceleration", "rsi_slope", "stoch_spread", "ema21_distance_atr",
    "bollinger_width", "volume_impulse", "candle_rejection", "breakout_20",
    "higher_trend_proxy", "london_new_york_session",
    "ema_9_slope", "ema_21_slope", "pullback_depth_atr", "impulse_strength_atr",
    "swing_position_20", "rsi_divergence_proxy", "macd_divergence_proxy",
    "compression_ratio", "breakout_strength_atr", "liquidity_sweep_code",
    "candle_sequence_4", "reversal_pressure",
    "volume_valid", "taker_buy_ratio", "crypto_market", "forex_market",
    "tokyo_session", "london_session", "new_york_session", "pair_atr_regime",
]

FEATURE_SCHEMA_VERSION = 6


def _session_mask(index: pd.DatetimeIndex, timezone_name: str,
                  opening_hour: int, closing_hour: int) -> pd.Series:
    if index.tz is None:
        localized = index.tz_localize("UTC")
    else:
        localized = index.tz_convert("UTC")
    local = localized.tz_convert(ZoneInfo(timezone_name))
    values = ((local.hour >= opening_hour) & (local.hour < closing_hour)
              & (local.dayofweek < 5)).astype(float)
    return pd.Series(values, index=index)


def build_features(frame: pd.DataFrame, market: str | None = None,
                   symbol: str | None = None) -> pd.DataFrame:
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
    output["return_3"] = data["close"].pct_change(3)
    output["return_12"] = data["close"].pct_change(12)
    output["ema_50_slope"] = data["ema_50"].pct_change(5)
    atr_median = output["atr_pct"].rolling(100, min_periods=30).median().replace(0, np.nan)
    output["atr_regime"] = output["atr_pct"] / atr_median
    path_length = data["close"].pct_change().abs().rolling(12, min_periods=6).sum().replace(0, np.nan)
    output["trend_efficiency"] = data["close"].pct_change(12) / path_length
    output["macd_acceleration"] = data["macd_hist"].diff()
    output["rsi_slope"] = data["rsi_14"].diff(3)
    output["stoch_spread"] = data["stoch_k"] - data["stoch_d"]
    output["ema21_distance_atr"] = (data["close"] - data["ema_21"]) / data["atr_14"].replace(0, np.nan)
    output["bollinger_width"] = (data["bb_upper"] - data["bb_lower"]) / close
    output["volume_impulse"] = data["volume_relative"] * np.sign(data["close"] - data["open"])
    output["candle_rejection"] = (data["lower_wick"] - data["upper_wick"]) / data["atr_14"].replace(0, np.nan)
    previous_high = data["high"].shift(1).rolling(20, min_periods=10).max()
    previous_low = data["low"].shift(1).rolling(20, min_periods=10).min()
    output["breakout_20"] = np.select(
        [data["close"] > previous_high, data["close"] < previous_low],
        [1.0, -1.0], default=0.0,
    )
    output["higher_trend_proxy"] = data["ema_50"].pct_change(10)
    atr_safe = data["atr_14"].replace(0, np.nan)
    output["ema_9_slope"] = data["ema_9"].pct_change(3)
    output["ema_21_slope"] = data["ema_21"].pct_change(3)
    bullish_alignment = data["ema_9"] >= data["ema_21"]
    output["pullback_depth_atr"] = np.where(
        bullish_alignment,
        (data["ema_9"] - data["low"]) / atr_safe,
        (data["high"] - data["ema_9"]) / atr_safe,
    )
    output["impulse_strength_atr"] = (data["close"] - data["open"]) / atr_safe
    range_low = data["low"].shift(1).rolling(20, min_periods=10).min()
    range_high = data["high"].shift(1).rolling(20, min_periods=10).max()
    output["swing_position_20"] = (data["close"] - range_low) / (range_high - range_low).replace(0, np.nan)
    price_change_atr = (data["close"] - data["close"].shift(8)) / atr_safe
    rsi_change = data["rsi_14"] - data["rsi_14"].shift(8)
    macd_change = data["macd_hist"] - data["macd_hist"].shift(8)
    output["rsi_divergence_proxy"] = np.where(
        price_change_atr * rsi_change < 0,
        -np.sign(price_change_atr) * rsi_change.abs() / 100,
        0.0,
    )
    output["macd_divergence_proxy"] = np.where(
        price_change_atr * macd_change < 0,
        -np.sign(price_change_atr) * macd_change.abs() / atr_safe,
        0.0,
    )
    width_median = output["bollinger_width"].rolling(60, min_periods=20).median().replace(0, np.nan)
    output["compression_ratio"] = output["bollinger_width"] / width_median
    output["breakout_strength_atr"] = np.select(
        [data["close"] > previous_high, data["close"] < previous_low],
        [(data["close"] - previous_high) / atr_safe,
         -(previous_low - data["close"]) / atr_safe],
        default=0.0,
    )
    bullish_sweep = (data["low"] < previous_low) & (data["close"] > previous_low)
    bearish_sweep = (data["high"] > previous_high) & (data["close"] < previous_high)
    output["liquidity_sweep_code"] = np.select([bullish_sweep, bearish_sweep], [1.0, -1.0], default=0.0)
    output["candle_sequence_4"] = np.sign(data["close"] - data["open"]).rolling(4, min_periods=2).mean()
    output["reversal_pressure"] = (
        output["rsi_divergence_proxy"].fillna(0) * 2
        + output["macd_divergence_proxy"].fillna(0)
        + output["liquidity_sweep_code"].fillna(0) * 0.25
    )
    output["bb_position"] = (data["close"] - data["bb_lower"]) / (data["bb_upper"] - data["bb_lower"]).replace(0, np.nan)
    output["vwap_distance"] = (data["close"] - data["vwap"]) / close
    output["obv_change"] = data["obv"].pct_change().replace([np.inf, -np.inf], np.nan)
    output["body_pct"] = data["body"] / close
    output["upper_wick_pct"] = data["upper_wick"] / close
    output["lower_wick_pct"] = data["lower_wick"] / close
    crypto_market = market == Market.CRYPTO.value
    forex_market = market == Market.FOREX.value
    valid_volume = data["volume"].fillna(0).gt(0)
    output["volume_valid"] = valid_volume.astype(float) if not forex_market else 0.0
    taker = data.get("taker_buy_volume", pd.Series(0.0, index=data.index)).fillna(0)
    output["taker_buy_ratio"] = np.where(
        valid_volume if not forex_market else False,
        taker / data["volume"].replace(0, np.nan), 0.0,
    )
    output["crypto_market"] = float(crypto_market)
    output["forex_market"] = float(forex_market)
    hours = pd.Series(data.index.hour, index=data.index)
    days = pd.Series(data.index.dayofweek, index=data.index)
    output["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    output["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    output["london_new_york_session"] = ((hours >= 7) & (hours <= 20)).astype(float)
    output["tokyo_session"] = _session_mask(data.index, "Asia/Tokyo", 9, 18)
    output["london_session"] = _session_mask(data.index, "Europe/London", 8, 17)
    output["new_york_session"] = _session_mask(data.index, "America/New_York", 8, 17)
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
    # O regime de ATR é calculado somente sobre o próprio histórico do par/ativo.
    # Assim EUR/USD, GBP/USD e USD/JPY não compartilham uma escala absoluta.
    pair_window = 240 if forex_market else 120
    pair_median = output["atr_pct"].rolling(pair_window, min_periods=30).median().replace(0, np.nan)
    output["pair_atr_regime"] = output["atr_pct"] / pair_median
    if forex_market:
        # Forex não tem volume centralizado. Nenhuma proxy de volume/VWAP entra
        # no modelo como se fosse volume real de bolsa.
        for column in ("vwap_distance", "obv_change", "volume_relative", "volume_impulse", "taker_buy_ratio"):
            output[column] = 0.0
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
