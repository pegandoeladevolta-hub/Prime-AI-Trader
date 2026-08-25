from __future__ import annotations

import unittest
from collections import Counter
from types import SimpleNamespace

from prime_ai_trader.core.models import Direction, Market
from prime_ai_trader.features.builder import FEATURE_SCHEMA_VERSION, build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.priceaction.structure import analyze_structure
from prime_ai_trader.signals.engine import SignalEngine
from tests.helpers import synthetic_candles


class _CoverageModel:
    report = SimpleNamespace(version="coverage-matrix")

    def __init__(self, ready: bool) -> None:
        self.ready = ready

    def is_compatible(self, _context) -> bool:
        return self.ready

    @staticmethod
    def predict_proba(rows) -> dict[int, float]:
        row = rows.iloc[-1]
        sign = float(row.get("trend_code", 0) or row.get("ema_distance_9_21", 0) or 1)
        return {
            1: 0.72 if sign >= 0 else 0.12,
            -1: 0.72 if sign < 0 else 0.12,
            0: 0.16,
        }


class DecisionPolicyCoverageTests(unittest.TestCase):
    def test_all_nine_combinations_keep_nonzero_progressive_coverage(self) -> None:
        counts: Counter[tuple[str, str]] = Counter()
        modes = ("PRICE ACTION", "CONFIRMAÇÃO", "QUANTITATIVO")
        sensitivities = ("RÁPIDO", "EQUILIBRADO", "CONSERVADOR")
        for seed in range(1, 21):
            frame = candles_frame(synthetic_candles(260, seed=seed))
            indicators = calculate_all(frame)
            features = build_features(frame, Market.CRYPTO.value, "BTC/USDT")
            structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
            fib = automatic_fibonacci(indicators)
            for mode in modes:
                for sensitivity in sensitivities:
                    context = {
                        "market": Market.CRYPTO.value,
                        "symbol": "BTC/USDT",
                        "timeframe": "1m",
                        "horizon_minutes": 1,
                        "strategy": "coverage-matrix",
                        "sensitivity": sensitivity,
                        "mode": mode,
                        "feature_schema": FEATURE_SCHEMA_VERSION,
                    }
                    signal = SignalEngine(_CoverageModel(mode == "QUANTITATIVO")).generate(
                        indicators, features, structure, fib, 1, sensitivity, True,
                        mode=mode, model_context=context, payout_percent=82,
                    )
                    counts[(mode, sensitivity)] += signal.direction != Direction.WAIT

        for mode in modes:
            with self.subTest(mode=mode):
                fast = counts[(mode, "RÁPIDO")]
                balanced = counts[(mode, "EQUILIBRADO")]
                conservative = counts[(mode, "CONSERVADOR")]
                self.assertGreaterEqual(conservative, 2)
                self.assertGreaterEqual(balanced, conservative)
                self.assertGreaterEqual(fast, balanced)
                self.assertGreaterEqual(fast, 10)


if __name__ == "__main__":
    unittest.main()
