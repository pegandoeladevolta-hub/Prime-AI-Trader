from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from prime_ai_trader.app.mt5_fast_controller import fast_intrabar_gate
from prime_ai_trader.core.models import Direction, Signal, SignalState


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


if __name__ == "__main__":
    unittest.main()
