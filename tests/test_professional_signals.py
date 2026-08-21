from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.controller import TradingController
from prime_ai_trader.backtest.engine import _wilson_interval
from prime_ai_trader.core.models import Direction, Market, Signal, SignalState
from prime_ai_trader.features.builder import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.priceaction.structure import analyze_structure
from prime_ai_trader.signals.engine import CONFLUENCE_MINIMUMS, SignalEngine
from tests.helpers import synthetic_candles


class ProfessionalSignalTests(unittest.TestCase):
    @staticmethod
    def _inputs(seed: int = 3):
        frame = candles_frame(synthetic_candles(220, seed=seed))
        indicators = calculate_all(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        return frame, indicators, build_features(frame), structure, automatic_fibonacci(frame)

    def test_professional_feature_schema_contains_price_action_and_momentum(self) -> None:
        self.assertGreaterEqual(FEATURE_SCHEMA_VERSION, 4)
        self.assertTrue({
            "macd_acceleration", "rsi_slope", "stoch_spread", "ema21_distance_atr",
            "candle_rejection", "breakout_20", "higher_trend_proxy",
        }.issubset(FEATURE_COLUMNS))

    def test_fast_profile_can_confirm_directional_professional_setup(self) -> None:
        _, indicators, features, structure, fib = self._inputs(3)
        with tempfile.TemporaryDirectory() as temp:
            signal = SignalEngine(ModelManager(Path(temp))).generate(
                indicators, features, structure, fib, 1, "RÁPIDO", True,
            )
        self.assertEqual(signal.direction, Direction.BUY)
        self.assertEqual(signal.state, SignalState.CONFIRMED)
        self.assertGreaterEqual(len(signal.confluences), 3)
        self.assertGreaterEqual(signal.technical_score, 68)

    def test_wait_signal_explains_its_actual_reason(self) -> None:
        _, indicators, features, structure, fib = self._inputs(2)
        with tempfile.TemporaryDirectory() as temp:
            signal = SignalEngine(ModelManager(Path(temp))).generate(
                indicators, features, structure, fib, 1, "RÁPIDO", True,
            )
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertTrue(signal.waiting_reasons)
        self.assertIn("ADX", signal.waiting_reasons[0])

    def test_sensitivity_profiles_have_distinct_confirmation_requirements(self) -> None:
        self.assertLess(CONFLUENCE_MINIMUMS["RÁPIDO"], CONFLUENCE_MINIMUMS["EQUILIBRADO"])
        self.assertLess(CONFLUENCE_MINIMUMS["EQUILIBRADO"], CONFLUENCE_MINIMUMS["CONSERVADOR"])

    def test_payout_80_percent_has_correct_break_even(self) -> None:
        _, indicators, features, structure, fib = self._inputs(3)
        with tempfile.TemporaryDirectory() as temp:
            signal = SignalEngine(ModelManager(Path(temp))).generate(
                indicators, features, structure, fib, 1, "RÁPIDO", True,
                payout_percent=80,
            )
        self.assertAlmostEqual(signal.break_even_rate, 1 / 1.8)

    def test_payout_74_percent_has_correct_break_even(self) -> None:
        _, indicators, features, structure, fib = self._inputs(3)
        with tempfile.TemporaryDirectory() as temp:
            signal = SignalEngine(ModelManager(Path(temp))).generate(
                indicators, features, structure, fib, 1, "RÁPIDO", True,
                payout_percent=74,
            )
        self.assertAlmostEqual(signal.break_even_rate, 1 / 1.74)

    def test_model_and_technical_agreement_does_not_artificially_crush_score(self) -> None:
        _, indicators, features, structure, fib = self._inputs(3)
        manager = SimpleNamespace(
            is_compatible=lambda context: True,
            predict_proba=lambda rows: {1: 0.605, -1: 0.02, 0: 0.375},
            report=SimpleNamespace(version="test-model"),
        )
        signal = SignalEngine(manager).generate(
            indicators, features, structure, fib, 1, "RÁPIDO", True,
            model_context={"symbol": "BTC/USDT"}, payout_percent=80,
        )
        self.assertEqual(signal.direction, Direction.BUY)
        self.assertGreaterEqual(signal.score, 68)
        self.assertEqual(signal.model_score, 60)

    def test_wilson_interval_reflects_small_sample_uncertainty(self) -> None:
        low, high = _wilson_interval(5, 9)
        self.assertLess(low, 0.40)
        self.assertGreater(high, 0.70)

    def test_live_websocket_confirmed_signal_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            candles = synthetic_candles(180)
            wait = Signal(Direction.WAIT, SignalState.WAITING, 55, {"AGUARDAR": 1}, None, 5)
            confirmed = Signal(Direction.BUY, SignalState.CONFIRMED, 82, {"COMPRA": 0.75}, candles[-1].close, 5)
            with patch.object(controller.binance, "fetch_candles", return_value=candles), patch.object(
                controller.news_provider, "fetch", return_value=[],
            ), patch.object(controller.signal_engine, "generate", side_effect=[wait, confirmed]):
                controller.analyze()
                controller.merge_live_candle(candles[-1])
            self.assertEqual(len(controller.repository.pending("BTC/USDT", "5m")), 1)

    def test_small_real_price_move_is_not_misclassified_as_draw(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            signal = Signal(
                Direction.BUY, SignalState.CONFIRMED, 75, {"COMPRA": 0.7},
                100.0, 1, created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            )
            controller.repository.save_signal(
                signal, Market.CRYPTO.value, "BTC/USDT", "1m", {"atr_14": 1.0}, "CONFIRMAÇÃO",
            )
            controller._settle_pending("BTC/USDT", "1m", 100.02)
            self.assertEqual(controller.repository.statistics()["wins"], 1)

    def test_small_backtest_sample_is_not_shown_as_yellow_risk(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            key = (Market.CRYPTO.value, "BTC/USDT", "5m", 5)
            controller._quality_gate[key] = SimpleNamespace(
                quality="AMOSTRA EM FORMAÇÃO", directional_operations=9, accuracy=5 / 9,
            )
            signal = Signal(Direction.BUY, SignalState.CONFIRMED, 80, {"COMPRA": 0.7}, 100.0, 5)
            result = controller._apply_quality_gate(signal, *key)
            self.assertFalse(result.warnings)
            self.assertIn("9/20", result.validation_note)


if __name__ == "__main__":
    unittest.main()
