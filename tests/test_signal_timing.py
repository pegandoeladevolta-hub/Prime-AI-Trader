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
    RuleAssessment, SignalEngine, model_disagreement_is_blocking,
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


class FastConfirmedTimingTests(unittest.TestCase):
    def _signal(self, age_seconds: float, *, state: SignalState = SignalState.CONFIRMED) -> Signal:
        return Signal(
            Direction.SELL, state, 90,
            {"COMPRA": 0.39, "VENDA": 0.42, "AGUARDAR": 0.19},
            0.7976, 1,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        )

    def test_fast_m1_confirmation_has_short_visible_entry_window(self) -> None:
        self.assertEqual(
            confirmed_entry_window_seconds("1m", 1, "RÁPIDO", "CONFIRMAÇÃO"),
            8.0,
        )
        self.assertEqual(
            confirmed_entry_window_seconds("5m", 1, "RÁPIDO", "CONFIRMAÇÃO"),
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

    def test_fast_confirmation_uses_model_as_advisory(self) -> None:
        self.assertFalse(model_disagreement_is_blocking("CONFIRMAÇÃO", "RÁPIDO"))
        self.assertTrue(model_disagreement_is_blocking("CONFIRMAÇÃO", "EQUILIBRADO"))
        self.assertTrue(model_disagreement_is_blocking("QUANTITATIVO", "RÁPIDO"))

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
            "horizon_minutes": 1, "strategy": "crypto-structure-volume-candles-v5",
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


if __name__ == "__main__":
    unittest.main()
