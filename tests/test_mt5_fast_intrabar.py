from __future__ import annotations

import inspect
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from prime_ai_trader.app.mt5_fast_controller import (
    MarketSignalStability,
    MT5FastTradingController,
    market_context_gate,
)
from prime_ai_trader.core.models import Candle, Direction, Signal, SignalState
from prime_ai_trader.ui.live_terminal_fast import PrimeTraderLiveApp


class MT5MarketContextTests(unittest.TestCase):
    def _signal(
        self,
        *,
        score: int = 78,
        rr: float = 1.8,
        direction: Direction = Direction.BUY,
    ) -> Signal:
        return Signal(
            direction=direction,
            state=SignalState.FORMING,
            score=score,
            probabilities={"COMPRA": 0.66, "VENDA": 0.24, "AGUARDAR": 0.10},
            entry=1.1000,
            horizon_minutes=0,
            technical_stop=1.0990 if direction == Direction.BUY else 1.1010,
            technical_target=1.1018 if direction == Direction.BUY else 1.0982,
            technical_room_ratio=rr,
            waiting_reasons=[],
            blockers=[],
            setup_name="PULLBACK DE TENDÊNCIA",
            buy_score=78 if direction == Direction.BUY else 34,
            sell_score=34 if direction == Direction.BUY else 78,
            independent_confirmations=["tendência", "momentum", "price action"],
            momentum_votes=3,
            higher_timeframe_bias="ALTA" if direction == Direction.BUY else "BAIXA",
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

    def test_open_candle_can_be_confirmed_by_market_context(self) -> None:
        allowed, reason, context_score = market_context_gate(
            self._signal(),
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            minimum_rr=1.5,
            structure_trend="ALTA",
        )
        self.assertTrue(allowed, reason)
        self.assertGreaterEqual(context_score, 4)

    def test_balanced_mode_no_longer_requires_candle_close(self) -> None:
        signal = self._signal(score=82)
        allowed, reason, _ = market_context_gate(
            signal,
            sensitivity="EQUILIBRADO",
            mode="CONFIRMAÇÃO",
            minimum_rr=1.5,
            structure_trend="ALTA",
        )
        self.assertTrue(allowed, reason)

    def test_context_confirmation_never_bypasses_rr_or_sltp(self) -> None:
        signal = self._signal(rr=1.2)
        allowed, _, _ = market_context_gate(
            signal,
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            minimum_rr=1.5,
            structure_trend="ALTA",
        )
        self.assertFalse(allowed)
        signal.technical_room_ratio = 1.8
        signal.technical_stop = None
        allowed, _, _ = market_context_gate(
            signal,
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            minimum_rr=1.5,
            structure_trend="ALTA",
        )
        self.assertFalse(allowed)

    def test_weak_context_is_not_promoted_just_because_price_moves(self) -> None:
        signal = self._signal(score=78)
        signal.independent_confirmations = []
        signal.momentum_votes = 0
        signal.higher_timeframe_bias = "BAIXA"
        allowed, reason, context_score = market_context_gate(
            signal,
            sensitivity="EQUILIBRADO",
            mode="CONFIRMAÇÃO",
            minimum_rr=1.5,
            structure_trend="LATERAL",
        )
        self.assertFalse(allowed)
        self.assertIn("contexto de mercado", reason)
        self.assertLess(context_score, 5)

    def test_stability_is_about_opportunity_not_candle_boundary(self) -> None:
        stability = MarketSignalStability()
        key = ("EURUSD", "1m", "COMPRA", "PULLBACK", 2200)
        streak, _, stable = stability.observe(
            key, required_streak=2, required_seconds=0.5, now=10.0,
        )
        self.assertEqual(streak, 1)
        self.assertFalse(stable)
        # A segunda observação pode estar em outra vela; como a chave não contém
        # open_time, a tese continua sendo a mesma oportunidade de mercado.
        streak, stable_for, stable = stability.observe(
            key, required_streak=2, required_seconds=0.5, now=11.0,
        )
        self.assertEqual(streak, 2)
        self.assertGreaterEqual(stable_for, 1.0)
        self.assertTrue(stable)

    def test_context_observations_can_reach_promotion_without_closed_candle(self) -> None:
        controller = MT5FastTradingController.__new__(MT5FastTradingController)
        controller._market_stability = MarketSignalStability()
        controller._active_opportunity = None
        controller._wait_observations = 0
        controller._last_market_gate_reason = ""
        controller.settings = SimpleNamespace(sensitivity="RÁPIDO", mode="PRICE ACTION")
        controller.minimum_rr = lambda: 1.5
        promoted = []
        controller._promote_snapshot = (
            lambda snapshot, key, context_score:
            promoted.append((key, context_score)) or "PROMOTED"
        )

        opened = datetime.now(timezone.utc) - timedelta(seconds=8)
        candle = self._candle(opened, closed=False)
        snapshot = SimpleNamespace(
            signal=self._signal(score=92, rr=1.8),
            history_candles=[candle],
            candles=[candle],
            symbol="EURUSD",
            timeframe="1m",
            structure=SimpleNamespace(trend="ALTA"),
        )

        self.assertIs(controller._observe_market_context(snapshot), snapshot)
        controller._market_stability.first_seen -= 1.0
        result = controller._observe_market_context(snapshot)
        self.assertEqual(result, "PROMOTED")
        self.assertEqual(len(promoted), 1)

    def test_direction_change_resets_market_stability(self) -> None:
        stability = MarketSignalStability()
        stability.observe(("EURUSD", "1m", "VENDA"), now=10.0)
        stability.observe(("EURUSD", "1m", "VENDA"), now=11.0)
        streak, stable_for, stable = stability.observe(
            ("EURUSD", "1m", "COMPRA"), now=13.0,
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
