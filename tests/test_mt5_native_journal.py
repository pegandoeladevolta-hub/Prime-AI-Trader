from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from prime_ai_trader.config.settings import AppSettings, SettingsStore
from prime_ai_trader.core.models import Direction, Signal, SignalState
from prime_ai_trader.database.mt5_journal import MT5TradeJournal


class FakeMT5Module:
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 3
    DEAL_REASON_SL = 4
    DEAL_REASON_TP = 5
    DEAL_REASON_CLIENT = 0


class FakeBridge:
    MAGIC = 260826

    def __init__(self) -> None:
        self.open_rows = []
        self.deals = []
        self.module = FakeMT5Module()

    def _module(self):
        return self.module

    def prime_positions(self):
        return list(self.open_rows)

    def history(self, days=30):
        return list(self.deals)


class MT5NativeJournalTests(unittest.TestCase):
    def _snapshot(self):
        signal = Signal(
            Direction.BUY, SignalState.CONFIRMED, 78,
            {"COMPRA": 0.7, "VENDA": 0.2, "AGUARDAR": 0.1},
            1.1000, 0,
            technical_stop=1.0980,
            technical_target=1.1030,
            technical_room_ratio=1.5,
        )
        return SimpleNamespace(signal=signal, symbol="EURUSD", timeframe="1m")

    def test_journal_records_mt5_fields_without_binary_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MT5TradeJournal(Path(tmp) / "journal.db")
            journal.record_open(
                self._snapshot(), volume=0.1, strategy="price-action",
                sensitivity="RÁPIDO", mode="PRICE ACTION", management="SCALP",
            )
            row = journal.active()[0]
            self.assertEqual(row["volume"], 0.1)
            self.assertEqual(row["stop_loss"], 1.0980)
            self.assertEqual(row["take_profit"], 1.1030)
            self.assertNotIn("payout_percent", row)
            self.assertNotIn("stake_amount", row)

    def test_sync_closes_trade_with_real_mt5_profit_and_tp_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = MT5TradeJournal(Path(tmp) / "journal.db")
            journal.record_open(
                self._snapshot(), volume=0.1, strategy="price-action",
                sensitivity="RÁPIDO", mode="PRICE ACTION", management="SCALP",
            )
            bridge = FakeBridge()
            now = datetime.now(timezone.utc).timestamp()
            bridge.open_rows = [{
                "ticket": 777, "symbol": "EURUSD", "type": 0, "volume": 0.1,
                "price_open": 1.1000, "sl": 1.0980, "tp": 1.1030,
                "time": now, "magic": bridge.MAGIC, "comment": "Prime Trader",
            }]
            context = dict(timeframe="1m", strategy="price-action", sensitivity="RÁPIDO",
                           mode="PRICE ACTION", management="SCALP")
            journal.sync_with_mt5(bridge, **context)
            self.assertEqual(journal.active()[0]["position_ticket"], 777)

            bridge.open_rows = []
            bridge.deals = [{
                "ticket": 900, "position_id": 777, "symbol": "EURUSD", "entry": 1,
                "time": now + 20, "price": 1.1030, "profit": 30.0,
                "commission": -1.0, "swap": 0.0, "fee": 0.0,
                "reason": FakeMT5Module.DEAL_REASON_TP,
                "magic": bridge.MAGIC, "comment": "Prime Trader",
            }]
            journal.sync_with_mt5(bridge, **context)
            row = journal.recent(1)[0]
            self.assertEqual(row["status"], "ENCERRADA")
            self.assertEqual(row["exit_reason"], "TAKE PROFIT")
            self.assertEqual(row["result"], "WIN")
            self.assertAlmostEqual(row["net_profit"], 29.0)

    def test_settings_file_does_not_persist_payout_or_stake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            SettingsStore(path).save(AppSettings())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("payout_percent", payload)
            self.assertNotIn("stake_amount", payload)
            self.assertNotIn("platform_auto_payout", payload)


if __name__ == "__main__":
    unittest.main()
