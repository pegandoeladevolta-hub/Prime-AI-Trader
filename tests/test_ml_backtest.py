from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prime_ai_trader.backtest.engine import BacktestEngine
from prime_ai_trader.features.builder import build_features, build_labels
from prime_ai_trader.indicators.technical import candles_frame
from prime_ai_trader.ml.models import ModelManager, temporal_folds
from tests.helpers import synthetic_candles


class MlBacktestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame = candles_frame(synthetic_candles(460, seed=12))
        cls.features = build_features(cls.frame)
        cls.labels = build_labels(cls.frame["close"], 2, 0.001)

    def test_temporal_folds_never_overlap_future(self) -> None:
        folds = temporal_folds(500, min_train=200, test_size=50)
        self.assertGreater(len(folds), 1)
        for train, test in folds:
            self.assertLess(train.max(), test.min())

    def test_training_and_probability_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manager = ModelManager(Path(temp))
            report = manager.train(self.features, self.labels)
            self.assertTrue(manager.trained)
            self.assertGreater(report.samples, 100)
            probabilities = manager.predict_proba(self.features)
            self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=6)
            self.assertTrue(set(probabilities).issubset({-1, 0, 1}))

    def test_backtest_reports_only_oos_predictions(self) -> None:
        result = BacktestEngine().run(self.features, self.labels, confidence_threshold=0.0)
        self.assertGreater(result.test_samples, 0)
        self.assertEqual(len(result.confusion), 3)
        self.assertLessEqual(result.operations, result.validation_samples + result.test_samples)
        self.assertGreaterEqual(result.coverage, 0)
        self.assertLessEqual(result.coverage, 1)


if __name__ == "__main__":
    unittest.main()

