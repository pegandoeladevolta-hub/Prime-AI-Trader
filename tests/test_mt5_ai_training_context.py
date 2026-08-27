from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.controller import TradingController
from prime_ai_trader.app.mt5_controller import LIVE_CHART_CANDLES, MT5TradingController
from prime_ai_trader.core.models import Market


class MT5AITrainingContextTests(unittest.TestCase):
    def _controller(
        self, *, execution="SÓ SINAIS", training_depth=5000, analysis_depth=2000,
    ):
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
            mt5_analysis_candles=analysis_depth,
            mt5_training_candles=training_depth,
        )
        return controller

    def test_model_context_separates_execution_training_and_analysis_depth(self):
        first = self._controller(execution="SÓ SINAIS").model_context()
        second = self._controller(execution="AUTOMÁTICO").model_context()
        third = self._controller(execution="AUTOMÁTICO", training_depth=10000).model_context()
        fourth = self._controller(
            execution="AUTOMÁTICO", training_depth=10000, analysis_depth=3000,
        ).model_context()
        self.assertEqual(first["timeframe"], "1m")
        self.assertEqual(first["sensitivity"], "RÁPIDO")
        self.assertEqual(first["mode"], "PRICE ACTION")
        self.assertEqual(first["analysis_candles"], 2000)
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)
        self.assertNotEqual(third, fourth)

    def test_live_signal_uses_deep_context_but_chart_remains_compact(self):
        controller = self._controller(analysis_depth=2000)
        controller._decision_candles = lambda candles, timeframe: candles
        history = list(range(2201))
        chart, decision, next_candle = controller._live_analysis_windows(history, "1m")
        self.assertEqual(len(decision), 2000)
        self.assertEqual(len(chart), LIVE_CHART_CANDLES)
        self.assertEqual(LIVE_CHART_CANDLES, 200)
        self.assertFalse(next_candle)
        self.assertEqual(decision[-1], history[-1])

    def test_analyze_requests_enough_history_for_selected_depth(self):
        controller = self._controller(analysis_depth=3000)
        with patch.object(TradingController, "analyze", return_value="snapshot") as mocked:
            result = controller.analyze(limit=500)
        self.assertEqual(result, "snapshot")
        mocked.assert_called_once_with(limit=3001)

    def test_invalid_analysis_depth_falls_back_to_2000(self):
        controller = self._controller(analysis_depth=777)
        self.assertEqual(controller.analysis_candles(), 2000)
        self.assertEqual(controller.settings.mt5_analysis_candles, 2000)


if __name__ == "__main__":
    unittest.main()
