from __future__ import annotations

import inspect
import unittest

from prime_ai_trader.ui.live_terminal_clear_profiles import PrimeTraderLiveApp as ClearProfilesApp
from prime_ai_trader.ui.live_terminal_fast import PrimeTraderLiveApp as FastApp
from prime_ai_trader.ui.live_terminal_mt5_credentials import PrimeTraderLiveApp as CredentialsApp


class MT5AccountRiskUiTests(unittest.TestCase):
    def test_clear_account_selector_has_direct_real_and_demo_buttons(self) -> None:
        source = inspect.getsource(ClearProfilesApp._build_clear_profile_card)
        self.assertIn("CONTA REAL", source)
        self.assertIn("CONTA DEMO", source)
        self.assertIn("_select_environment", source)

    def test_mismatch_handler_offers_active_account_or_login_review(self) -> None:
        source = inspect.getsource(CredentialsApp._handle_mt5_connection_error)
        self.assertIn("askyesnocancel", source)
        self.assertIn("_connect_active_session_once", source)
        self.assertIn("_open_credentials_dialog", source)

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
