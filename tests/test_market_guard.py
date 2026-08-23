from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from prime_ai_trader.indicators.technical import calculate_all
from prime_ai_trader.signals.market_guard import POLICIES, evaluate_market_entry


def market_frame(direction: int = 1, *, volume: float = 1_000.0, periods: int = 90) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    changes = direction * 0.00045 + rng.normal(0, 0.00012, periods)
    close = 100 * np.cumprod(1 + changes)
    open_price = np.r_[close[0], close[:-1]]
    high = np.maximum(open_price, close) * 1.00035
    low = np.minimum(open_price, close) * 0.99965
    raw = pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=pd.date_range("2026-08-20 12:00", periods=periods, freq="min", tz="UTC"),
    )
    result = calculate_all(raw)
    result.loc[result.index[-1], "volume_relative"] = 1.0 if volume else 0.0
    return result


def decision(frame: pd.DataFrame, *, market="Criptomoedas", direction="COMPRA", **overrides):
    values = {
        "indicators": frame,
        "features": None,
        "direction": direction,
        "market": market,
        "sensitivity": "RÁPIDO",
        "mode": "CONFIRMAÇÃO",
        "candle_closed": True,
        "score": 80,
        "probabilities": {direction: 0.70, "AGUARDAR": 0.15},
        "payout_percent": 82,
    }
    values.update(overrides)
    return evaluate_market_entry(**values)


class MarketGuardTests(unittest.TestCase):
    def test_markets_have_distinct_policies(self):
        self.assertNotEqual(POLICIES["CRYPTO"], POLICIES["FOREX"])
        self.assertIsNotNone(POLICIES["CRYPTO"].minimum_volume_relative)
        self.assertIsNone(POLICIES["FOREX"].minimum_volume_relative)

    def test_confirmation_mode_never_uses_open_candle(self):
        result = decision(market_frame(), candle_closed=False)
        self.assertFalse(result.allowed)
        self.assertTrue(any("fechamento real" in reason for reason in result.reasons))

    def test_crypto_requires_real_relative_volume(self):
        result = decision(market_frame(volume=0.0))
        self.assertFalse(result.allowed)
        self.assertTrue(any("volume relativo" in reason for reason in result.reasons))

    def test_forex_does_not_reuse_crypto_volume_rule(self):
        frame = market_frame(volume=0.0)
        result = decision(frame, market="Forex")
        self.assertFalse(any("volume relativo" in reason for reason in result.reasons))

    def test_wick_dominated_sell_is_rejected(self):
        frame = market_frame(direction=-1)
        idx = frame.index[-1]
        close = float(frame.loc[idx, "close"])
        frame.loc[idx, "open"] = close * 1.00002
        frame.loc[idx, "high"] = close * 1.002
        frame.loc[idx, "low"] = close * 0.99998
        frame.loc[idx, "close_position"] = 0.99
        result = decision(frame, direction="VENDA")
        self.assertFalse(result.allowed)
        self.assertTrue(any("pavio" in reason for reason in result.reasons))

    def test_countertrend_pullback_is_not_called_reversal(self):
        frame = market_frame(direction=1)
        idx = frame.index[-1]
        frame.loc[idx, "open"] = frame.loc[idx, "close"] * 1.001
        result = decision(frame, direction="VENDA")
        self.assertFalse(result.allowed)
        self.assertTrue(any("pullback não é reversão" in reason for reason in result.reasons))

    def test_low_rapid_score_is_filtered_by_market(self):
        crypto = decision(market_frame(), score=63)
        forex = decision(market_frame(), market="Forex", score=65)
        self.assertFalse(crypto.allowed)
        self.assertFalse(forex.allowed)
        self.assertTrue(any("Score" in reason for reason in crypto.reasons))
        self.assertTrue(any("Score" in reason for reason in forex.reasons))


if __name__ == "__main__":
    unittest.main()
