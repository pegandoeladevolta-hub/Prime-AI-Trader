from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from prime_ai_trader.core.models import Direction, Market, Signal, SignalState
from prime_ai_trader.features.builder import FEATURE_SCHEMA_VERSION, build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.priceaction.structure import analyze_structure
from prime_ai_trader.signals.engine import (
    RuleAssessment, SignalEngine, decision_policy, model_disagreement_is_blocking,
)
from prime_ai_trader.signals.timing import (
    confirmed_entry_window_seconds, preserve_recent_confirmed_signal,
)
from tests.helpers import synthetic_candles


class _ModelReport:
    version = "test-model"


class _DivergentModel:
    report = _ModelReport()

    @staticmethod
    def is_compatible(_context) -> bool:
        return True

    @staticmethod
    def predict_proba(_features) -> dict[int, float]:
        return {-1: 0.42, 0: 0.19, 1: 0.39}


class _NoModel:
    report = None

    @staticmethod
    def is_compatible(_context) -> bool:
        return False


class FastConfirmedTimingTests(unittest.TestCase):
    def _signal(self, age_seconds: float, *, state: SignalState = SignalState.CONFIRMED) -> Signal:
        return Signal(
            Direction.SELL, state, 90,
            {"COMPRA": 0.39, "VENDA": 0.42, "AGUARDAR": 0.19},
            0.7976, 1,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        )

    def test_all_profiles_and_modes_have_short_visible_entry_window(self) -> None:
        for sensitivity in ("RÁPIDO", "EQUILIBRADO", "CONSERVADOR"):
            for mode in ("PRICE ACTION", "CONFIRMAÇÃO", "QUANTITATIVO"):
                with self.subTest(sensitivity=sensitivity, mode=mode):
                    self.assertEqual(
                        confirmed_entry_window_seconds("1m", 1, sensitivity, mode), 8.0,
                    )
        self.assertEqual(
            confirmed_entry_window_seconds("5m", 1, "RÁPIDO", "PRICE ACTION"), 9.0,
        )
        for timeframe in ("3m", "15m", "30m", "1h", "4h"):
            self.assertGreater(
                confirmed_entry_window_seconds(timeframe, 5, "CONSERVADOR", "QUANTITATIVO"),
                0.0,
            )

    def test_new_open_candle_does_not_immediately_erase_confirmed_signal(self) -> None:
        self.assertTrue(preserve_recent_confirmed_signal(
            self._signal(3), candle_closed=False, timeframe="1m", horizon_minutes=1,
            sensitivity="RÁPIDO", mode="CONFIRMAÇÃO",
        ))

    def test_expired_or_nonconfirmed_signal_is_not_preserved(self) -> None:
        self.assertFalse(preserve_recent_confirmed_signal(
            self._signal(9), candle_closed=False, timeframe="1m", horizon_minutes=1,
            sensitivity="RÁPIDO", mode="CONFIRMAÇÃO",
        ))
        self.assertFalse(preserve_recent_confirmed_signal(
            self._signal(2, state=SignalState.FORMING), candle_closed=False,
            timeframe="1m", horizon_minutes=1, sensitivity="RÁPIDO", mode="CONFIRMAÇÃO",
        ))

    def test_closed_candle_is_always_reprocessed(self) -> None:
        self.assertFalse(preserve_recent_confirmed_signal(
            self._signal(2), candle_closed=True, timeframe="1m", horizon_minutes=1,
            sensitivity="RÁPIDO", mode="CONFIRMAÇÃO",
        ))

    def test_only_quantitative_mode_uses_model_as_isolated_veto(self) -> None:
        for sensitivity in ("RÁPIDO", "EQUILIBRADO", "CONSERVADOR"):
            self.assertFalse(model_disagreement_is_blocking("PRICE ACTION", sensitivity))
            self.assertFalse(model_disagreement_is_blocking("CONFIRMAÇÃO", sensitivity))
            self.assertTrue(model_disagreement_is_blocking("QUANTITATIVO", sensitivity))

    def test_all_nine_mode_profile_combinations_have_explicit_policy(self) -> None:
        policies = {
            (mode, sensitivity): decision_policy(mode, sensitivity)
            for mode in ("PRICE ACTION", "CONFIRMAÇÃO", "QUANTITATIVO")
            for sensitivity in ("RÁPIDO", "EQUILIBRADO", "CONSERVADOR")
        }
        self.assertEqual(len(policies), 9)
        self.assertTrue(all(item.minimum_independent == 0
                            for (mode, _), item in policies.items() if mode == "PRICE ACTION"))
        self.assertTrue(all(item.model_required and item.model_gate
                            for (mode, _), item in policies.items() if mode == "QUANTITATIVO"))
        self.assertLess(
            policies[("CONFIRMAÇÃO", "CONSERVADOR")].opposite_pattern_threshold,
            policies[("CONFIRMAÇÃO", "RÁPIDO")].opposite_pattern_threshold,
        )

    def _generated_signal(self, mode: str) -> Signal:
        frame = candles_frame(synthetic_candles(220, seed=41))
        indicators = calculate_all(frame)
        features = build_features(frame, Market.CRYPTO.value, "SUI/USDT")
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))

        def forced_sell(_indicators, _structure, _fib, professional, _mode,
                        _market, _symbol, candlesticks):
            return RuleAssessment(
                0, 120, [], [
                    "EMA 9 abaixo da EMA 21", "MACD abaixo da linha de sinal",
                    "Momentum vendedor acelerando", "ADX/-DI confirma força vendedora",
                ],
                sell_setup="CONTINUIDADE DE TENDÊNCIA", professional=professional,
                candlesticks=candlesticks,
            )

        context = {
            "market": Market.CRYPTO.value, "symbol": "SUI/USDT", "timeframe": "1m",
            "horizon_minutes": 1, "strategy": "crypto-structure-volume-candles-v6",
            "sensitivity": "RÁPIDO", "mode": mode,
            "feature_schema": FEATURE_SCHEMA_VERSION,
        }
        with patch.object(SignalEngine, "assess_rules", side_effect=forced_sell):
            return SignalEngine(_DivergentModel()).generate(
                indicators, features, structure, automatic_fibonacci(indicators),
                1, "RÁPIDO", True, mode=mode, model_context=context, payout_percent=82,
            )

    def test_fast_confirmation_exposes_model_disagreement_as_warning(self) -> None:
        signal = self._generated_signal("CONFIRMAÇÃO")
        self.assertEqual(signal.model_score, 42)
        self.assertIsNone(signal.expected_value)
        self.assertTrue(any("Modelo diverge" in item for item in signal.warnings))
        self.assertFalse(any("Score IA" in item for item in signal.waiting_reasons))

    def test_quantitative_mode_keeps_model_disagreement_as_visible_veto(self) -> None:
        signal = self._generated_signal("QUANTITATIVO")
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertTrue(signal.waiting_reasons[0].startswith("Score IA 42.0/100"))

    def test_quantitative_mode_requires_trained_context_model(self) -> None:
        frame = candles_frame(synthetic_candles(220, seed=43))
        indicators = calculate_all(frame)
        features = build_features(frame, Market.CRYPTO.value, "BTC/USDT")
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        context = {
            "market": Market.CRYPTO.value, "symbol": "BTC/USDT", "timeframe": "1m",
            "horizon_minutes": 1, "strategy": "crypto-structure-volume-candles-v6",
            "sensitivity": "RÁPIDO", "mode": "QUANTITATIVO",
            "feature_schema": FEATURE_SCHEMA_VERSION,
        }
        signal = SignalEngine(_NoModel()).generate(
            indicators, features, structure, automatic_fibonacci(indicators),
            1, "RÁPIDO", True, mode="QUANTITATIVO", model_context=context,
        )
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertEqual(
            signal.waiting_reasons[0],
            "Modo quantitativo exige IA treinada para este contexto",
        )


if __name__ == "__main__":
    unittest.main()
