from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from prime_ai_trader.audio.voice import VoiceService
from prime_ai_trader.backtest.engine import _directional_confluence
from prime_ai_trader.core.models import Direction, Signal, SignalState
from prime_ai_trader.features.builder import build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.priceaction.structure import analyze_structure
from prime_ai_trader.signals.engine import (
    CONFLUENCE_MINIMUMS, MOMENTUM_MINIMUMS, PROBABILITY_EDGES,
    SENSITIVITY_PROFILES, THRESHOLDS, SignalEngine, sensitivity_profile,
)
from prime_ai_trader.ui.dashboard import PrimeAITraderApp, voice_message_for_signal
from tests.helpers import synthetic_candles


class ProfileCalibrationTests(unittest.TestCase):
    def _signal(self, state: SignalState = SignalState.WAITING,
                direction: Direction = Direction.WAIT, **extra) -> Signal:
        return Signal(direction, state, 72, {"COMPRA": 0.64}, 100.0, 1, **extra)

    @staticmethod
    def _voice(signal: Signal, profile: str = "RÁPIDO", **overrides):
        options = {
            "strict_risk_blocks": False,
            "voice_confirmed": True,
            "voice_pre_signal": False,
            "voice_alerts": True,
        }
        options.update(overrides)
        return voice_message_for_signal(signal, "BTC/USDT", profile, **options)

    def test_profiles_have_independent_progressive_score_requirements(self) -> None:
        self.assertEqual(THRESHOLDS["RÁPIDO"], 57)
        self.assertLess(THRESHOLDS["RÁPIDO"], THRESHOLDS["EQUILIBRADO"])
        self.assertLess(THRESHOLDS["EQUILIBRADO"], THRESHOLDS["CONSERVADOR"])

    def test_fast_profile_needs_two_confirmations_and_one_momentum_vote(self) -> None:
        self.assertEqual(CONFLUENCE_MINIMUMS["RÁPIDO"], 2)
        self.assertEqual(MOMENTUM_MINIMUMS["RÁPIDO"], 1)

    def test_conservative_profile_has_high_confirmation(self) -> None:
        profile = sensitivity_profile("CONSERVADOR")
        self.assertGreaterEqual(profile.score, 85)
        self.assertGreaterEqual(profile.confluences, 5)
        self.assertGreaterEqual(profile.minimum_adx, 20)
        self.assertIn("ALTA CONFIRMAÇÃO", profile.description)

    def test_fast_profile_has_smaller_model_and_direction_requirements(self) -> None:
        fast = sensitivity_profile("RÁPIDO")
        balanced = sensitivity_profile("EQUILIBRADO")
        self.assertLess(fast.model_weight_factor, balanced.model_weight_factor)
        self.assertLess(fast.direction_gap, balanced.direction_gap)
        self.assertLess(PROBABILITY_EDGES["RÁPIDO"], PROBABILITY_EDGES["EQUILIBRADO"])
        self.assertTrue(fast.early_reading)

    def test_unknown_profile_falls_back_to_balanced(self) -> None:
        self.assertIs(sensitivity_profile("desconhecido"), SENSITIVITY_PROFILES["EQUILIBRADO"])

    def test_fast_profile_can_read_setup_rejected_by_balanced_adx(self) -> None:
        # A semente antiga continha um pullback sem retomada; sua aceitação
        # mascarava o filtro de ADX que este teste realmente pretende isolar.
        frame = candles_frame(synthetic_candles(220, seed=22))
        indicators = calculate_all(frame)
        features = build_features(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        fib = automatic_fibonacci(frame)
        with tempfile.TemporaryDirectory() as temp:
            engine = SignalEngine(ModelManager(Path(temp)))
            fast = engine.generate(indicators, features, structure, fib, 1, "RÁPIDO", True)
            balanced = engine.generate(indicators, features, structure, fib, 1, "EQUILIBRADO", True)
        self.assertNotEqual(fast.direction, Direction.WAIT)
        self.assertEqual(balanced.direction, Direction.WAIT)
        self.assertTrue(any("ADX" in reason for reason in balanced.waiting_reasons))

    def test_backtest_uses_same_category_adx_as_live_signal(self) -> None:
        row = pd.Series({
            "adx_14": 11.0, "atr_regime": 1.0,
            "ema_distance_9_21": 1.0, "ema_distance_21_50": 1.0,
            "macd_hist": 1.0, "plus_di": 25.0, "minus_di": 15.0,
            "trend_code": 1.0,
        })
        self.assertTrue(_directional_confluence(row, 1, "RÁPIDO"))
        self.assertFalse(_directional_confluence(row, 1, "EQUILIBRADO"))
        self.assertFalse(_directional_confluence(row, 1, "CONSERVADOR"))

    def test_price_action_treats_model_disagreement_as_advisory(self) -> None:
        frame = candles_frame(synthetic_candles(220, seed=3))
        indicators = calculate_all(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        manager = SimpleNamespace(
            is_compatible=lambda context: True,
            predict_proba=lambda rows: {1: 0.55, -1: 0.04, 0: 0.41},
            report=SimpleNamespace(version="profile-test"),
        )
        signal = SignalEngine(manager).generate(
            indicators, build_features(frame), structure, automatic_fibonacci(frame),
            1, "RÁPIDO", True, mode="PRICE ACTION",
            model_context={"symbol": "BTC/USDT"}, payout_percent=80,
        )
        self.assertEqual(signal.direction, Direction.BUY)
        self.assertTrue(any("Modelo diverge" in reason for reason in signal.warnings))
        self.assertFalse(any("mínimo técnico" in reason for reason in signal.waiting_reasons))

    def test_quantitative_keeps_model_floor_for_every_sensitivity(self) -> None:
        frame = candles_frame(synthetic_candles(220, seed=3))
        indicators = calculate_all(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        manager = SimpleNamespace(
            is_compatible=lambda context: True,
            predict_proba=lambda rows: {1: 0.55, -1: 0.04, 0: 0.41},
            report=SimpleNamespace(version="profile-test"),
        )
        engine = SignalEngine(manager)
        values = (indicators, build_features(frame), structure, automatic_fibonacci(frame))
        for sensitivity, floor in (("RÁPIDO", "55.8/100"),
                                   ("EQUILIBRADO", "60.0/100"),
                                   ("CONSERVADOR", "70.0/100")):
            with self.subTest(sensitivity=sensitivity):
                signal = engine.generate(
                    *values, 1, sensitivity, True, mode="QUANTITATIVO",
                    model_context={"symbol": "BTC/USDT"}, payout_percent=80,
                )
                self.assertEqual(signal.direction, Direction.WAIT)
                self.assertTrue(any(
                    f"mínimo técnico {floor}" in reason for reason in signal.waiting_reasons
                ))

    def test_non_blocking_risk_warning_never_speaks(self) -> None:
        signal = self._signal(warnings=["Notícia de alto risco: FED"])
        self.assertIsNone(self._voice(signal))

    def test_blocking_risk_only_speaks_when_strict_block_is_enabled(self) -> None:
        signal = self._signal(SignalState.BLOCKED, blockers=["Evento de alto impacto"])
        self.assertIsNone(self._voice(signal, strict_risk_blocks=False))
        spoken = self._voice(signal, strict_risk_blocks=True)
        self.assertIsNotNone(spoken)
        assert spoken is not None
        self.assertIn("bloqueadas", spoken[0])
        self.assertEqual(spoken[1], 300.0)

    def test_confirmed_signal_takes_priority_over_a_risk_warning(self) -> None:
        signal = self._signal(SignalState.CONFIRMED, Direction.BUY,
                              warnings=["Notícia de alto risco"])
        spoken = self._voice(signal)
        self.assertIsNotNone(spoken)
        assert spoken is not None
        self.assertIn("compra confirmado", spoken[0])
        self.assertNotIn("risco", spoken[0])

    def test_fast_profile_does_not_announce_unrequested_pre_signal(self) -> None:
        signal = self._signal(SignalState.FORMING, Direction.SELL)
        spoken = self._voice(signal, "RÁPIDO")
        self.assertIsNone(spoken)

    def test_fast_profile_announces_early_direction_only_after_explicit_opt_in(self) -> None:
        signal = self._signal(SignalState.FORMING, Direction.SELL)
        spoken = self._voice(signal, "RÁPIDO", voice_pre_signal=True)
        self.assertIsNotNone(spoken)
        assert spoken is not None
        self.assertIn("Leitura rápida de venda", spoken[0])
        self.assertIn("formação", spoken[0])
        self.assertNotIn("confirmado", spoken[0])

    def test_balanced_profile_respects_disabled_pre_signal(self) -> None:
        signal = self._signal(SignalState.FORMING, Direction.BUY)
        self.assertIsNone(self._voice(signal, "EQUILIBRADO"))

    def test_balanced_profile_can_announce_enabled_pre_signal(self) -> None:
        signal = self._signal(SignalState.FORMING, Direction.BUY)
        spoken = self._voice(signal, "EQUILIBRADO", voice_pre_signal=True)
        self.assertIsNotNone(spoken)
        assert spoken is not None
        self.assertIn("Possível sinal de compra", spoken[0])

    def test_disabled_confirmed_audio_also_disables_automatic_fast_reading(self) -> None:
        signal = self._signal(SignalState.FORMING, Direction.BUY)
        self.assertIsNone(self._voice(signal, "RÁPIDO", voice_confirmed=False))

    def test_warning_changes_do_not_retrigger_voice_signature(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._render_signal)
        self.assertNotIn("tuple(signal.warnings)", source)
        self.assertNotIn("Existe um aviso de risco para esta análise", source)

    def test_voice_cooldown_is_tracked_per_message(self) -> None:
        voice = VoiceService()
        self.assertTrue(voice._reserve_message("risco", 300.0, 1000.0))
        self.assertTrue(voice._reserve_message("compra", 8.0, 1010.0))
        self.assertFalse(voice._reserve_message("risco", 300.0, 1020.0))
        self.assertTrue(voice._reserve_message("risco", 300.0, 1301.0))


if __name__ == "__main__":
    unittest.main()
