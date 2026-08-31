from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.mt5_credentials import (
    MT5CredentialPurgeError,
    purge_saved_mt5_credentials,
)
from prime_ai_trader.app.mt5_profiles import REAL, SIMULATOR
from prime_ai_trader.platform.mt5_dual import MT5Bridge


class MemorySecretStore:
    def __init__(self, values=None, *, discard_writes: bool = False):
        self.values = dict(values or {})
        self.discard_writes = discard_writes
        self.save_calls = 0

    def load(self):
        return dict(self.values)

    def save(self, values):
        self.save_calls += 1
        if not self.discard_writes:
            self.values = dict(values)


class LegacyCredentialPurgeTests(unittest.TestCase):
    def test_real_and_demo_credentials_are_removed_but_other_secrets_survive(self) -> None:
        memory = MemorySecretStore({
            "mt5_clear_real_login": "101",
            "mt5_clear_real_password": "senha-real",
            "mt5_clear_real_server": "ClearInvestimentos-CLEAR",
            "mt5_clear_simulator_login": "202",
            "mt5_clear_simulator_password": "senha-demo",
            "mt5_clear_simulator_server": "ClearInvestimentos-DEMO",
            "outro_segredo": "preservar",
        })
        self.assertTrue(purge_saved_mt5_credentials(memory))
        self.assertEqual(memory.values, {"outro_segredo": "preservar"})
        self.assertEqual(memory.save_calls, 1)

    def test_clean_store_is_not_rewritten(self) -> None:
        memory = MemorySecretStore({"outro_segredo": "preservar"})
        self.assertFalse(purge_saved_mt5_credentials(memory))
        self.assertEqual(memory.values, {"outro_segredo": "preservar"})
        self.assertEqual(memory.save_calls, 0)

    def test_failed_purge_is_reported_instead_of_claiming_removal(self) -> None:
        memory = MemorySecretStore(
            {"mt5_clear_simulator_password": "senha-demo"},
            discard_writes=True,
        )
        with self.assertRaises(MT5CredentialPurgeError):
            purge_saved_mt5_credentials(memory)


class FakeActiveSessionMT5:
    def __init__(self, *, login: int, server: str):
        self.login = login
        self.server = server
        self.calls = []

    def shutdown(self):
        return None

    def initialize(self, **kwargs):
        self.calls.append(dict(kwargs))
        return True

    def last_error(self):
        return (1, "Success")

    def account_info(self):
        return SimpleNamespace(
            login=self.login,
            server=self.server,
            name="Conta Clear",
            currency="BRL",
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            margin_free=10000.0,
            trade_allowed=True,
        )


class ActiveSessionBridgeTests(unittest.TestCase):
    def test_demo_is_detected_from_the_open_mt5_without_credentials(self) -> None:
        bridge = MT5Bridge(environment=REAL)
        fake = FakeActiveSessionMT5(
            login=1199787247,
            server="ClearInvestimentos-DEMO",
        )
        bridge._mt5 = fake
        terminal = Path(r"C:\Program Files\Clear Investimentos MT5\terminal64.exe")
        with patch.object(bridge, "discover_terminal_paths", return_value=[terminal]):
            account = bridge.connect()
        self.assertEqual(account.login, 1199787247)
        self.assertEqual(bridge.environment, SIMULATOR)
        self.assertTrue(bridge.connected)
        self.assertEqual(fake.calls, [{"path": str(terminal)}])

    def test_real_is_detected_from_the_same_terminal_installation(self) -> None:
        bridge = MT5Bridge(environment=SIMULATOR)
        fake = FakeActiveSessionMT5(
            login=1019787247,
            server="ClearInvestimentos-CLEAR",
        )
        bridge._mt5 = fake
        terminal = Path(r"C:\Program Files\Clear Investimentos MT5\terminal64.exe")
        with patch.object(bridge, "discover_terminal_paths", return_value=[terminal]):
            account = bridge.connect()
        self.assertEqual(account.login, 1019787247)
        self.assertEqual(bridge.environment, REAL)
        self.assertEqual(fake.calls, [{"path": str(terminal)}])

    def test_bridge_has_no_api_for_receiving_or_saving_passwords(self) -> None:
        bridge = MT5Bridge()
        self.assertFalse(hasattr(bridge, "set_credentials"))
        self.assertFalse(hasattr(bridge, "credentials_configured"))


if __name__ == "__main__":
    unittest.main()
