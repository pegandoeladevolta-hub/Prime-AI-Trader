from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from prime_ai_trader.indicators.technical import (
    adx, atr, bollinger, calculate_all, candles_frame, cci, ema, macd, obv, rsi,
    stochastic, vwap, williams_r,
)
from tests.helpers import synthetic_candles


class IndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame = candles_frame(synthetic_candles(220))

    def test_ema_constant_series(self) -> None:
        values = ema(pd.Series([10.0] * 30), 9).dropna()
        self.assertTrue(np.allclose(values, 10.0))

    def test_rsi_uptrend_reaches_100(self) -> None:
        result = rsi(pd.Series(np.arange(1.0, 50.0))).iloc[-1]
        self.assertAlmostEqual(result, 100.0)

    def test_macd_has_positive_histogram_for_accelerating_uptrend(self) -> None:
        series = pd.Series(np.arange(1.0, 100.0) ** 1.3)
        line, signal, hist = macd(series)
        self.assertGreater(line.iloc[-1], 0)
        self.assertGreater(hist.iloc[-1], 0)
        self.assertFalse(pd.isna(signal.iloc[-1]))

    def test_bollinger_constant(self) -> None:
        mid, upper, lower = bollinger(pd.Series([50.0] * 30))
        self.assertEqual(mid.iloc[-1], 50.0)
        self.assertEqual(upper.iloc[-1], 50.0)
        self.assertEqual(lower.iloc[-1], 50.0)

    def test_atr_is_positive(self) -> None:
        self.assertGreater(atr(self.frame).dropna().iloc[-1], 0)

    def test_stochastic_bounded(self) -> None:
        k, d = stochastic(self.frame)
        self.assertTrue(k.dropna().between(0, 100).all())
        self.assertTrue(d.dropna().between(0, 100).all())

    def test_adx_and_directional_indexes_are_nonnegative(self) -> None:
        strength, plus, minus = adx(self.frame)
        self.assertTrue((strength.dropna() >= 0).all())
        self.assertTrue((plus.dropna() >= 0).all())
        self.assertTrue((minus.dropna() >= 0).all())

    def test_vwap_matches_manual_value(self) -> None:
        small = pd.DataFrame({"high": [11, 13], "low": [9, 9], "close": [10, 12], "volume": [2, 1]})
        expected = (((11 + 9 + 10) / 3) * 2 + ((13 + 9 + 12) / 3)) / 3
        self.assertAlmostEqual(vwap(small).iloc[-1], expected)

    def test_obv_direction(self) -> None:
        small = pd.DataFrame({"close": [10, 11, 10, 12], "volume": [5, 7, 3, 2]})
        self.assertEqual(obv(small).tolist(), [0, 7, 4, 6])

    def test_cci_and_williams_are_finite(self) -> None:
        self.assertTrue(np.isfinite(cci(self.frame).dropna().iloc[-1]))
        value = williams_r(self.frame).dropna().iloc[-1]
        self.assertGreaterEqual(value, -100)
        self.assertLessEqual(value, 0)

    def test_calculate_all_contract(self) -> None:
        result = calculate_all(self.frame)
        required = {"ema_9", "ema_21", "ema_50", "rsi_14", "macd", "bb_upper", "stoch_k", "adx_14", "atr_14", "vwap", "obv", "cci_20", "williams_r"}
        self.assertTrue(required.issubset(result.columns))


if __name__ == "__main__":
    unittest.main()

