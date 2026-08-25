from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from prime_ai_trader.backtest.engine import _directional_confluence
from prime_ai_trader.core.models import Direction, Market
from prime_ai_trader.features.builder import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_features
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.priceaction.professional import (
    StructureEvent, _pullback_direction, assess_professional_market,
    assess_pullback_context, detect_pullback, timeframe_policy,
)
from prime_ai_trader.signals.engine import RuleAssessment, SignalEngine
from prime_ai_trader.strategies.context import strategy_key
from tests.test_professional_price_action import _pullback_frame


class PullbackDirectionAuditTests(unittest.TestCase):
    @staticmethod
    def _correction(direction: Direction):
        indicators, structure = _pullback_frame(direction)
        last = indicators.index[-1]
        previous = indicators.iloc[-2]
        atr = float(indicators.at[last, "atr_14"])
        ema_21 = float(indicators.at[last, "ema_21"])
        if direction == Direction.BUY:
            close = float(previous["close"]) - atr * 0.18
            opened = close + atr * 0.26
            indicators.loc[last, ["open", "high", "low", "close", "close_position",
                                  "ema_9", "macd_hist", "rsi_14"]] = (
                opened, opened + atr * 0.08, close - atr * 0.05, close, 0.18,
                ema_21 - atr * 0.18, float(previous["macd_hist"]) - atr * 0.04,
                float(previous["rsi_14"]) - 2.0,
            )
        else:
            close = float(previous["close"]) + atr * 0.18
            opened = close - atr * 0.26
            indicators.loc[last, ["open", "high", "low", "close", "close_position",
                                  "ema_9", "macd_hist", "rsi_14"]] = (
                opened, close + atr * 0.05, opened - atr * 0.08, close, 0.82,
                ema_21 + atr * 0.18, float(previous["macd_hist"]) + atr * 0.04,
                float(previous["rsi_14"]) + 2.0,
            )
        return indicators, structure

    def test_bullish_pullback_does_not_flip_when_ema9_crosses_ema21(self) -> None:
        indicators, structure = self._correction(Direction.BUY)
        self.assertEqual(_pullback_direction(indicators, structure), Direction.BUY)
        found = detect_pullback(indicators, structure, None, timeframe_policy("5m"))
        if found is not None:
            self.assertEqual(found.direction, Direction.BUY)

    def test_bearish_pullback_does_not_flip_when_ema9_crosses_ema21(self) -> None:
        indicators, structure = self._correction(Direction.SELL)
        self.assertEqual(_pullback_direction(indicators, structure), Direction.SELL)
        found = detect_pullback(indicators, structure, None, timeframe_policy("5m"))
        if found is not None:
            self.assertEqual(found.direction, Direction.SELL)

    def test_bullish_correction_cannot_be_scored_as_sell_pullback(self) -> None:
        indicators, structure = self._correction(Direction.BUY)
        rules = SignalEngine.assess_rules(indicators, structure, None)
        self.assertFalse(any("Pullback na EMA 21 com rejeição vendedora" in reason
                             for reason in rules.sell_reasons))

    def test_bearish_correction_cannot_be_scored_as_buy_pullback(self) -> None:
        indicators, structure = self._correction(Direction.SELL)
        rules = SignalEngine.assess_rules(indicators, structure, None)
        self.assertFalse(any("Pullback na EMA 21 com rejeição compradora" in reason
                             for reason in rules.buy_reasons))

    def test_bullish_context_distinguishes_sell_correction_from_buy_resumption(self) -> None:
        indicators, structure = self._correction(Direction.BUY)
        context = assess_pullback_context(indicators, structure, timeframe_policy("1m"))
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.primary_direction, Direction.BUY)
        self.assertEqual(context.correction_direction, Direction.SELL)
        self.assertFalse(context.resumed)
        self.assertIn("CORREÇÃO", context.phase)

    def test_bearish_context_distinguishes_buy_correction_from_sell_resumption(self) -> None:
        indicators, structure = self._correction(Direction.SELL)
        context = assess_pullback_context(indicators, structure, timeframe_policy("1m"))
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.primary_direction, Direction.SELL)
        self.assertEqual(context.correction_direction, Direction.BUY)
        self.assertFalse(context.resumed)

    def test_confirmed_bullish_resumption_preserves_buy_direction(self) -> None:
        indicators, structure = _pullback_frame(Direction.BUY)
        context = assess_pullback_context(indicators, structure, timeframe_policy("1m"))
        assert context is not None
        self.assertTrue(context.resumed)
        self.assertEqual(context.primary_direction, Direction.BUY)
        self.assertIn("RETOMADA", context.phase)

    def test_confirmed_bearish_resumption_preserves_sell_direction(self) -> None:
        indicators, structure = _pullback_frame(Direction.SELL)
        context = assess_pullback_context(indicators, structure, timeframe_policy("1m"))
        assert context is not None
        self.assertTrue(context.resumed)
        self.assertEqual(context.primary_direction, Direction.SELL)

    def test_real_bearish_choch_is_not_mislabeled_as_temporary_correction(self) -> None:
        indicators, structure = self._correction(Direction.BUY)
        event = StructureEvent("CHOCH", Direction.SELL, 100.0, 0.40, True)
        context = assess_pullback_context(indicators, structure, timeframe_policy("1m"), event)
        assert context is not None
        self.assertTrue(context.invalidated)
        self.assertIn("REVERSÃO ESTRUTURAL", context.phase)

    def test_loss_of_ema50_invalidates_old_bullish_trend(self) -> None:
        indicators, structure = self._correction(Direction.BUY)
        last = indicators.index[-1]
        indicators.at[last, "close"] = (
            float(indicators.at[last, "ema_50"]) - float(indicators.at[last, "atr_14"]) * 0.50
        )
        context = assess_pullback_context(indicators, structure, timeframe_policy("1m"))
        assert context is not None
        self.assertTrue(context.invalidated)

    def test_engine_rejects_sell_that_only_describes_bullish_correction(self) -> None:
        indicators, structure = self._correction(Direction.BUY)
        assessment = assess_professional_market(indicators, structure, None, "1m")
        self.assertIsNotNone(assessment.pullback_context)
        rules = RuleAssessment(18, 90, ["Estrutura de alta"], [
            "EMA 9 abaixo da EMA 21", "Momentum vendedor", "Volume vendedor",
            "Vela vendedora", "RSI vendedor", "ADX vendedor",
        ], professional=assessment)
        columns = ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume"]
        frame = indicators[columns]
        features = build_features(frame, Market.CRYPTO.value, "BTC/USDT")
        context = {
            "market": Market.CRYPTO.value, "symbol": "BTC/USDT", "timeframe": "1m",
            "horizon_minutes": 1, "sensitivity": "RÁPIDO", "mode": "CONFIRMAÇÃO",
            "strategy": strategy_key(Market.CRYPTO.value), "feature_schema": FEATURE_SCHEMA_VERSION,
        }
        with tempfile.TemporaryDirectory() as temporary, patch(
            "prime_ai_trader.signals.engine.assess_professional_market", return_value=assessment,
        ), patch.object(SignalEngine, "assess_rules", return_value=rules):
            signal = SignalEngine(ModelManager(Path(temporary))).generate(
                indicators, features, structure, None, 1, "RÁPIDO", True,
                mode="CONFIRMAÇÃO", model_context=context, payout_percent=82,
            )
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertTrue(any("Pullback invertido" in reason for reason in signal.waiting_reasons))
        self.assertEqual(signal.pullback_primary_direction, "COMPRA")
        self.assertEqual(signal.pullback_correction_direction, "VENDA")
        self.assertEqual(signal.sell_rule_points, 90)


class PullbackTrainingAndBacktestTests(unittest.TestCase):
    @staticmethod
    def _row(**changes) -> pd.Series:
        values = {
            "adx_14": 26.0, "atr_regime": 1.0, "ema21_distance_atr": 0.3,
            "trend_efficiency": 0.5, "compression_ratio": 1.0,
            "breakout_strength_atr": 0.0, "reversal_pressure": 0.0,
            "candlestick_reversal": 0.0, "candlestick_bias": 0.0,
            "candlestick_indecision": 0.0, "candlestick_exhaustion": 0.0,
            "micro_trend_atr": 0.0, "momentum_turn_score": 0.0,
            "close_position": 0.5, "taker_buy_valid": 0.0,
            "ema_distance_9_21": 1.0, "ema_distance_21_50": 1.0,
            "macd_hist": 1.0, "plus_di": 30.0, "minus_di": 12.0,
            "trend_code": 1.0, "primary_trend_code": 1.0,
            "pullback_correction_code": 0.0, "pullback_resumption_score": 0.5,
        }
        values.update(changes)
        return pd.Series(values)

    def test_schema_separates_old_models_from_corrected_pullback_features(self) -> None:
        self.assertGreaterEqual(FEATURE_SCHEMA_VERSION, 9)
        self.assertTrue({
            "primary_trend_code", "pullback_correction_code", "pullback_resumption_score",
        }.issubset(FEATURE_COLUMNS))
        self.assertIn("pullback-v10", strategy_key(Market.CRYPTO.value))
        self.assertIn("pullback-v10", strategy_key(Market.FOREX.value))

    def test_backtest_rejects_sell_that_is_only_bullish_correction(self) -> None:
        row = self._row(
            trend_efficiency=-0.1, primary_trend_code=1.0,
            pullback_correction_code=-1.0, pullback_resumption_score=-0.3,
            ema_distance_9_21=-1.0, macd_hist=-1.0, plus_di=12.0, minus_di=30.0,
        )
        self.assertFalse(_directional_confluence(row, -1, "RÁPIDO"))

    def test_backtest_rejects_buy_that_is_only_bearish_correction(self) -> None:
        row = self._row(
            trend_efficiency=0.1, primary_trend_code=-1.0,
            pullback_correction_code=1.0, pullback_resumption_score=-0.3,
            ema_distance_21_50=-1.0, trend_code=-1.0,
        )
        self.assertFalse(_directional_confluence(row, 1, "RÁPIDO"))

    def test_confirmed_breakout_can_override_old_macro_pullback_bias(self) -> None:
        row = self._row(
            trend_efficiency=-0.1, primary_trend_code=1.0,
            pullback_correction_code=-1.0, pullback_resumption_score=0.6,
            breakout_strength_atr=-0.4, ema_distance_9_21=-1.0,
            macd_hist=-1.0, plus_di=12.0, minus_di=30.0,
        )
        self.assertTrue(_directional_confluence(row, -1, "RÁPIDO"))


if __name__ == "__main__":
    unittest.main()
