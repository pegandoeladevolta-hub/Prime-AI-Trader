from __future__ import annotations

import unittest
import time

import numpy as np
import pandas as pd

from prime_ai_trader.features.builder import FEATURE_COLUMNS, build_features, build_labels, build_time_labels
from prime_ai_trader.fibonacci.auto import RATIOS, automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.priceaction.structure import analyze_structure, detect_pivots, support_resistance_zones
from tests.helpers import synthetic_candles


class StructureFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = candles_frame(synthetic_candles(240))

    def test_pivots_detect_local_extremes(self) -> None:
        frame = pd.DataFrame({"high": [1, 2, 5, 2, 1, 3, 2], "low": [0, 1, 2, 1, -2, 1, 0]})
        highs, lows = detect_pivots(frame, 1, 1)
        self.assertIn(2, highs)
        self.assertIn(4, lows)

    def test_support_resistance_is_limited_and_grouped(self) -> None:
        indicators = calculate_all(self.frame)
        supports, resistances = support_resistance_zones(indicators, float(indicators["atr_14"].iloc[-1]))
        self.assertLessEqual(len(supports), 4)
        self.assertLessEqual(len(resistances), 4)
        self.assertTrue(all(zone.low <= zone.high for zone in supports + resistances))

    def test_structure_contract(self) -> None:
        indicators = calculate_all(self.frame)
        result = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        self.assertIn(result.trend, {"ALTA", "BAIXA", "LATERAL", "INDEFINIDA"})
        self.assertTrue(set(result.sequence).issubset({"HH", "HL", "LH", "LL"}))

    def test_fibonacci_levels(self) -> None:
        result = automatic_fibonacci(self.frame)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(set(result.levels), set(RATIOS))
        self.assertIn(result.direction, {"IMPULSO DE ALTA", "IMPULSO DE BAIXA"})
        self.assertGreater(result.swing_high, result.swing_low)

    def test_features_have_stable_schema(self) -> None:
        result = build_features(self.frame)
        self.assertEqual(result.columns.tolist(), FEATURE_COLUMNS)
        self.assertEqual(len(result), len(self.frame))

    def test_feature_builder_stays_fast_on_large_history(self) -> None:
        frame = candles_frame(synthetic_candles(1000, seed=33))
        started = time.perf_counter()
        result = build_features(frame)
        self.assertEqual(len(result), 1000)
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_features_do_not_change_when_future_is_appended(self) -> None:
        first = build_features(self.frame.iloc[:180])
        longer = build_features(self.frame)
        common = first.iloc[80:170]
        other = longer.loc[common.index]
        np.testing.assert_allclose(common.to_numpy(), other.to_numpy(), equal_nan=True, rtol=1e-10, atol=1e-10)

    def test_labels_only_use_declared_horizon(self) -> None:
        labels = build_labels(self.frame["close"], 3, 0.001)
        self.assertTrue(labels.iloc[-3:].isna().all())
        current = self.frame["close"].iloc[10]
        future = self.frame["close"].iloc[13]
        expected = 1 if future / current - 1 > 0.001 else -1 if future / current - 1 < -0.001 else 0
        self.assertEqual(labels.iloc[10], expected)

    def test_time_labels_use_exact_minute_horizon(self) -> None:
        base = self.frame["close"]
        chart_index = self.frame.index[::3]
        labels = build_time_labels(chart_index, base, 5, 0.0)
        first = chart_index[4]
        current = base.loc[first]
        future = base.loc[first + pd.Timedelta(minutes=5)]
        self.assertEqual(labels.loc[first], 1 if future > current else -1 if future < current else 0)


if __name__ == "__main__":
    unittest.main()
