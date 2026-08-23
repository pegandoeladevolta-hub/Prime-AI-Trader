from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from prime_ai_trader.core.models import Direction, Market, SignalState
from prime_ai_trader.features.builder import build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.priceaction.professional import detect_pullback, timeframe_policy
from prime_ai_trader.priceaction.structure import MarketStructure, analyze_structure
from prime_ai_trader.signals.engine import SignalEngine
from prime_ai_trader.strategies.context import forex_sessions, strategy_key
from tests.helpers import synthetic_candles


class MarketSpecificStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = candles_frame(synthetic_candles(220, seed=17))
        self.indicators = calculate_all(self.frame)
        self.structure = analyze_structure(self.indicators, float(self.indicators["atr_14"].iloc[-1]))

    def test_crypto_features_keep_real_volume_and_buyer_strength(self) -> None:
        features = build_features(self.frame, Market.CRYPTO.value, "BTC/USDT")
        self.assertEqual(features["crypto_market"].iloc[-1], 1.0)
        self.assertEqual(features["volume_valid"].iloc[-1], 1.0)
        expected = self.frame["taker_buy_volume"].iloc[-1] / self.frame["volume"].iloc[-1]
        self.assertAlmostEqual(features["taker_buy_ratio"].iloc[-1], expected)

    def test_forex_never_invents_centralized_volume_or_vwap(self) -> None:
        fake_forex = self.frame.copy()
        fake_forex["volume"] = 999_999.0
        features = build_features(fake_forex, Market.FOREX.value, "EUR/USD")
        for column in ("volume_valid", "volume_relative", "volume_impulse", "vwap_distance", "obv_change", "taker_buy_ratio"):
            self.assertEqual(float(features[column].iloc[-1]), 0.0, column)
        rules = SignalEngine.assess_rules(
            calculate_all(fake_forex), self.structure, None, market=Market.FOREX.value,
            symbol="EUR/USD",
        )
        reasons = " ".join((*rules.buy_reasons, *rules.sell_reasons))
        self.assertNotIn("Volume comprador", reasons)
        self.assertNotIn("Volume vendedor", reasons)
        self.assertNotIn("VWAP", reasons)

    def test_forex_sessions_use_dst_aware_iana_timezones(self) -> None:
        summer = datetime(2025, 6, 2, 7, 30, tzinfo=timezone.utc)
        self.assertIn("LONDRES", forex_sessions(summer))
        self.assertIn("NOVA YORK", forex_sessions(datetime(2025, 6, 2, 12, 30, tzinfo=timezone.utc)))
        self.assertIn("TÓQUIO", forex_sessions(datetime(2025, 6, 2, 0, 30, tzinfo=timezone.utc)))

    def test_strategy_identifiers_are_separate_by_market(self) -> None:
        self.assertNotEqual(strategy_key(Market.CRYPTO.value), strategy_key(Market.FOREX.value))

    def test_delayed_one_minute_source_cannot_confirm_signal(self) -> None:
        features = build_features(self.frame, Market.CRYPTO.value, "BTC/USDT")
        with tempfile.TemporaryDirectory() as temporary:
            engine = SignalEngine(ModelManager(Path(temporary)))
            signal = engine.generate(
                self.indicators, features, self.structure, automatic_fibonacci(self.frame),
                1, "RÁPIDO", True, mode="CONFIRMAÇÃO",
                model_context={"market": Market.CRYPTO.value, "symbol": "BTC/USDT",
                               "timeframe": "1m", "horizon_minutes": 1,
                               "strategy": strategy_key(Market.CRYPTO.value),
                               "sensitivity": "RÁPIDO", "mode": "CONFIRMAÇÃO",
                               "feature_schema": 6},
                source_lag_seconds=200,
            )
        self.assertNotEqual(signal.state, SignalState.CONFIRMED)
        self.assertTrue(any("Fonte atrasada" in reason for reason in signal.waiting_reasons))

    def test_one_minute_false_pullback_without_rejection_is_not_confirmed(self) -> None:
        closes = np.r_[np.linspace(92.0, 110.0, 70), [109.2, 108.8, 108.4, 108.0, 107.6, 107.3, 108.5]]
        opens = np.r_[closes[0] - 0.1, closes[:-1]]
        index = pd.date_range("2025-01-01", periods=len(closes), freq="1min", tz="UTC")
        raw = pd.DataFrame({
            "open": opens, "high": np.maximum(opens, closes) + 0.28,
            "low": np.minimum(opens, closes) - 0.28, "close": closes,
            "volume": 400.0, "quote_volume": 40_000.0, "taker_buy_volume": 210.0,
        }, index=index)
        indicators = calculate_all(raw)
        indicators.loc[indicators.index[-1], ["lower_wick", "upper_wick"]] = (0.0, 0.0)
        structure = MarketStructure("ALTA", [], None, False, False, [], [], [], [])
        result = detect_pullback(indicators, structure, None, timeframe_policy("1m"))
        self.assertIsNotNone(result)
        self.assertFalse(result.confirmed)


if __name__ == "__main__":
    unittest.main()
