from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from prime_ai_trader.core.models import Direction, Signal, SignalState
from prime_ai_trader.database.repository import Repository


class FinancialMetricTests(unittest.TestCase):
    @staticmethod
    def _signal() -> Signal:
        return Signal(
            Direction.BUY, SignalState.CONFIRMED, 80, {"COMPRA": 0.7},
            100.0, 1, payout_percent=74,
        )

    def test_fixed_payout_example_has_correct_financial_profit_factor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Repository(Path(temporary) / "finance.db")
            ids = [repository.save_signal(
                self._signal(), "Criptomoedas", "XRP/USDT", "1m", {}, "CONFIRMAÇÃO",
                platform="VEX", strategy="crypto-structure-volume-v3",
                sensitivity="RÁPIDO", stake_amount=80,
            ) for _ in range(10)]
            for signal_id in ids[:7]:
                repository.record_manual_result(signal_id, "WIN", payout_percent=74, stake_amount=80)
            for signal_id in ids[7:]:
                repository.record_manual_result(signal_id, "LOSS", payout_percent=74, stake_amount=80)
            stats = repository.statistics(result_source="MANUAL")
        self.assertEqual((stats["wins"], stats["losses"]), (7, 3))
        self.assertAlmostEqual(stats["gross_profit"], 414.40, places=2)
        self.assertAlmostEqual(stats["gross_loss"], 240.00, places=2)
        self.assertAlmostEqual(stats["net_profit"], 174.40, places=2)
        self.assertAlmostEqual(stats["profit_factor"], 1.7266666667, places=6)
        self.assertAlmostEqual(stats["break_even_rate"], 1 / 1.74, places=8)

    def test_manual_result_replaces_inferred_result_without_mixing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Repository(Path(temporary) / "source.db")
            signal_id = repository.save_signal(self._signal(), "Forex", "EUR/USD", "1m", {}, "CONFIRMAÇÃO")
            repository.set_result(signal_id, 101.0, "WIN", result_source="INFERRED")
            repository.record_manual_result(signal_id, "LOSS", payout_percent=74, stake_amount=80)
            stats = repository.statistics()
        self.assertEqual(stats["manual_results"], 1)
        self.assertEqual(stats["inferred_results"], 0)
        self.assertEqual(stats["net_profit"], -80)

    def test_existing_version_090_database_is_migrated_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.db"
            # sqlite3.Connection.__exit__ commits, but it does not close the
            # native handle.  Windows therefore keeps the temporary database
            # locked unless the connection is closed explicitly.
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    connection.execute("""CREATE TABLE signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                        market TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                        horizon_minutes INTEGER NOT NULL, direction TEXT NOT NULL, state TEXT NOT NULL,
                        score INTEGER NOT NULL, entry REAL, exit REAL, result TEXT,
                        probabilities_json TEXT NOT NULL, indicators_json TEXT NOT NULL,
                        confluences_json TEXT NOT NULL, model_version TEXT NOT NULL, mode TEXT NOT NULL)""")
                    connection.execute("""INSERT INTO signals(created_at, market, symbol, timeframe,
                        horizon_minutes, direction, state, score, entry, exit, result,
                        probabilities_json, indicators_json, confluences_json, model_version, mode)
                        VALUES ('2026-08-20T10:00:00+00:00','Criptomoedas','BTC/USDT','1m',1,
                        'COMPRA','SINAL CONFIRMADO',80,100,101,'WIN','{}','{}','[]','rules','CONFIRMAÇÃO')""")
            repository = Repository(path)
            row = repository.recent(1)[0]
        self.assertEqual(row["symbol"], "BTC/USDT")
        self.assertEqual(row["platform"], "MANUAL")
        self.assertEqual(row["result_source"], "INFERRED")
        self.assertAlmostEqual(row["profit_loss"], 0.8)
        self.assertIn("technical_stop", row)
        self.assertIn("technical_target", row)

    def test_technical_levels_are_persisted_with_the_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Repository(Path(temporary) / "levels.db")
            signal = self._signal()
            signal.technical_stop = 99.25
            signal.technical_target = 100.85
            signal.technical_room_ratio = 1.13
            repository.save_signal(
                signal, "Criptomoedas", "XRP/USDT", "1m", {}, "CONFIRMAÇÃO",
            )
            row = repository.recent(1)[0]
        self.assertAlmostEqual(row["technical_stop"], 99.25)
        self.assertAlmostEqual(row["technical_target"], 100.85)
        self.assertAlmostEqual(row["technical_room_ratio"], 1.13)


if __name__ == "__main__":
    unittest.main()
