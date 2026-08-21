from __future__ import annotations

import inspect
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from prime_ai_trader.backtest.engine import _directional_confluence
from prime_ai_trader.core.models import Candle, Direction, Market, TIMEFRAMES, Zone
from prime_ai_trader.features.builder import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.platform.vex import VexPlatformSnapshot, merge_vex_quote
from prime_ai_trader.priceaction.professional import (
    PullbackSignal, assess_professional_market, detect_market_regime,
    detect_momentum_divergences, detect_pullback, detect_structure_event,
    live_refresh_interval, timeframe_policy,
)
from prime_ai_trader.priceaction.structure import MarketStructure, analyze_structure
from prime_ai_trader.signals.engine import SignalEngine
from prime_ai_trader.ui.dashboard import PrimeAITraderApp
from tests.helpers import synthetic_candles


def _indicators(seed: int = 42, count: int = 100) -> pd.DataFrame:
    return calculate_all(candles_frame(synthetic_candles(count, seed=seed)))


def _structure(trend: str = "LATERAL", *, highs: list[int] | None = None,
               lows: list[int] | None = None, supports: list[Zone] | None = None,
               resistances: list[Zone] | None = None) -> MarketStructure:
    return MarketStructure(trend, [], None, False, False, supports or [],
                           resistances or [], highs or [], lows or [])


def _event_frame(direction: Direction, trend: str) -> tuple[pd.DataFrame, MarketStructure]:
    indicators = _indicators()
    last, previous = indicators.index[-1], indicators.index[-2]
    indicators.loc[last, "atr_14"] = 1.0
    if direction == Direction.BUY:
        pivot = len(indicators) - 7
        indicators.loc[indicators.index[pivot], "high"] = 100.0
        indicators.loc[previous, "close"] = 99.9
        indicators.loc[last, ["open", "high", "low", "close", "close_position"]] = (
            99.9, 100.6, 99.8, 100.45, 0.85,
        )
        return indicators, _structure(trend, highs=[pivot])
    pivot = len(indicators) - 7
    indicators.loc[indicators.index[pivot], "low"] = 98.0
    indicators.loc[previous, "close"] = 98.1
    indicators.loc[last, ["open", "high", "low", "close", "close_position"]] = (
        98.1, 98.2, 97.45, 97.55, 0.15,
    )
    return indicators, _structure(trend, lows=[pivot])


def _pullback_frame(direction: Direction) -> tuple[pd.DataFrame, MarketStructure]:
    closes = np.r_[np.linspace(92.0, 110.0, 70), [109.2, 108.8, 108.4, 108.0, 107.6, 107.3, 108.5]]
    if direction == Direction.SELL:
        closes = 200.0 - closes
    opens = np.r_[closes[0] - (0.1 if direction == Direction.BUY else -0.1), closes[:-1]]
    high = np.maximum(opens, closes) + 0.28
    low = np.minimum(opens, closes) - 0.28
    index = pd.date_range("2025-01-01", periods=len(closes), freq="5min", tz="UTC")
    frame = pd.DataFrame({"open": opens, "high": high, "low": low, "close": closes,
                          "volume": np.full(len(closes), 400.0),
                          "quote_volume": np.full(len(closes), 40_000.0),
                          "taker_buy_volume": np.full(len(closes), 210.0)}, index=index)
    indicators = calculate_all(frame)
    trend = "ALTA" if direction == Direction.BUY else "BAIXA"
    return indicators, _structure(trend)


def _snapshot(**changes) -> VexPlatformSnapshot:
    values = {"observed_at": datetime.now(timezone.utc),
              "url": "https://vexinvest.com/traderoom", "authenticated": True,
              "asset": "BTC/USDT", "market": Market.CRYPTO.value,
              "payout_percent": 82, "remaining_seconds": 43,
              "horizon_minutes": 1, "price": 101.5, "otc": False}
    values.update(changes)
    return VexPlatformSnapshot(**values)


class ProfessionalTimeframeTests(unittest.TestCase):
    def test_all_supported_timeframes_have_explicit_policy(self) -> None:
        for timeframe in TIMEFRAMES:
            with self.subTest(timeframe=timeframe):
                policy = timeframe_policy(timeframe)
                self.assertEqual(policy.timeframe, timeframe)
                self.assertGreater(policy.structure_bars, policy.pullback_bars)

    def test_longer_timeframes_require_larger_structural_context(self) -> None:
        short = timeframe_policy("1m")
        long = timeframe_policy("4h")
        self.assertLess(short.structure_bars, long.structure_bars)
        self.assertLess(short.minimum_displacement_atr, long.minimum_displacement_atr)

    def test_timeframe_is_inferred_without_assuming_one_minute(self) -> None:
        self.assertEqual(timeframe_policy(None, _indicators()).timeframe, "5m")

    def test_unknown_timeframe_has_safe_default(self) -> None:
        self.assertEqual(timeframe_policy("99d").timeframe, "5m")

    def test_fast_refreshes_more_often_than_conservative(self) -> None:
        for timeframe in TIMEFRAMES:
            with self.subTest(timeframe=timeframe):
                self.assertLess(live_refresh_interval(timeframe, "RÁPIDO"),
                                live_refresh_interval(timeframe, "CONSERVADOR"))

    def test_refresh_is_bounded_and_does_not_spin_the_interface(self) -> None:
        for timeframe in TIMEFRAMES:
            for sensitivity in ("RÁPIDO", "EQUILIBRADO", "CONSERVADOR"):
                with self.subTest(timeframe=timeframe, sensitivity=sensitivity):
                    self.assertGreaterEqual(live_refresh_interval(timeframe, sensitivity), 3)
                    self.assertLessEqual(live_refresh_interval(timeframe, sensitivity), 30)


class MarketRegimeTests(unittest.TestCase):
    def test_short_history_is_not_presented_as_confirmed_trend(self) -> None:
        regime = detect_market_regime(_indicators().iloc[:12])
        self.assertEqual(regime.direction, Direction.WAIT)
        self.assertIn("FORMAÇÃO", regime.name)

    def test_aligned_bullish_market_is_identified(self) -> None:
        data = _indicators()
        index = data.index[-1]
        data.loc[index, ["close", "ema_9", "ema_21", "ema_50", "adx_14", "rsi_14"]] = (
            105.0, 104.0, 103.0, 101.0, 27.0, 61.0,
        )
        regime = detect_market_regime(data)
        self.assertEqual(regime.direction, Direction.BUY)
        self.assertIn("ALTA", regime.name)

    def test_aligned_bearish_market_is_identified(self) -> None:
        data = _indicators()
        index = data.index[-1]
        data.loc[index, ["close", "ema_9", "ema_21", "ema_50", "adx_14", "rsi_14"]] = (
            95.0, 96.0, 97.0, 99.0, 27.0, 42.0,
        )
        regime = detect_market_regime(data)
        self.assertEqual(regime.direction, Direction.SELL)
        self.assertIn("BAIXA", regime.name)

    def test_transition_is_not_confused_with_established_trend(self) -> None:
        data = _indicators()
        index = data.index[-1]
        data.loc[index, ["close", "ema_9", "ema_21", "ema_50", "atr_14", "adx_14"]] = (
            100.0, 100.1, 100.0, 101.0, 1.0, 23.0,
        )
        regime = detect_market_regime(data)
        self.assertTrue(regime.transition)
        self.assertEqual(regime.direction, Direction.WAIT)

    def test_bullish_exhaustion_is_identified(self) -> None:
        data = _indicators()
        data.loc[data.index[-2], "macd_hist"] = 0.9
        data.loc[data.index[-1], ["close", "ema_9", "ema_21", "ema_50", "atr_14",
                                  "adx_14", "rsi_14", "macd_hist"]] = (
                                      110.0, 109.0, 106.0, 104.0, 1.0, 35.0, 82.0, 0.2)
        regime = detect_market_regime(data)
        self.assertTrue(regime.exhausted)
        self.assertIn("EXAUSTÃO COMPRADORA", regime.name)

    def test_bearish_exhaustion_is_identified(self) -> None:
        data = _indicators()
        data.loc[data.index[-2], "macd_hist"] = -0.9
        data.loc[data.index[-1], ["close", "ema_9", "ema_21", "ema_50", "atr_14",
                                  "adx_14", "rsi_14", "macd_hist"]] = (
                                      90.0, 91.0, 94.0, 96.0, 1.0, 35.0, 18.0, -0.2)
        regime = detect_market_regime(data)
        self.assertTrue(regime.exhausted)
        self.assertIn("EXAUSTÃO VENDEDORA", regime.name)


class StructuralEventTests(unittest.TestCase):
    def test_bullish_continuation_break_is_bos(self) -> None:
        data, structure = _event_frame(Direction.BUY, "ALTA")
        result = detect_structure_event(data, structure, timeframe_policy("1m"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.kind, result.direction), ("BOS", Direction.BUY))

    def test_bearish_continuation_break_is_bos(self) -> None:
        data, structure = _event_frame(Direction.SELL, "BAIXA")
        result = detect_structure_event(data, structure, timeframe_policy("1m"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.kind, result.direction), ("BOS", Direction.SELL))

    def test_bullish_trend_change_is_choch(self) -> None:
        data, structure = _event_frame(Direction.BUY, "BAIXA")
        result = detect_structure_event(data, structure, timeframe_policy("1m"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.kind, result.direction), ("CHOCH", Direction.BUY))

    def test_bearish_trend_change_is_choch(self) -> None:
        data, structure = _event_frame(Direction.SELL, "ALTA")
        result = detect_structure_event(data, structure, timeframe_policy("1m"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.kind, result.direction), ("CHOCH", Direction.SELL))

    def test_wick_above_resistance_without_closing_break_is_rejected(self) -> None:
        data, structure = _event_frame(Direction.BUY, "ALTA")
        data.loc[data.index[-1], ["high", "close", "close_position"]] = (101.2, 99.95, 0.45)
        self.assertIsNone(detect_structure_event(data, structure, timeframe_policy("1m")))

    def test_breakout_without_sufficient_atr_displacement_is_rejected(self) -> None:
        data, structure = _event_frame(Direction.BUY, "ALTA")
        data.loc[data.index[-1], "close"] = 100.04
        self.assertIsNone(detect_structure_event(data, structure, timeframe_policy("1m")))

    def test_unconfirmed_recent_pivot_cannot_create_lookahead_break(self) -> None:
        data, structure = _event_frame(Direction.BUY, "ALTA")
        structure.pivot_highs = [len(data) - 2]
        self.assertIsNone(detect_structure_event(data, structure, timeframe_policy("1m")))

    def test_structure_event_label_describes_real_trend_change(self) -> None:
        data, structure = _event_frame(Direction.BUY, "BAIXA")
        event = detect_structure_event(data, structure, timeframe_policy("5m"))
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIn("MUDANÇA DE TENDÊNCIA", event.label)


class PullbackAndDivergenceTests(unittest.TestCase):
    def test_bullish_pullback_is_recognized_and_confirms_resumption(self) -> None:
        data, structure = _pullback_frame(Direction.BUY)
        result = detect_pullback(data, structure, None, timeframe_policy("5m"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.direction, Direction.BUY)
        self.assertTrue(result.confirmed)

    def test_bearish_pullback_is_recognized_and_confirms_resumption(self) -> None:
        data, structure = _pullback_frame(Direction.SELL)
        result = detect_pullback(data, structure, None, timeframe_policy("5m"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.direction, Direction.SELL)
        self.assertTrue(result.confirmed)

    def test_pullback_without_trend_alignment_is_not_invented(self) -> None:
        data, _ = _pullback_frame(Direction.BUY)
        self.assertIsNone(detect_pullback(data, _structure("BAIXA"), None, timeframe_policy("5m")))

    def test_deep_pullback_below_ema50_is_not_valid_continuation(self) -> None:
        data, structure = _pullback_frame(Direction.BUY)
        data.loc[data.index[-2], "low"] = float(data["ema_50"].iloc[-1]) - 5.0
        self.assertIsNone(detect_pullback(data, structure, None, timeframe_policy("5m")))

    def test_regular_bullish_rsi_divergence_uses_confirmed_pivots(self) -> None:
        data = _indicators()
        first, second = len(data) - 15, len(data) - 6
        data.loc[data.index[[first, second]], "low"] = [100.0, 98.0]
        data.loc[data.index[[first, second]], "rsi_14"] = [26.0, 39.0]
        values = detect_momentum_divergences(data, _structure(lows=[first, second]))
        self.assertTrue(any(value.direction == Direction.BUY and not value.hidden
                            and value.oscillator == "RSI" for value in values))

    def test_regular_bearish_rsi_divergence_uses_confirmed_pivots(self) -> None:
        data = _indicators()
        first, second = len(data) - 15, len(data) - 6
        data.loc[data.index[[first, second]], "high"] = [100.0, 103.0]
        data.loc[data.index[[first, second]], "rsi_14"] = [76.0, 63.0]
        values = detect_momentum_divergences(data, _structure(highs=[first, second]))
        self.assertTrue(any(value.direction == Direction.SELL and not value.hidden
                            and value.oscillator == "RSI" for value in values))

    def test_hidden_bullish_divergence_supports_continuation(self) -> None:
        data = _indicators()
        first, second = len(data) - 15, len(data) - 6
        data.loc[data.index[[first, second]], "low"] = [98.0, 100.0]
        data.loc[data.index[[first, second]], "rsi_14"] = [44.0, 34.0]
        values = detect_momentum_divergences(data, _structure(lows=[first, second]))
        self.assertTrue(any(value.direction == Direction.BUY and value.hidden for value in values))

    def test_hidden_bearish_divergence_supports_continuation(self) -> None:
        data = _indicators()
        first, second = len(data) - 15, len(data) - 6
        data.loc[data.index[[first, second]], "high"] = [103.0, 100.0]
        data.loc[data.index[[first, second]], "rsi_14"] = [57.0, 69.0]
        values = detect_momentum_divergences(data, _structure(highs=[first, second]))
        self.assertTrue(any(value.direction == Direction.SELL and value.hidden for value in values))

    def test_stale_divergence_is_not_recycled_as_new_signal(self) -> None:
        data = _indicators()
        first, second = len(data) - 35, len(data) - 22
        data.loc[data.index[[first, second]], "low"] = [100.0, 96.0]
        data.loc[data.index[[first, second]], "rsi_14"] = [20.0, 40.0]
        self.assertFalse(detect_momentum_divergences(data, _structure(lows=[first, second])))

    def test_opposite_regular_divergence_penalizes_blind_continuation(self) -> None:
        data = _indicators()
        first, second = len(data) - 15, len(data) - 6
        data.loc[data.index[[first, second]], "high"] = [100.0, 103.0]
        data.loc[data.index[[first, second]], "rsi_14"] = [80.0, 62.0]
        result = assess_professional_market(data, _structure(highs=[first, second]))
        self.assertTrue(any("DIVERGÊNCIA" in item for item in result.buy_penalties))

    def test_exhausted_pullback_generates_explicit_quality_penalty(self) -> None:
        data = _indicators()
        fake = PullbackSignal(Direction.BUY, 0.90, 2.0, "EMA 21", False, True, ())
        with patch("prime_ai_trader.priceaction.professional.detect_pullback", return_value=fake):
            result = assess_professional_market(data, _structure("ALTA"))
        self.assertTrue(any("profunda" in item for item in result.buy_penalties))

    def test_near_resistance_penalizes_buy_without_room(self) -> None:
        data = _indicators()
        close, atr = float(data["close"].iloc[-1]), float(data["atr_14"].iloc[-1])
        zone = Zone("RESISTÊNCIA", close + atr * 0.08, close + atr * 0.12, 3, len(data) - 8)
        result = assess_professional_market(data, _structure(resistances=[zone]), timeframe="5m")
        self.assertTrue(any("Resistência muito próxima" in item for item in result.buy_penalties))

    def test_near_support_penalizes_sell_without_room(self) -> None:
        data = _indicators()
        close, atr = float(data["close"].iloc[-1]), float(data["atr_14"].iloc[-1])
        zone = Zone("SUPORTE", close - atr * 0.12, close - atr * 0.08, 3, len(data) - 8)
        result = assess_professional_market(data, _structure(supports=[zone]), timeframe="5m")
        self.assertTrue(any("Suporte muito próximo" in item for item in result.sell_penalties))


class ProfessionalFeatureAndSignalTests(unittest.TestCase):
    def test_feature_schema_was_bumped_for_structural_model_compatibility(self) -> None:
        self.assertGreaterEqual(FEATURE_SCHEMA_VERSION, 5)

    def test_all_professional_features_are_available_to_training(self) -> None:
        expected = {"pullback_depth_atr", "impulse_strength_atr", "swing_position_20",
                    "rsi_divergence_proxy", "macd_divergence_proxy", "compression_ratio",
                    "breakout_strength_atr", "liquidity_sweep_code", "reversal_pressure",
                    "ema_9_slope", "ema_21_slope", "candle_sequence_4"}
        self.assertTrue(expected.issubset(FEATURE_COLUMNS))

    def test_new_features_do_not_change_after_future_candles_are_appended(self) -> None:
        frame = candles_frame(synthetic_candles(180, seed=7))
        before, after = build_features(frame.iloc[:130]), build_features(frame)
        pd.testing.assert_frame_equal(before, after.loc[before.index], check_exact=False,
                                      rtol=1e-11, atol=1e-11)

    def test_model_features_never_expose_infinite_values(self) -> None:
        values = build_features(candles_frame(synthetic_candles(180, seed=9)))
        self.assertFalse(np.isinf(values.select_dtypes(include="number").to_numpy()).any())

    def test_all_profiles_modes_and_timeframes_get_structural_context(self) -> None:
        frame = candles_frame(synthetic_candles(180, seed=3))
        indicators = calculate_all(frame)
        features = build_features(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        fib = automatic_fibonacci(frame)
        with tempfile.TemporaryDirectory() as temp:
            engine = SignalEngine(ModelManager(Path(temp)))
            for timeframe in TIMEFRAMES:
                for sensitivity in ("RÁPIDO", "EQUILIBRADO", "CONSERVADOR"):
                    for mode in ("PRICE ACTION", "CONFIRMAÇÃO", "QUANTITATIVO"):
                        with self.subTest(timeframe=timeframe, sensitivity=sensitivity, mode=mode):
                            context = {"timeframe": timeframe, "symbol": "BTC/USDT"}
                            signal = engine.generate(indicators, features, structure, fib, 1,
                                                     sensitivity, True, mode=mode, model_context=context)
                            self.assertEqual(signal.timeframe_context, timeframe)
                            self.assertTrue(signal.market_regime)

    def test_confirmed_bos_is_described_in_directional_confluences(self) -> None:
        data, structure = _event_frame(Direction.BUY, "ALTA")
        result = assess_professional_market(data, structure, timeframe="1m")
        self.assertTrue(any("BOS" in item for item in result.buy_reasons))

    def test_confirmed_choch_penalizes_opposite_old_trend(self) -> None:
        data, structure = _event_frame(Direction.BUY, "BAIXA")
        result = assess_professional_market(data, structure, timeframe="1m")
        self.assertTrue(any("choch" in item.lower() for item in result.sell_penalties))

    def test_independent_categories_do_not_count_substring_di_in_words(self) -> None:
        categories = SignalEngine._independent_confirmations(["Direção definida pela estrutura"])
        self.assertEqual(categories, {"tendência"})


class BacktestStructuralFilterTests(unittest.TestCase):
    @staticmethod
    def _row(**changes) -> pd.Series:
        values = {"adx_14": 22.0, "atr_regime": 1.0, "ema_distance_9_21": 1.0,
                  "ema_distance_21_50": 1.0, "macd_hist": 1.0, "plus_di": 30.0,
                  "minus_di": 12.0, "trend_code": 1.0, "trend_efficiency": 0.45,
                  "compression_ratio": 0.90, "breakout_strength_atr": 0.0,
                  "reversal_pressure": 0.0, "ema21_distance_atr": 1.0}
        values.update(changes)
        return pd.Series(values)

    def test_valid_directional_context_remains_allowed(self) -> None:
        self.assertTrue(_directional_confluence(self._row(), 1, "EQUILIBRADO"))

    def test_backtest_rejects_overextended_price(self) -> None:
        self.assertFalse(_directional_confluence(self._row(ema21_distance_atr=3.2), 1))

    def test_backtest_rejects_opposite_trend_efficiency(self) -> None:
        self.assertFalse(_directional_confluence(self._row(trend_efficiency=-0.40), 1))

    def test_backtest_rejects_compression_without_breakout(self) -> None:
        self.assertFalse(_directional_confluence(self._row(compression_ratio=0.42), 1))

    def test_breakout_can_release_compression(self) -> None:
        self.assertTrue(_directional_confluence(self._row(compression_ratio=0.42,
                                                          breakout_strength_atr=0.30), 1))

    def test_backtest_rejects_opposing_reversal_pressure(self) -> None:
        self.assertFalse(_directional_confluence(self._row(reversal_pressure=-0.45), 1))


class VexLiveGraphTests(unittest.TestCase):
    @staticmethod
    def _candle(snapshot: VexPlatformSnapshot, *, minutes_ago: int = 0) -> Candle:
        start = snapshot.observed_at.replace(second=0, microsecond=0) - timedelta(minutes=minutes_ago)
        return Candle(start, 100.0, 101.0, 99.0, 100.5, 321.0,
                      quote_volume=40_000.0, trades=44, taker_buy_volume=180.0)

    def test_visible_vex_price_updates_current_candle(self) -> None:
        snapshot = _snapshot(price=101.5)
        result = merge_vex_quote(self._candle(snapshot), snapshot, "1m")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.close, 101.5)
        self.assertEqual(result.high, 101.5)
        self.assertFalse(result.closed)

    def test_vex_update_preserves_existing_real_exchange_volume(self) -> None:
        snapshot = _snapshot(price=98.5)
        result = merge_vex_quote(self._candle(snapshot), snapshot, "1m")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.volume, result.quote_volume, result.trades,
                          result.taker_buy_volume), (321.0, 40_000.0, 44, 180.0))
        self.assertEqual(result.low, 98.5)

    def test_new_vex_minute_starts_real_quote_without_fake_volume(self) -> None:
        snapshot = _snapshot(price=102.0)
        result = merge_vex_quote(self._candle(snapshot, minutes_ago=1), snapshot, "1m")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.open, result.high, result.low, result.close, result.volume),
                         (102.0, 102.0, 102.0, 102.0, 0.0))
        self.assertFalse(result.closed)

    def test_stale_vex_price_is_never_applied(self) -> None:
        snapshot = _snapshot(observed_at=datetime.now(timezone.utc) - timedelta(seconds=20))
        self.assertIsNone(merge_vex_quote(self._candle(snapshot), snapshot, "1m"))

    def test_otc_vex_price_is_not_mixed_with_public_market(self) -> None:
        snapshot = _snapshot(otc=True)
        self.assertIsNone(merge_vex_quote(self._candle(snapshot), snapshot, "1m"))

    def test_missing_invalid_or_unauthenticated_vex_price_is_rejected(self) -> None:
        snapshot = _snapshot()
        for changes in ({"price": None}, {"price": 0.0}, {"price": float("nan")},
                        {"authenticated": False}):
            with self.subTest(changes=changes):
                changed = replace(snapshot, **changes)
                self.assertIsNone(merge_vex_quote(self._candle(changed), changed, "1m"))

    def test_unknown_timeframe_is_rejected(self) -> None:
        snapshot = _snapshot()
        self.assertIsNone(merge_vex_quote(self._candle(snapshot), snapshot, "invalid"))

    def test_dashboard_updates_real_visible_vex_price_incrementally(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._vex_snapshot_ready)
        self.assertIn("merge_vex_quote", source)
        self.assertIn("PREÇO VISÍVEL AO VIVO", source)

    def test_websocket_preserves_genuine_closed_candle_confirmation(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._start_crypto_stream)
        self.assertIn("not candle.closed", source)
        self.assertIn("merge_vex_quote", source)

    def test_dashboard_refresh_adapts_to_timeframe_and_sensitivity(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._start_crypto_stream)
        self.assertIn("live_refresh_interval(timeframe", source)


if __name__ == "__main__":
    unittest.main()
