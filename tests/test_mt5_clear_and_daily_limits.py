from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.mt5_daily_limits import evaluate_daily_limits
from prime_ai_trader.platform.mt5_positions import MT5Bridge


class FakeJournal:
    def __init__(self, rows):
        self.rows = list(rows)

    def recent(self, limit=100000):
        return list(self.rows)[:limit]


class FakeMT5Module:
    def __init__(self):
        self.calls = []
        self._attempt = 0

    def shutdown(self):
        return None

    def initialize(self, **kwargs):
        self.calls.append(kwargs)
        self._attempt += 1
        return self._attempt >= 2

    def last_error(self):
        return (-6, "Terminal: Authorization failed") if self._attempt < 2 else (1, "Success")

    def account_info(self):
        if self._attempt < 2:
            return None
        return SimpleNamespace(
            login=123456, server="Clear-Real", name="Conta Teste", currency="BRL",
            balance=10000.0, equity=10000.0, margin=0.0, margin_free=10000.0,
            trade_allowed=True,
        )


class ClearTerminalTests(unittest.TestCase):
    def test_clear_terminal_has_priority_over_old_metaquotes_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clear = root / "Clear Investimentos MT5 Terminal" / "terminal64.exe"
            clear.parent.mkdir(parents=True)
            clear.write_bytes(b"")
            old = root / "MetaQuotes MetaTrader 5" / "terminal64.exe"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"")
            environment = {
                "ProgramW6432": str(root),
                "ProgramFiles": str(root),
                "ProgramFiles(x86)": str(root),
                "LOCALAPPDATA": str(root / "local"),
            }
            with patch.dict(os.environ, environment, clear=False), patch.object(
                MT5Bridge, "_registry_terminal_paths", return_value=[]
            ):
                found = MT5Bridge.discover_terminal_paths(old)
            self.assertTrue(found)
            self.assertEqual(found[0], clear)
            self.assertTrue(all("clear" in str(path).lower() for path in found))

    def test_authorization_minus_6_launches_same_clear_terminal_and_retries(self) -> None:
        bridge = MT5Bridge()
        fake = FakeMT5Module()
        bridge._mt5 = fake
        clear = Path(r"C:\Program Files\Clear Investimentos MT5 Terminal\terminal64.exe")
        with patch.object(bridge, "discover_terminal_paths", return_value=[clear]), patch.object(
            bridge, "_launch_terminal"
        ) as launcher, patch("prime_ai_trader.platform.mt5_positions.time.sleep", return_value=None):
            account = bridge.connect()
        self.assertEqual(account.server, "Clear-Real")
        self.assertEqual(account.currency, "BRL")
        self.assertEqual(bridge.terminal_path, str(clear))
        launcher.assert_called_once_with(clear)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[-1]["path"], str(clear))


class DailyLimitTests(unittest.TestCase):
    def test_profit_target_blocks_new_orders_after_closed_trade(self) -> None:
        now = datetime.now(timezone.utc)
        journal = FakeJournal([
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": 120.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": 90.0},
            {"status": "ABERTA", "closed_at": None, "net_profit": 500.0},
        ])
        status = evaluate_daily_limits(
            journal, profit_target=200.0, stop_loss=150.0, now=now
        )
        self.assertTrue(status.blocked)
        self.assertAlmostEqual(status.net_profit, 210.0)
        self.assertEqual(status.operations, 2)
        self.assertIn("META DIÁRIA ATINGIDA", status.reason)

    def test_daily_stop_blocks_after_realized_loss(self) -> None:
        now = datetime.now(timezone.utc)
        journal = FakeJournal([
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -80.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -50.0},
        ])
        status = evaluate_daily_limits(
            journal, profit_target=250.0, stop_loss=120.0, now=now
        )
        self.assertTrue(status.blocked)
        self.assertAlmostEqual(status.net_profit, -130.0)
        self.assertIn("STOP DIÁRIO ATINGIDO", status.reason)

    def test_previous_day_does_not_block_today(self) -> None:
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        journal = FakeJournal([
            {"status": "ENCERRADA", "closed_at": yesterday.isoformat(), "net_profit": 500.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": 40.0},
        ])
        status = evaluate_daily_limits(
            journal, profit_target=200.0, stop_loss=100.0, now=now
        )
        self.assertFalse(status.blocked)
        self.assertAlmostEqual(status.net_profit, 40.0)
        self.assertEqual(status.operations, 1)

    def test_manual_limit_change_can_release_same_day(self) -> None:
        now = datetime.now(timezone.utc)
        journal = FakeJournal([
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": 210.0},
        ])
        blocked = evaluate_daily_limits(
            journal, profit_target=200.0, stop_loss=120.0, now=now
        )
        released = evaluate_daily_limits(
            journal, profit_target=300.0, stop_loss=120.0, now=now
        )
        self.assertTrue(blocked.blocked)
        self.assertFalse(released.blocked)

    def test_two_consecutive_losses_pause_new_entries(self) -> None:
        now = datetime.now(timezone.utc)
        journal = FakeJournal([
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -35.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -20.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": 90.0},
        ])
        status = evaluate_daily_limits(
            journal, profit_target=200.0, stop_loss=200.0,
            max_consecutive_losses=2, now=now,
        )
        self.assertTrue(status.blocked)
        self.assertEqual(status.consecutive_losses, 2)
        self.assertIn("PAUSA POR LOSSES", status.reason)

    def test_win_breaks_consecutive_loss_streak(self) -> None:
        now = datetime.now(timezone.utc)
        journal = FakeJournal([
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -35.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": 10.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -20.0},
        ])
        status = evaluate_daily_limits(
            journal, profit_target=200.0, stop_loss=200.0,
            max_consecutive_losses=2, now=now,
        )
        self.assertFalse(status.blocked)
        self.assertEqual(status.consecutive_losses, 1)

    def test_zero_disables_consecutive_loss_pause(self) -> None:
        now = datetime.now(timezone.utc)
        journal = FakeJournal([
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -10.0},
            {"status": "ENCERRADA", "closed_at": now.isoformat(), "net_profit": -10.0},
        ])
        status = evaluate_daily_limits(
            journal, profit_target=0.0, stop_loss=0.0,
            max_consecutive_losses=0, now=now,
        )
        self.assertFalse(status.blocked)
        self.assertEqual(status.consecutive_losses, 2)


if __name__ == "__main__":
    unittest.main()
