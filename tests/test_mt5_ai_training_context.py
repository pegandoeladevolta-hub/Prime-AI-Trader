from __future__ import annotations

import unittest
from types import SimpleNamespace

from prime_ai_trader.app.controller import LIVE_MAXIMUM_CANDLES, LIVE_MINIMUM_CANDLES
from prime_ai_trader.app.mt5_controller import MT5TradingController
from prime_ai_trader.core.models import Market


class MT5AITrainingContextTests(unittest.TestCase):
    def _controller(self, *, execution="SÓ SINAIS", depth=5000):
        controller = MT5TradingController.__new__(MT5TradingController)
        controller.settings = SimpleNamespace(
            market=Market.FOREX.value,
            mt5_symbol="USDJPY",
            crypto_symbol="BTCUSD",
            forex_symbol="USDJPY",
            timeframe="1m",
            horizon_minutes=1,
            sensitivity="RÁPIDO",
            mode="PRICE ACTION",
            mt5_execution_profile=execution,
            mt5_training_candles=depth,
        )
        return controller

    def test_model_context_separates_execution_profile_and_training_depth(self):
        first = self._controller(execution="SÓ SINAIS", depth=5000).model_context()
        second = self._controller(execution="AUTOMÁTICO", depth=5000).model_context()
        third = self._controller(execution="AUTOMÁTICO", depth=10000).model_context()
        self.assertEqual(first["timeframe"], "1m")
        self.assertEqual(first["sensitivity"], "RÁPIDO")
        self.assertEqual(first["mode"], "PRICE ACTION")
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)

    def test_live_signal_window_is_not_changed_by_deep_training_history(self):
        self.assertEqual(LIVE_MINIMUM_CANDLES, 200)
        self.assertEqual(LIVE_MAXIMUM_CANDLES, 200)


if __name__ == "__main__":
    unittest.main()
