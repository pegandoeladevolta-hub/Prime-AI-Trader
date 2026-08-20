from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prime_ai_trader.core.models import Direction, Signal, SignalState
from prime_ai_trader.database.repository import Repository
from prime_ai_trader.features.builder import build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.ml.models import ModelManager
from prime_ai_trader.priceaction.structure import analyze_structure
from prime_ai_trader.signals.engine import SignalEngine
from tests.helpers import synthetic_candles


class SignalDatabaseTests(unittest.TestCase):
    def test_blocker_forces_wait(self) -> None:
        frame = candles_frame(synthetic_candles(180))
        indicators = calculate_all(frame)
        features = build_features(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        with tempfile.TemporaryDirectory() as temp:
            engine = SignalEngine(ModelManager(Path(temp)))
            signal = engine.generate(indicators, features, structure, automatic_fibonacci(frame), 5, "RÁPIDO", True, ["Evento de alto impacto"])
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertEqual(signal.state, SignalState.BLOCKED)

    def test_unconfirmed_candle_cannot_be_confirmed_signal(self) -> None:
        frame = candles_frame(synthetic_candles(180, seed=4))
        indicators = calculate_all(frame)
        features = build_features(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        with tempfile.TemporaryDirectory() as temp:
            engine = SignalEngine(ModelManager(Path(temp)))
            signal = engine.generate(indicators, features, structure, automatic_fibonacci(frame), 5, "RÁPIDO", False)
        self.assertNotEqual(signal.state, SignalState.CONFIRMED)

    def test_database_roundtrip_and_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Repository(Path(temp) / "test.db")
            signal = Signal(Direction.BUY, SignalState.CONFIRMED, 72, {"COMPRA": 0.7}, 100.0, 5, ["teste"])
            ids = [repo.save_signal(signal, "Criptomoedas", "BTC/USDT", "5m", {"rsi": 55}, "CONFIRMAÇÃO") for _ in range(30)]
            for signal_id in ids:
                repo.set_result(signal_id, 101.0, "WIN")
            rate, samples = repo.calibration(72)
            self.assertEqual(samples, 30)
            self.assertEqual(rate, 1.0)
            stats = repo.statistics()
            self.assertEqual(stats["wins"], 30)
            self.assertIsNone(stats["profit_factor"])

    def test_calibration_respects_market_context_and_ignores_draws(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Repository(Path(temp) / "context.db")
            signal = Signal(Direction.BUY, SignalState.CONFIRMED, 72, {"COMPRA": 0.7}, 100.0, 5, ["teste"])
            btc_ids = [
                repo.save_signal(signal, "Criptomoedas", "BTC/USDT", "5m", {}, "CONFIRMAÇÃO")
                for _ in range(30)
            ]
            eth_ids = [
                repo.save_signal(signal, "Criptomoedas", "ETH/USDT", "5m", {}, "CONFIRMAÇÃO")
                for _ in range(30)
            ]
            draw_id = repo.save_signal(signal, "Criptomoedas", "BTC/USDT", "5m", {}, "CONFIRMAÇÃO")
            for signal_id in btc_ids:
                repo.set_result(signal_id, 101.0, "WIN")
            for signal_id in eth_ids:
                repo.set_result(signal_id, 99.0, "LOSS")
            repo.set_result(draw_id, 100.0, "DRAW")

            rate, samples = repo.calibration(
                72, market="Criptomoedas", symbol="BTC/USDT", timeframe="5m",
                horizon_minutes=5, mode="CONFIRMAÇÃO",
            )
            self.assertEqual((rate, samples), (1.0, 30))
            global_rate, global_samples = repo.calibration(72)
            self.assertEqual((global_rate, global_samples), (0.5, 60))
            stats = repo.statistics()
            self.assertEqual(stats["directional_total"], 60)
            self.assertEqual(stats["accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()

