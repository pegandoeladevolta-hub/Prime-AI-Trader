from __future__ import annotations

import inspect
import unittest

from prime_ai_trader.app.mt5_position_guard import PrimeAutoPositionGuard
from prime_ai_trader.platform.mt5_positions import MT5Bridge
from prime_ai_trader.ui.live_terminal_fast import PrimeTraderLiveApp


class PrimeAutoPositionGuardTests(unittest.TestCase):
    def test_order_acceptance_blocks_during_mt5_sync_window(self) -> None:
        guard = PrimeAutoPositionGuard(sync_grace_seconds=5.0, flat_confirmations=2)
        guard.mark_order_accepted(now=100.0)
        status = guard.evaluate([], connected=True, now=101.0)
        self.assertTrue(status.blocked)
        self.assertIn("sincronização", status.reason)

    def test_open_position_blocks_all_new_orders_until_it_disappears(self) -> None:
        guard = PrimeAutoPositionGuard(sync_grace_seconds=5.0, flat_confirmations=2)
        guard.mark_order_accepted(now=100.0)
        position = {"ticket": 10, "symbol": "EURUSD", "magic": MT5Bridge.MAGIC}

        active = guard.evaluate([position], connected=True, now=101.0)
        self.assertTrue(active.blocked)
        self.assertEqual(active.open_positions, 1)

        # Uma leitura vazia não é suficiente: evita liberar por oscilação do MT5.
        first_empty = guard.evaluate([], connected=True, now=110.0)
        self.assertTrue(first_empty.blocked)
        self.assertFalse(first_empty.released)

        second_empty = guard.evaluate([], connected=True, now=111.0)
        self.assertFalse(second_empty.blocked)
        self.assertTrue(second_empty.released)

    def test_restart_detects_existing_prime_position_without_local_state(self) -> None:
        guard = PrimeAutoPositionGuard()
        status = guard.evaluate(
            [{"ticket": 22, "symbol": "BTCUSD", "magic": MT5Bridge.MAGIC}],
            connected=True,
            now=200.0,
        )
        self.assertTrue(status.blocked)
        self.assertTrue(guard.locked)
        self.assertTrue(guard.position_seen)

    def test_disconnect_never_releases_an_existing_lock(self) -> None:
        guard = PrimeAutoPositionGuard()
        guard.mark_order_accepted(now=10.0)
        status = guard.evaluate([], connected=False, now=100.0)
        self.assertTrue(status.blocked)
        self.assertTrue(guard.locked)

    def test_prime_position_filter_uses_magic_or_prime_comment(self) -> None:
        magic = MT5Bridge.MAGIC
        self.assertTrue(MT5Bridge._is_prime_position({"magic": magic}, magic))
        self.assertTrue(MT5Bridge._is_prime_position({"magic": 0, "comment": "Prime Trader"}, magic))
        self.assertFalse(MT5Bridge._is_prime_position({"magic": 0, "comment": "Manual"}, magic))

    def test_auto_terminal_has_position_gate_before_parent_execution(self) -> None:
        source = inspect.getsource(PrimeTraderLiveApp._maybe_execute_auto)
        self.assertIn("_prime_position_status", source)
        self.assertIn("guard_status.blocked", source)
        self.assertIn("super()._maybe_execute_auto", source)
        self.assertLess(
            source.index("guard_status.blocked"),
            source.rindex("super()._maybe_execute_auto"),
        )

    def test_successful_order_arms_local_position_guard(self) -> None:
        source = inspect.getsource(PrimeTraderLiveApp._execute_confirmed_signal)
        self.assertIn("mark_order_accepted", source)
        self.assertIn("nenhuma nova ordem até esta posição encerrar", source)


if __name__ == "__main__":
    unittest.main()
