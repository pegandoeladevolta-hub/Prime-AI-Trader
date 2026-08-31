from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.mt5_profiles import REAL, SIMULATOR
from prime_ai_trader.ui.live_terminal_clear_profiles import PrimeTraderLiveApp as ClearProfilesApp
from prime_ai_trader.ui.live_terminal_fast import PrimeTraderLiveApp as FastApp
from prime_ai_trader.ui.live_terminal_mt5_credentials import PrimeTraderLiveApp as SessionApp


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeProfileStore:
    def __init__(self):
        self.environment = REAL
        self.saved_path = ""

    def set_environment(self, environment):
        self.environment = environment

    def journal_path(self, environment=None):
        return f"journal-{environment or self.environment}.db"

    def set_terminal_path(self, path, environment=None):
        self.saved_path = path


class MT5AccountRiskUiTests(unittest.TestCase):
    def test_clear_card_connects_to_open_mt5_without_account_selector(self) -> None:
        source = inspect.getsource(ClearProfilesApp._build_clear_profile_card)
        self.assertIn("CONECTAR AO MT5 ABERTO", source)
        self.assertIn("identifica automaticamente", source)
        self.assertNotIn("CONTA REAL", source)
        self.assertNotIn("CONTA DEMO", source)

    def test_detected_mt5_account_selects_real_or_demo_automatically(self) -> None:
        source = inspect.getsource(ClearProfilesApp._on_mt5_account_connected)
        self.assertIn("classify_account_environment", source)
        self.assertIn("set_environment", source)
        self.assertIn("_enforce_real_manual_confirmation", source)

    def test_demo_server_is_adopted_before_positions_and_risk_are_used(self) -> None:
        app = object.__new__(ClearProfilesApp)
        app.profile_store = FakeProfileStore()
        app.mt5 = SimpleNamespace(environment=REAL, terminal_path=r"C:\Clear\terminal64.exe")
        app.mt5_environment_var = FakeVar(REAL)
        app.mt5_environment_status_var = FakeVar()
        app.mt5_terminal_display_var = FakeVar()
        app.status_var = FakeVar()
        app._load_profile_into_view = lambda: None
        enforcement = []
        app._enforce_real_manual_confirmation = lambda: enforcement.append(
            app.profile_store.environment
        )
        account = SimpleNamespace(
            server="ClearInvestimentos-DEMO",
            name="Conta Demo",
            login=1199787247,
        )
        with patch(
            "prime_ai_trader.ui.live_terminal_clear_profiles.MT5TradeJournal",
            return_value="journal-demo",
        ):
            app._on_mt5_account_connected(account)
        self.assertEqual(app.profile_store.environment, SIMULATOR)
        self.assertEqual(app.mt5.environment, SIMULATOR)
        self.assertEqual(app.mt5_journal, "journal-demo")
        self.assertEqual(enforcement, [SIMULATOR])
        self.assertIn("CLEAR DEMO", app.mt5_environment_status_var.get())

    def test_startup_only_purges_old_credentials_and_has_no_login_dialog(self) -> None:
        source = inspect.getsource(SessionApp)
        self.assertIn("purge_saved_mt5_credentials", source)
        self.assertNotIn("SENHA MT5", source)
        self.assertNotIn("LOGIN AUTOMÁTICO", source)
        self.assertNotIn("SALVAR E USAR DEMO", source)

    def test_history_loading_retries_without_generic_error_dialog(self) -> None:
        source = inspect.getsource(FastApp._task_error)
        self.assertIn("MT5_HISTORY_LOADING_PREFIX", source)
        self.assertIn("_history_load_retry_job", source)
        self.assertIn("CARREGANDO HISTÓRICO MT5", source)

    def test_real_account_cannot_pass_automatic_execution_gate(self) -> None:
        source = inspect.getsource(FastApp._auto_enabled_and_armed)
        self.assertIn("profile_store.environment == REAL", source)
        self.assertIn("return False", source)

    def test_real_account_switch_forces_manual_confirmation_mode(self) -> None:
        source = inspect.getsource(ClearProfilesApp._enforce_real_manual_confirmation)
        self.assertIn("EXEC_COMMAND", source)
        self.assertIn("mt5_armed.set(False)", source)


if __name__ == "__main__":
    unittest.main()
