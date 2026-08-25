from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from prime_ai_trader.app.controller import TradingController
from prime_ai_trader.backtest.engine import _directional_confluence
from prime_ai_trader.core.models import Direction, Market, Signal, SignalState
from prime_ai_trader.features.builder import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.platform.vex import VexPlatformSnapshot
from prime_ai_trader.priceaction.professional import PullbackSignal, assess_professional_market
from prime_ai_trader.priceaction.structure import MarketStructure, analyze_structure
from prime_ai_trader.signals.engine import SignalEngine
from prime_ai_trader.signals.reversal import assess_entry_reversal
from prime_ai_trader.signals.timing import preserve_recent_confirmed_signal
from prime_ai_trader.strategies.context import strategy_key
from tests.helpers import synthetic_candles


class ReversalRiskRegressionTests(unittest.TestCase):
    @staticmethod
    def _turn(direction: Direction, *, taker_buy: float = 25.0):
        buy = direction == Direction.BUY
        closes = np.array([101.20, 101.05, 100.80, 100.52])
        if not buy:
            closes = 202.0 - closes
        index = pd.date_range("2026-08-25 12:00", periods=4, freq="1min", tz="UTC")
        rows = pd.DataFrame({
            "open": closes + (0.10 if buy else -0.10),
            "high": closes + 0.45,
            "low": closes - 0.45,
            "close": closes,
            "atr_14": 1.0,
            "ema_9": [101.15, 101.04, 100.93, 100.82] if buy
                     else [100.85, 100.96, 101.07, 101.18],
            "macd_hist": [0.30, 0.26, 0.21, 0.15] if buy
                         else [-0.30, -0.26, -0.21, -0.15],
            "rsi_14": [64.0, 61.0, 58.0, 54.0] if buy
                      else [36.0, 39.0, 42.0, 46.0],
            "close_position": 0.35 if buy else 0.65,
            "upper_wick": 0.38 if buy else 0.08,
            "lower_wick": 0.08 if buy else 0.38,
            "volume": 100.0,
            "volume_relative": 1.20,
            "taker_buy_volume": taker_buy if buy else 100.0 - taker_buy,
        }, index=index)
        feature = pd.DataFrame({
            "rsi_slope": [-7.0 if buy else 7.0],
            "reversal_pressure": [-0.38 if buy else 0.38],
        }, index=index[-1:])
        return rows, feature

    def test_buy_with_multiple_independent_reversal_signs_is_rejected(self) -> None:
        rows, features = self._turn(Direction.BUY)
        risk = assess_entry_reversal(
            rows, features, Direction.BUY, market=Market.CRYPTO.value,
            timeframe="1m", horizon_minutes=1, candle_closed=True,
        )
        self.assertGreaterEqual(risk.votes, 4)
        self.assertTrue(risk.blocks("RÁPIDO"))
        self.assertTrue(any("Fluxo real" in item for item in risk.reasons))

    def test_sell_reversal_filter_is_symmetric(self) -> None:
        rows, features = self._turn(Direction.SELL)
        risk = assess_entry_reversal(
            rows, features, Direction.SELL, market=Market.CRYPTO.value,
            timeframe="1m", horizon_minutes=1, candle_closed=True,
        )
        self.assertGreaterEqual(risk.votes, 4)
        self.assertTrue(risk.blocks("EQUILIBRADO"))

    def test_open_candle_never_becomes_confirmed_reversal_evidence(self) -> None:
        rows, features = self._turn(Direction.BUY)
        risk = assess_entry_reversal(
            rows, features, Direction.BUY, market=Market.CRYPTO.value,
            timeframe="1m", horizon_minutes=1, candle_closed=False,
        )
        self.assertEqual(risk.votes, 0)

    def test_forex_and_missing_taker_never_invent_binance_aggression(self) -> None:
        rows, features = self._turn(Direction.BUY)
        forex = assess_entry_reversal(
            rows, features, Direction.BUY, market=Market.FOREX.value,
            timeframe="1m", horizon_minutes=1, candle_closed=True,
        )
        rows.loc[rows.index[-1], "taker_buy_volume"] = 0.0
        missing = assess_entry_reversal(
            rows, features, Direction.BUY, market=Market.CRYPTO.value,
            timeframe="1m", horizon_minutes=1, candle_closed=True,
        )
        self.assertFalse(any("Fluxo real" in item for item in forex.reasons))
        self.assertFalse(any("Fluxo real" in item for item in missing.reasons))

    def test_backtest_rejects_same_microtrend_and_momentum_conflict(self) -> None:
        row = pd.Series({
            "adx_14": 25.0, "atr_regime": 1.0,
            "ema_distance_9_21": 1.0, "ema_distance_21_50": 1.0,
            "macd_hist": 0.2, "plus_di": 30.0, "minus_di": 15.0,
            "trend_code": 1.0, "micro_trend_atr": -0.60,
            "momentum_turn_score": -0.52, "close_position": 0.54,
        })
        self.assertFalse(_directional_confluence(row, 1, "RÁPIDO"))

    def test_schema_exposes_causal_microtrend_and_validated_orderflow(self) -> None:
        self.assertGreaterEqual(FEATURE_SCHEMA_VERSION, 8)
        self.assertTrue({
            "micro_trend_atr", "momentum_turn_score", "ema9_distance_atr",
            "taker_buy_valid", "orderflow_imbalance",
        }.issubset(FEATURE_COLUMNS))
        frame = candles_frame(synthetic_candles(180, seed=3))
        frame.loc[frame.index[-1], "taker_buy_volume"] = 0.0
        crypto = build_features(frame, Market.CRYPTO.value, "BTC/USDT")
        forex = build_features(frame, Market.FOREX.value, "EUR/USD")
        self.assertEqual(float(crypto["taker_buy_valid"].iloc[-1]), 0.0)
        self.assertEqual(float(crypto["orderflow_imbalance"].iloc[-1]), 0.0)
        self.assertEqual(float(forex["orderflow_imbalance"].iloc[-1]), 0.0)

    def test_absent_taker_volume_does_not_create_fake_hundred_percent_seller(self) -> None:
        frame = candles_frame(synthetic_candles(220, seed=3))
        frame["taker_buy_volume"] = 0.0
        indicators = calculate_all(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        rules = SignalEngine.assess_rules(
            indicators, structure, None, market=Market.CRYPTO.value, symbol="BTC/USDT",
        )
        self.assertFalse(any("Força vendedora real da Binance" in item for item in rules.sell_reasons))


class PullbackConfirmationRegressionTests(unittest.TestCase):
    def _inputs(self):
        frame = candles_frame(synthetic_candles(260, seed=4))
        indicators = calculate_all(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        return frame, indicators, structure

    @staticmethod
    def _false_pullback() -> PullbackSignal:
        return PullbackSignal(
            Direction.BUY, 0.52, 0.8, "EMA 21", False, False,
            ("Retração saudável de 52% após impulso", "Momentum volta a favorecer a direção principal"),
        )

    def test_unconfirmed_pullback_is_not_counted_as_positive_confluence(self) -> None:
        _, indicators, structure = self._inputs()
        with patch("prime_ai_trader.priceaction.professional.detect_pullback",
                   return_value=self._false_pullback()):
            assessment = assess_professional_market(indicators, structure, None, "1m")
        self.assertFalse(any("PULLBACK COMPRADOR" in reason for reason in assessment.buy_reasons))
        self.assertTrue(any("não foi confirmada" in reason for reason in assessment.buy_penalties))

    def test_fast_confirmation_no_longer_accepts_unconfirmed_one_minute_pullback(self) -> None:
        frame, indicators, structure = self._inputs()
        base = assess_professional_market(indicators, structure, None, "1m")
        assessment = replace(
            base, pullback=self._false_pullback(),
            buy_penalties=("Pullback identificado, mas a retomada ainda não foi confirmada",),
        )
        context = {
            "market": Market.CRYPTO.value, "symbol": "BTC/USDT", "timeframe": "1m",
            "horizon_minutes": 1, "strategy": strategy_key(Market.CRYPTO.value),
            "sensitivity": "RÁPIDO", "mode": "CONFIRMAÇÃO",
            "feature_schema": FEATURE_SCHEMA_VERSION,
        }
        with tempfile.TemporaryDirectory() as directory, patch(
            "prime_ai_trader.signals.engine.assess_professional_market", return_value=assessment,
        ):
            result = SignalEngine(ModelManager(Path(directory))).generate(
                indicators, build_features(frame, Market.CRYPTO.value, "BTC/USDT"),
                structure, automatic_fibonacci(frame), 1, "RÁPIDO", True,
                mode="CONFIRMAÇÃO", model_context=context, payout_percent=82,
            )
        self.assertEqual(result.direction, Direction.WAIT)
        self.assertTrue(any("Pullback sem retomada confirmada" in item
                            for item in result.waiting_reasons))


class LiveEntryTimingRegressionTests(unittest.TestCase):
    @staticmethod
    def _signal(direction: Direction = Direction.BUY, **changes) -> Signal:
        return Signal(
            direction, SignalState.CONFIRMED, 84, {direction.value: 0.7},
            100.0, 1, created_at=datetime.now(timezone.utc) - timedelta(seconds=2),
            **changes,
        )

    @staticmethod
    def _preserved(signal: Signal, **changes) -> bool:
        return preserve_recent_confirmed_signal(
            signal, candle_closed=False, timeframe="1m", horizon_minutes=1,
            sensitivity="RÁPIDO", mode="CONFIRMAÇÃO", **changes,
        )

    def test_buy_is_invalidated_when_new_quote_turns_down(self) -> None:
        self.assertFalse(self._preserved(self._signal(), current_price=99.75, atr_value=1.0))

    def test_sell_is_invalidated_when_new_quote_turns_up(self) -> None:
        self.assertFalse(self._preserved(
            self._signal(Direction.SELL), current_price=100.25, atr_value=1.0,
        ))

    def test_small_normal_tick_still_keeps_confirmed_signal_visible(self) -> None:
        self.assertTrue(self._preserved(self._signal(), current_price=99.96, atr_value=1.0))

    def test_technical_invalidation_cancels_signal_even_before_visibility_window(self) -> None:
        signal = self._signal(technical_stop=99.97)
        self.assertFalse(self._preserved(signal, current_price=99.96, atr_value=1.0))

    def test_platform_last_seconds_do_not_keep_stale_confirmed_signal(self) -> None:
        self.assertFalse(self._preserved(self._signal(), platform_remaining_seconds=5))

    def test_platform_countdown_with_enough_time_remains_eligible(self) -> None:
        self.assertTrue(self._preserved(self._signal(), platform_remaining_seconds=43))

    def test_platform_refuses_entry_in_last_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"XDG_DATA_HOME": directory},
        ):
            controller = TradingController()
            controller.settings.platform_sync_enabled = True
            controller.platform_snapshot = VexPlatformSnapshot(
                datetime.now(timezone.utc), "https://vexinvest.com/traderoom", True,
                "BTC/USDT", Market.CRYPTO.value, 82, 5, 1, 100.0, False,
            )
            result = controller._apply_platform_alignment(
                self._signal(), Market.CRYPTO.value, "BTC/USDT", 100.0,
            )
        self.assertEqual(result.direction, Direction.WAIT)
        self.assertTrue(any("entrada tardia" in item for item in result.waiting_reasons))

    def test_platform_with_full_window_keeps_confirmed_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"XDG_DATA_HOME": directory},
        ):
            controller = TradingController()
            controller.settings.platform_sync_enabled = True
            controller.platform_snapshot = VexPlatformSnapshot(
                datetime.now(timezone.utc), "https://vexinvest.com/traderoom", True,
                "BTC/USDT", Market.CRYPTO.value, 82, 43, 1, 100.0, False,
            )
            result = controller._apply_platform_alignment(
                self._signal(), Market.CRYPTO.value, "BTC/USDT", 100.0,
            )
        self.assertEqual(result.direction, Direction.BUY)


if __name__ == "__main__":
    unittest.main()
