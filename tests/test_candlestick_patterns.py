from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from prime_ai_trader.backtest.engine import _directional_confluence
from prime_ai_trader.core.models import Direction, Market, SignalState
from prime_ai_trader.features.builder import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.priceaction.candles import (
    analyze_candlestick_patterns, candlestick_feature_frame,
)
from prime_ai_trader.priceaction.structure import analyze_structure
from prime_ai_trader.signals.engine import RuleAssessment, SignalEngine
from tests.helpers import synthetic_candles


def _frame(rows: list[tuple[float, float, float, float]], spacing: str = "1min",
           scale: float = 1.0) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(rows), freq=spacing, tz="UTC")
    values = [[value * scale for value in row] for row in rows]
    frame = pd.DataFrame(values, columns=["open", "high", "low", "close"], index=index)
    frame["volume"] = 1000.0
    frame["quote_volume"] = frame["volume"] * frame["close"]
    frame["taker_buy_volume"] = 500.0
    frame["atr_14"] = (frame["high"] - frame["low"]).rolling(3, min_periods=1).mean()
    return frame


class CandlestickLibraryTests(unittest.TestCase):
    def test_bullish_and_bearish_engulfing_are_detected(self) -> None:
        bullish = _frame([
            (10.0, 10.4, 9.8, 10.2),
            (10.5, 10.6, 9.8, 10.0),
            (9.9, 10.8, 9.7, 10.7),
        ])
        bearish = _frame([
            (10.0, 10.4, 9.8, 10.2),
            (10.0, 10.7, 9.9, 10.6),
            (10.7, 10.8, 9.7, 9.8),
        ])
        self.assertIn("ENGOLFO COMPRADOR", [item.name for item in analyze_candlestick_patterns(bullish).patterns])
        self.assertIn("ENGOLFO VENDEDOR", [item.name for item in analyze_candlestick_patterns(bearish).patterns])

    def test_pin_bars_identify_the_wick_reversal_risk(self) -> None:
        bullish = _frame([(10, 10.4, 9.8, 10.2), (10.2, 10.4, 9.9, 10.1), (10.1, 10.3, 8.8, 10.2)])
        bearish = _frame([(10, 10.4, 9.8, 10.2), (10.2, 10.4, 9.9, 10.1), (10.2, 11.5, 10.0, 10.1)])
        buy = analyze_candlestick_patterns(bullish)
        sell = analyze_candlestick_patterns(bearish)
        self.assertGreaterEqual(buy.directional_strength(Direction.BUY), 0.72)
        self.assertGreaterEqual(sell.directional_strength(Direction.SELL), 0.72)

    def test_morning_and_evening_stars_use_three_closed_candles(self) -> None:
        morning = _frame([(11.0, 11.1, 9.8, 10.0), (10.0, 10.25, 9.85, 10.05), (10.0, 10.8, 9.95, 10.7)])
        evening = _frame([(10.0, 11.2, 9.9, 11.0), (11.0, 11.2, 10.8, 10.95), (11.0, 11.05, 10.1, 10.2)])
        self.assertIn("ESTRELA DA MANHÃ", [item.name for item in analyze_candlestick_patterns(morning).patterns])
        self.assertIn("ESTRELA DA TARDE", [item.name for item in analyze_candlestick_patterns(evening).patterns])

    def test_harami_patterns_require_containment_inside_previous_body(self) -> None:
        bullish = _frame([(10, 10.2, 9.8, 10.1), (11, 11.1, 9.7, 9.8), (9.9, 10.5, 9.85, 10.3)])
        bearish = _frame([(10, 10.2, 9.8, 10.1), (9.8, 11.1, 9.7, 11.0), (10.9, 10.95, 10.3, 10.5)])
        self.assertIn("HARAMI COMPRADOR", [item.name for item in analyze_candlestick_patterns(bullish).patterns])
        self.assertIn("HARAMI VENDEDOR", [item.name for item in analyze_candlestick_patterns(bearish).patterns])

    def test_three_soldiers_and_three_crows_require_progressive_closes(self) -> None:
        soldiers = _frame([(10, 10.7, 9.9, 10.6), (10.4, 11.2, 10.3, 11.1), (10.9, 11.8, 10.8, 11.7)])
        crows = _frame([(12, 12.1, 11.3, 11.4), (11.6, 11.7, 10.8, 10.9), (11.0, 11.1, 10.2, 10.3)])
        self.assertIn("TRÊS SOLDADOS BRANCOS", [item.name for item in analyze_candlestick_patterns(soldiers).patterns])
        self.assertIn("TRÊS CORVOS NEGROS", [item.name for item in analyze_candlestick_patterns(crows).patterns])

    def test_marubozu_requires_dominant_body_and_small_wicks(self) -> None:
        frame = _frame([(10, 10.2, 9.8, 10.1), (10.1, 10.3, 10, 10.2), (10.2, 11.2, 10.2, 11.2)])
        result = analyze_candlestick_patterns(frame)
        self.assertIn("MARUBOZU COMPRADOR", [item.name for item in result.patterns])
        self.assertGreaterEqual(result.directional_strength(Direction.BUY), 0.74)

    def test_doji_and_inside_bar_are_indecision_not_directional_orders(self) -> None:
        frame = _frame([(10.0, 10.7, 9.6, 10.5), (10.5, 10.8, 9.8, 10.0), (10.2, 10.6, 9.9, 10.205)])
        result = analyze_candlestick_patterns(frame)
        self.assertGreaterEqual(result.indecision, 0.76)
        self.assertEqual(result.directional_strength(Direction.BUY), 0.0)
        self.assertEqual(result.directional_strength(Direction.SELL), 0.0)

    def test_open_candle_pattern_is_reported_as_forming_not_confirmed(self) -> None:
        frame = _frame([(10, 10.3, 9.8, 10.1), (10.3, 10.4, 9.8, 10.0), (9.9, 10.6, 9.7, 10.5)])
        result = analyze_candlestick_patterns(frame, current_closed=False, timeframe="1m")
        self.assertTrue(result.patterns)
        self.assertTrue(all(not item.confirmed for item in result.patterns))
        self.assertTrue(all("EM FORMAÇÃO" in item.label for item in result.patterns))
        self.assertEqual(result.directional_strength(Direction.BUY), 0.0)

    def test_detector_is_price_scale_and_timeframe_independent(self) -> None:
        rows = [(10.0, 10.4, 9.8, 10.2), (10.5, 10.6, 9.8, 10.0), (9.9, 10.8, 9.7, 10.7)]
        for spacing, scale in (("1min", 1.0), ("5min", 100.0), ("1h", 0.001), ("4h", 10_000.0)):
            with self.subTest(spacing=spacing, scale=scale):
                names = [item.name for item in analyze_candlestick_patterns(
                    _frame(rows, spacing, scale), timeframe=spacing,
                ).patterns]
                self.assertIn("ENGOLFO COMPRADOR", names)

    def test_pattern_features_are_causal_when_future_is_appended(self) -> None:
        candles = synthetic_candles(220, seed=29)
        base = candles_frame(candles[:180])
        future = candles_frame(candles)
        before = candlestick_feature_frame(calculate_all(base))
        after = candlestick_feature_frame(calculate_all(future)).loc[before.index]
        pd.testing.assert_frame_equal(before, after)

    def test_feature_schema_includes_candle_library_without_lookahead(self) -> None:
        expected = {
            "candlestick_bias", "candlestick_reversal", "candlestick_indecision",
            "candlestick_exhaustion", "engulfing_code", "pinbar_code",
            "three_candle_code",
        }
        self.assertGreaterEqual(FEATURE_SCHEMA_VERSION, 7)
        self.assertTrue(expected.issubset(FEATURE_COLUMNS))
        frame = candles_frame(synthetic_candles(160, seed=31))
        self.assertEqual(build_features(frame).columns.tolist(), FEATURE_COLUMNS)

    def test_backtest_rejects_opposing_pattern_indecision_and_exhaustion(self) -> None:
        base = {
            "adx_14": 30.0, "atr_regime": 1.0, "ema21_distance_atr": 0.2,
            "trend_efficiency": 0.7, "compression_ratio": 1.0,
            "breakout_strength_atr": 0.0, "reversal_pressure": 0.0,
            "ema_distance_9_21": 1.0, "ema_distance_21_50": 1.0,
            "macd_hist": 1.0, "plus_di": 30.0, "minus_di": 10.0,
            "trend_code": 1.0,
        }
        self.assertFalse(_directional_confluence(pd.Series({**base, "candlestick_reversal": -0.9}), 1, "RÁPIDO"))
        self.assertFalse(_directional_confluence(pd.Series({**base, "candlestick_indecision": 1.0}), 1, "RÁPIDO"))
        self.assertFalse(_directional_confluence(pd.Series({**base, "candlestick_exhaustion": 0.8}), 1, "RÁPIDO"))

    def test_strict_one_minute_mode_blocks_confirmed_doji(self) -> None:
        frame = candles_frame(synthetic_candles(220, seed=3))
        indicators = calculate_all(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        context = {
            "market": Market.CRYPTO.value, "symbol": "BTC/USDT", "timeframe": "1m",
            "horizon_minutes": 1, "strategy": "crypto-structure-volume-candles-v7",
            "sensitivity": "RÁPIDO", "mode": "CONFIRMAÇÃO", "feature_schema": FEATURE_SCHEMA_VERSION,
        }
        with tempfile.TemporaryDirectory() as temporary:
            signal = SignalEngine(ModelManager(Path(temporary))).generate(
                indicators, build_features(frame, Market.CRYPTO.value, "BTC/USDT"),
                structure, automatic_fibonacci(frame), 1, "RÁPIDO", True,
                mode="CONFIRMAÇÃO", model_context=context,
            )
        self.assertEqual(signal.state, SignalState.WAITING)
        self.assertTrue(any("indecisão" in reason for reason in signal.waiting_reasons))
        self.assertTrue(signal.candlestick_patterns)

    def test_fast_contextual_doji_preserves_aligned_trend_but_balanced_blocks(self) -> None:
        frame = candles_frame(synthetic_candles(260, seed=3))
        indicators = calculate_all(frame)
        features = build_features(frame, Market.CRYPTO.value, "BTC/USDT")
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        base_context = {
            "market": Market.CRYPTO.value, "symbol": "BTC/USDT", "timeframe": "1m",
            "horizon_minutes": 1, "strategy": "crypto-structure-volume-candles-v7",
            "mode": "CONFIRMAÇÃO", "feature_schema": FEATURE_SCHEMA_VERSION,
        }
        # Isola a política de doji: um pullback incompleto é um veto próprio
        # e não pode ser usado para demonstrar indecisão contextual segura.
        with tempfile.TemporaryDirectory() as temporary, patch(
            "prime_ai_trader.priceaction.professional.detect_pullback", return_value=None,
        ):
            engine = SignalEngine(ModelManager(Path(temporary)))
            fast = engine.generate(
                indicators, features, structure, automatic_fibonacci(frame),
                1, "RÁPIDO", True, mode="CONFIRMAÇÃO",
                model_context={**base_context, "sensitivity": "RÁPIDO"},
            )
            balanced = engine.generate(
                indicators, features, structure, automatic_fibonacci(frame),
                1, "EQUILIBRADO", True, mode="CONFIRMAÇÃO",
                model_context={**base_context, "sensitivity": "EQUILIBRADO"},
            )
        self.assertEqual(fast.direction, Direction.BUY)
        self.assertTrue(any("indecisão dentro de tendência alinhada" in item
                            for item in fast.warnings))
        self.assertEqual(balanced.direction, Direction.WAIT)
        self.assertTrue(any("indecisão sem contexto direcional seguro" in item
                            for item in balanced.waiting_reasons))

    def test_strict_one_minute_mode_blocks_pattern_opposite_to_suggested_side(self) -> None:
        frame = _frame([(10, 10.4, 9.8, 10.2), (10.5, 10.6, 9.8, 10.0), (9.9, 10.8, 9.7, 10.7)])
        indicators = calculate_all(frame)
        features = build_features(frame, Market.CRYPTO.value, "BTC/USDT")
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))

        def forced_sell(_indicators, _structure, _fib, professional, _mode,
                        _market, _symbol, candlesticks):
            return RuleAssessment(
                0, 100, [], ["Estrutura profissional LH/LL", "MACD vendedor"],
                sell_setup="CONTINUIDADE DE TENDÊNCIA", professional=professional,
                candlesticks=candlesticks,
            )

        context = {
            "market": Market.CRYPTO.value, "symbol": "BTC/USDT", "timeframe": "1m",
            "horizon_minutes": 1, "strategy": "crypto-structure-volume-candles-v7",
            "sensitivity": "RÁPIDO", "mode": "CONFIRMAÇÃO", "feature_schema": FEATURE_SCHEMA_VERSION,
        }
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            SignalEngine, "assess_rules", side_effect=forced_sell,
        ):
            signal = SignalEngine(ModelManager(Path(temporary))).generate(
                indicators, features, structure, None, 1, "RÁPIDO", True,
                mode="CONFIRMAÇÃO", model_context=context,
            )
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertTrue(any("engolfo comprador" in reason for reason in signal.waiting_reasons))


if __name__ == "__main__":
    unittest.main()
