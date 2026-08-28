from __future__ import annotations

import inspect
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from prime_ai_trader.app.mt5_fast_controller import (
    FAST_STABLE_SECONDS,
    FastSignalStability,
    MT5FastTradingController,
    fast_intrabar_gate,
)
from prime_ai_trader.core.models import Candle, Direction, Signal, SignalState
from prime_ai_trader.ui.live_terminal_fast import PrimeTraderLiveApp


class MT5FastIntrabarTests(unittest.TestCase):
    def _signal(self, *, score: int = 76, rr: float = 1.8) -> Signal:
        return Signal(
            direction=Direction.BUY,
            state=SignalState.FORMING,
            score=score,
            probabilities={"COMPRA": 0.66, "VENDA": 0.34},
            entry=0.71983,
            horizon_minutes=0,
            technical_stop=0.71953,
            technical_target=0.72037,
            technical_room_ratio=rr,
            waiting_reasons=[],
            blockers=[],
        )

    @staticmethod
    def _candle(opened: datetime, *, closed: bool) -> Candle:
        return Candle(
            open_time=opened,
            open=1.1000,
            high=1.1010,
            low=1.0990,
            close=1.1005,
            volume=100,
            close_time=(opened + timedelta(minutes=1)) if closed else None,
            closed=closed,
        )

    def test_fast_price_action_can_confirm_open_one_minute_candle(self) -> None:
        now = datetime.now(timezone.utc)
        allowed, reason = fast_intrabar_gate(
            self._signal(),
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            timeframe="1m",
            minimum_rr=1.5,
            candle_open_time=now - timedelta(seconds=8),
            candle_closed=False,
            now=now,
        )
        self.assertTrue(allowed, reason)

    def test_first_ticks_are_not_confirmed_immediately(self) -> None:
        now = datetime.now(timezone.utc)
        allowed, _ = fast_intrabar_gate(
            self._signal(),
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            timeframe="1m",
            minimum_rr=1.5,
            candle_open_time=now - timedelta(seconds=2),
            candle_closed=False,
            now=now,
        )
        self.assertFalse(allowed)

    def test_fast_confirmation_requires_extra_score_margin(self) -> None:
        now = datetime.now(timezone.utc)
        allowed, _ = fast_intrabar_gate(
            self._signal(score=60),
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            timeframe="1m",
            minimum_rr=1.5,
            candle_open_time=now - timedelta(seconds=10),
            candle_closed=False,
            now=now,
        )
        self.assertFalse(allowed)

    def test_fast_confirmation_never_bypasses_rr_or_sltp(self) -> None:
        now = datetime.now(timezone.utc)
        signal = self._signal(rr=1.2)
        allowed, _ = fast_intrabar_gate(
            signal,
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            timeframe="1m",
            minimum_rr=1.5,
            candle_open_time=now - timedelta(seconds=10),
            candle_closed=False,
            now=now,
        )
        self.assertFalse(allowed)
        signal.technical_stop = None
        signal.technical_room_ratio = 1.8
        allowed, _ = fast_intrabar_gate(
            signal,
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            timeframe="1m",
            minimum_rr=1.5,
            candle_open_time=now - timedelta(seconds=10),
            candle_closed=False,
            now=now,
        )
        self.assertFalse(allowed)

    def test_balanced_and_confirmation_modes_keep_closed_candle_policy(self) -> None:
        now = datetime.now(timezone.utc)
        for sensitivity, mode in (("EQUILIBRADO", "PRICE ACTION"), ("RÁPIDO", "CONFIRMAÇÃO")):
            with self.subTest(sensitivity=sensitivity, mode=mode):
                allowed, _ = fast_intrabar_gate(
                    self._signal(),
                    sensitivity=sensitivity,
                    mode=mode,
                    timeframe="1m",
                    minimum_rr=1.5,
                    candle_open_time=now - timedelta(seconds=20),
                    candle_closed=False,
                    now=now,
                )
                self.assertFalse(allowed)

    def test_three_stable_observations_can_reach_promotion_path(self) -> None:
        """Regressão do histórico real: sequência FORMING não pode ficar presa."""
        controller = MT5FastTradingController.__new__(MT5FastTradingController)
        controller._fast_promoted_candles = set()
        controller._fast_stability = FastSignalStability()
        controller._last_fast_gate_reason = ""
        controller.settings = SimpleNamespace(sensitivity="RÁPIDO", mode="PRICE ACTION")
        controller.minimum_rr = lambda: 1.5
        promoted = []
        controller._promote_snapshot = lambda snapshot, key: promoted.append(key) or "PROMOTED"

        opened = datetime.now(timezone.utc) - timedelta(seconds=20)
        candle = self._candle(opened, closed=False)
        snapshot = SimpleNamespace(
            signal=self._signal(score=92, rr=1.8),
            history_candles=[candle],
            candles=[candle],
            symbol="EURUSD",
            timeframe="1m",
        )

        self.assertIs(controller._observe_intrabar(snapshot), snapshot)
        controller._fast_stability.first_seen -= FAST_STABLE_SECONDS + 0.1
        self.assertIs(controller._observe_intrabar(snapshot), snapshot)
        result = controller._observe_intrabar(snapshot)
        self.assertEqual(result, "PROMOTED")
        self.assertEqual(len(promoted), 1)

    def test_direction_change_resets_fast_stability(self) -> None:
        stability = FastSignalStability()
        stability.observe(("EURUSD", "1m", "candle", "VENDA"), now=10.0)
        stability.observe(("EURUSD", "1m", "candle", "VENDA"), now=11.0)
        streak, stable_for, stable = stability.observe(
            ("EURUSD", "1m", "candle", "COMPRA"), now=13.0,
        )
        self.assertEqual(streak, 1)
        self.assertEqual(stable_for, 0.0)
        self.assertFalse(stable)

    def test_closed_candle_is_not_hidden_by_newer_open_candle(self) -> None:
        @dataclass
        class Snapshot:
            candles: list
            history_candles: list

        controller = MT5FastTradingController.__new__(MT5FastTradingController)
        opened = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=2)
        previous = self._candle(opened, closed=True)
        closing = self._candle(opened + timedelta(minutes=1), closed=True)
        newer = self._candle(opened + timedelta(minutes=2), closed=False)
        controller.snapshot = Snapshot(
            candles=[previous, closing, newer],
            history_candles=[previous, closing, newer],
        )
        controller._prepare_closed_candle_analysis(closing)
        self.assertEqual(controller.snapshot.history_candles[-1].open_time, closing.open_time)
        self.assertTrue(controller.snapshot.history_candles[-1].closed)

    def test_visible_automatic_mode_is_source_of_truth(self) -> None:
        source = inspect.getsource(PrimeTraderLiveApp)
        self.assertIn("self.execution_profile_var.get() == EXEC_AUTO", source)
        self.assertIn("self.mt5_auto.set", source)
        self.assertNotIn("self.execution_profile_var.set(EXEC_SIGNALS)", source)


if __name__ == "__main__":
    unittest.main()
