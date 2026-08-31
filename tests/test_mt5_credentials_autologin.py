from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.mt5_credentials import (
    MT5Credentials,
    MT5CredentialPersistenceError,
    MT5CredentialStore,
    parse_mt5_credentials,
)
from prime_ai_trader.app.mt5_profiles import REAL, SIMULATOR
from prime_ai_trader.config.settings import SecretStore
from prime_ai_trader.platform.mt5_dual import MT5Bridge, MT5ProfileMismatchError


class MemorySecretStore:
    def __init__(self):
        self.values = {"outro_segredo": "preservar"}

    def load(self):
        return dict(self.values)

    def save(self, values):
        self.values = dict(values)


class DiscardingSecretStore(MemorySecretStore):
    def save(self, values):
        return None


class CredentialStoreTests(unittest.TestCase):
    def test_default_real_server_does_not_make_blank_real_section_partial(self) -> None:
        credentials = parse_mt5_credentials(
            REAL,
            login_text="",
            password="",
            server="ClearInvestimentos-CLEAR",
        )
        self.assertIsNone(credentials)

    def test_demo_form_values_are_parsed_independently(self) -> None:
        credentials = parse_mt5_credentials(
            SIMULATOR,
            login_text="1199787247",
            password="senha-demo",
            server="ClearInvestimentos-DEMO",
        )
        self.assertEqual(credentials.login, 1199787247)
        self.assertEqual(credentials.server, "ClearInvestimentos-DEMO")
        self.assertTrue(credentials.configured)

    def test_partial_section_has_specific_validation_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "SENHA MT5"):
            parse_mt5_credentials(
                SIMULATOR,
                login_text="1199787247",
                password="",
                server="ClearInvestimentos-DEMO",
            )

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

    def test_both_profiles_are_validated_before_any_write(self) -> None:
        memory = MemorySecretStore()
        original = dict(memory.values)
        store = MT5CredentialStore(memory)
        with self.assertRaisesRegex(ValueError, "senha"):
            store.save_profiles({
                REAL: MT5Credentials(101, "senha-real", "ClearInvestimentos-CLEAR"),
                SIMULATOR: MT5Credentials(202, "", "ClearInvestimentos-DEMO"),
            })
        self.assertEqual(memory.values, original)

    def test_save_is_verified_instead_of_showing_false_success(self) -> None:
        store = MT5CredentialStore(DiscardingSecretStore())
        with self.assertRaises(MT5CredentialPersistenceError):
            store.save(
                SIMULATOR,
                login=202,
                password="senha-demo",
                server="ClearInvestimentos-DEMO",
            )

    def test_demo_survives_closing_and_reopening_the_encrypted_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "secrets.dat"
            first = MT5CredentialStore(SecretStore(path))
            first.save(
                SIMULATOR,
                login=1199787247,
                password="senha-demo",
                server="ClearInvestimentos-DEMO",
            )

            reopened = MT5CredentialStore(SecretStore(path)).get(SIMULATOR)
            self.assertEqual(reopened.login, 1199787247)
            self.assertEqual(reopened.password, "senha-demo")
            self.assertEqual(reopened.server, "ClearInvestimentos-DEMO")
            self.assertTrue(reopened.configured)


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


class ReauthenticationRejectedMT5(FakeMT5Module):
    """Imita a Clear: sessão ativa funciona, novo login retorna erro -6."""

    def __init__(self, *, login: int, server: str):
        super().__init__(login=login, server=server)
        self.error = (1, "Success")

    def initialize(self, **kwargs):
        self.calls.append(dict(kwargs))
        if "login" in kwargs:
            self.error = (-6, "Terminal: Authorization failed")
            return False
        self.error = (1, "Success")
        return True

    def last_error(self):
        return self.error


class AccountSwitchingMT5(FakeMT5Module):
    def initialize(self, **kwargs):
        self.calls.append(dict(kwargs))
        if "login" in kwargs:
            self.login = int(kwargs["login"])
            self.server = str(kwargs["server"])
        return True


class AutoLoginBridgeTests(unittest.TestCase):
    def test_matching_active_session_is_used_without_resending_password(self) -> None:
        bridge = MT5Bridge(environment=REAL)
        bridge.set_credentials(
            login=1019787247,
            password="segredo",
            server="ClearInvestimentos-CLEAR",
        )
        fake = ReauthenticationRejectedMT5(
            login=1019787247, server="ClearInvestimentos-CLEAR"
        )
        bridge._mt5 = fake
        terminal = Path(r"C:\Clear\terminal64.exe")
        with patch.object(bridge, "discover_for_environment", return_value=[terminal]):
            account = bridge.connect()
        self.assertEqual(account.login, 1019787247)
        self.assertEqual(fake.calls[0]["path"], str(terminal))
        self.assertNotIn("login", fake.calls[0])
        self.assertNotIn("password", fake.calls[0])
        self.assertEqual(len(fake.calls), 1)

    def test_demo_active_session_survives_reauthentication_error_minus_6(self) -> None:
        bridge = MT5Bridge(environment=SIMULATOR)
        bridge.set_credentials(
            login=987654,
            password="demo-secret",
            server="ClearInvestimentos-DEMO",
        )
        fake = ReauthenticationRejectedMT5(
            login=987654, server="ClearInvestimentos-DEMO"
        )
        bridge._mt5 = fake
        terminal = Path(r"C:\Clear Simulador\terminal64.exe")
        with patch.object(bridge, "discover_for_environment", return_value=[terminal]):
            account = bridge.connect()
        self.assertEqual(account.login, 987654)
        self.assertTrue(bridge.connected)
        self.assertNotIn("server", fake.calls[0])
        self.assertEqual(len(fake.calls), 1)

    def test_credentials_are_used_only_to_switch_from_another_active_account(self) -> None:
        bridge = MT5Bridge(environment=SIMULATOR)
        bridge.set_credentials(
            login=987654,
            password="demo-secret",
            server="ClearInvestimentos-DEMO",
        )
        fake = AccountSwitchingMT5(
            login=1019787247, server="ClearInvestimentos-CLEAR"
        )
        bridge._mt5 = fake
        terminal = Path(r"C:\Clear\terminal64.exe")
        with patch.object(bridge, "discover_for_environment", return_value=[terminal]):
            account = bridge.connect()
        self.assertEqual(account.login, 987654)
        self.assertEqual(len(fake.calls), 2)
        self.assertNotIn("login", fake.calls[0])
        self.assertEqual(fake.calls[1]["login"], 987654)
        self.assertEqual(fake.calls[1]["password"], "demo-secret")
        self.assertEqual(fake.calls[1]["server"], "ClearInvestimentos-DEMO")

    def test_profile_mismatch_exposes_safe_account_choice_context(self) -> None:
        bridge = MT5Bridge(environment=REAL)
        fake = FakeMT5Module(login=987654, server="ClearInvestimentos-DEMO")
        bridge._mt5 = fake
        terminal = Path(r"C:\Clear\terminal64.exe")
        with patch.object(bridge, "discover_for_environment", return_value=[terminal]):
            with self.assertRaises(MT5ProfileMismatchError) as captured:
                bridge.connect()
        error = captured.exception
        self.assertEqual(error.expected_environment, REAL)
        self.assertEqual(error.detected_environment, SIMULATOR)
        self.assertEqual(error.detected_login, 987654)
        self.assertFalse(error.credentials_configured)
        self.assertNotIn("password", str(error).lower())


if __name__ == "__main__":
    unittest.main()
