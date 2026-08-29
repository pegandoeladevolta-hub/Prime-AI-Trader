from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.mt5_credentials import MT5CredentialStore
from prime_ai_trader.app.mt5_profiles import REAL, SIMULATOR
from prime_ai_trader.platform.mt5_dual import MT5Bridge


class MemorySecretStore:
    def __init__(self):
        self.values = {"outro_segredo": "preservar"}

    def load(self):
        return dict(self.values)

    def save(self, values):
        self.values = dict(values)


class CredentialStoreTests(unittest.TestCase):
    def test_real_and_simulator_are_kept_separately(self) -> None:
        memory = MemorySecretStore()
        store = MT5CredentialStore(memory)
        store.save(
            REAL, login=101, password="senha-real", server="ClearInvestimentos-CLEAR"
        )
        store.save(
            SIMULATOR, login=202, password="senha-demo", server="ClearInvestimentos-DEMO"
        )

        real = store.get(REAL)
        demo = store.get(SIMULATOR)
        self.assertTrue(real.configured)
        self.assertTrue(demo.configured)
        self.assertEqual(real.login, 101)
        self.assertEqual(demo.login, 202)
        self.assertEqual(real.password, "senha-real")
        self.assertEqual(demo.password, "senha-demo")
        self.assertEqual(memory.values["outro_segredo"], "preservar")

    def test_clear_one_environment_does_not_remove_the_other(self) -> None:
        memory = MemorySecretStore()
        store = MT5CredentialStore(memory)
        store.save(REAL, login=101, password="r", server="ClearInvestimentos-CLEAR")
        store.save(SIMULATOR, login=202, password="d", server="ClearInvestimentos-DEMO")
        store.clear(SIMULATOR)
        self.assertTrue(store.get(REAL).configured)
        self.assertFalse(store.get(SIMULATOR).configured)


class FakeMT5Module:
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


class AutoLoginBridgeTests(unittest.TestCase):
    def test_real_credentials_are_forwarded_to_official_mt5_initialize(self) -> None:
        bridge = MT5Bridge(environment=REAL)
        bridge.set_credentials(
            login=1019787247,
            password="segredo",
            server="ClearInvestimentos-CLEAR",
        )
        fake = FakeMT5Module(login=1019787247, server="ClearInvestimentos-CLEAR")
        bridge._mt5 = fake
        terminal = Path(r"C:\Clear\terminal64.exe")
        with patch.object(bridge, "discover_for_environment", return_value=[terminal]):
            account = bridge.connect()
        self.assertEqual(account.login, 1019787247)
        self.assertEqual(fake.calls[0]["login"], 1019787247)
        self.assertEqual(fake.calls[0]["password"], "segredo")
        self.assertEqual(fake.calls[0]["server"], "ClearInvestimentos-CLEAR")
        self.assertEqual(fake.calls[0]["path"], str(terminal))

    def test_demo_credentials_are_forwarded_and_classified_as_simulator(self) -> None:
        bridge = MT5Bridge(environment=SIMULATOR)
        bridge.set_credentials(
            login=987654,
            password="demo-secret",
            server="ClearInvestimentos-DEMO",
        )
        fake = FakeMT5Module(login=987654, server="ClearInvestimentos-DEMO")
        bridge._mt5 = fake
        terminal = Path(r"C:\Clear Simulador\terminal64.exe")
        with patch.object(bridge, "discover_for_environment", return_value=[terminal]):
            account = bridge.connect()
        self.assertEqual(account.login, 987654)
        self.assertTrue(bridge.connected)
        self.assertEqual(fake.calls[0]["server"], "ClearInvestimentos-DEMO")


if __name__ == "__main__":
    unittest.main()
