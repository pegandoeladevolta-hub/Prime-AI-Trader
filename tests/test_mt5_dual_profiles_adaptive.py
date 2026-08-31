from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from prime_ai_trader.app.mt5_adaptive_controller import (
    MT5AdaptiveTradingController,
    MT5_HISTORY_LOADING_PREFIX,
)
from prime_ai_trader.app.mt5_profiles import REAL, SIMULATOR, MT5ProfileStore, classify_account_environment
from prime_ai_trader.platform.mt5_dual import MT5Bridge


class MT5ProfileStoreTests(unittest.TestCase):
    def test_real_and_simulator_share_terminal_but_keep_limits_and_journals_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MT5ProfileStore(Path(tmp) / "profiles.json")
            store.set_terminal_path(r"C:\Clear\terminal64.exe", REAL)
            store.set_daily_limits(300, 120, REAL)
            store.set_consecutive_loss_limit(2, REAL)
            store.set_daily_limits(800, 350, SIMULATOR)
            store.set_consecutive_loss_limit(4, SIMULATOR)
            self.assertEqual(store.terminal_path(REAL), store.terminal_path(SIMULATOR))
            self.assertEqual(store.terminal_path(), r"C:\Clear\terminal64.exe")
            self.assertEqual(store.daily_limits(REAL), (300.0, 120.0))
            self.assertEqual(store.daily_limits(SIMULATOR), (800.0, 350.0))
            self.assertEqual(store.consecutive_loss_limit(REAL), 2)
            self.assertEqual(store.consecutive_loss_limit(SIMULATOR), 4)
            self.assertNotEqual(store.journal_path(REAL), store.journal_path(SIMULATOR))

    def test_legacy_real_terminal_path_becomes_the_single_shared_mt5_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            path.write_text(
                '{"environment":"CLEAR SIMULADOR",'
                '"real_terminal_path":"C:\\\\Program Files\\\\Clear Investimentos MT5\\\\terminal64.exe"}',
                encoding="utf-8",
            )
            store = MT5ProfileStore(path)
            expected = r"C:\Program Files\Clear Investimentos MT5\terminal64.exe"
            self.assertEqual(store.terminal_path(REAL), expected)
            self.assertEqual(store.terminal_path(SIMULATOR), expected)

    def test_server_classification(self) -> None:
        self.assertEqual(classify_account_environment("ClearInvestimentos-CLEAR"), REAL)
        self.assertEqual(classify_account_environment("ClearInvestimentos-DEMO"), SIMULATOR)
        self.assertEqual(classify_account_environment("CLEAR-Simulador"), SIMULATOR)


class AdaptiveDepthTests(unittest.TestCase):
    def test_270_candles_are_used_instead_of_rejected_when_2000_requested(self) -> None:
        controller = object.__new__(MT5AdaptiveTradingController)
        controller.settings = SimpleNamespace(mt5_analysis_candles=2000)
        controller._effective_analysis_candles = 0
        controller._analysis_reduced_warning = ""
        history = list(range(270))
        chart, decision, _ = controller._live_analysis_windows(history, "1m")
        self.assertEqual(len(chart), 200)
        self.assertEqual(len(decision), 270)
        status = controller.analysis_depth_status()
        self.assertTrue(status["reduced"])
        self.assertEqual(status["effective"], 270)
        self.assertEqual(status["requested"], 2000)

    def test_too_little_history_still_blocks_for_quality(self) -> None:
        controller = object.__new__(MT5AdaptiveTradingController)
        controller.settings = SimpleNamespace(mt5_analysis_candles=2000)
        controller._effective_analysis_candles = 0
        controller._analysis_reduced_warning = ""
        with self.assertRaisesRegex(ValueError, MT5_HISTORY_LOADING_PREFIX):
            controller._live_analysis_windows(list(range(120)), "1m")


class FakeHistoryMT5:
    TIMEFRAME_M1 = 1

    def __init__(self) -> None:
        self.range_calls = 0

    def symbol_info(self, symbol):
        return SimpleNamespace(visible=True)

    def account_info(self):
        return SimpleNamespace(login=1199787247)

    @staticmethod
    def _rows(amount: int):
        start = 1_700_000_000
        return [
            {
                "time": start + index * 60,
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.1,
                "real_volume": 1,
                "tick_volume": 2,
            }
            for index in range(amount)
        ]

    def copy_rates_from_pos(self, symbol, timeframe, start, limit):
        return self._rows(108)

    def copy_rates_range(self, symbol, timeframe, start, end):
        self.range_calls += 1
        return self._rows(250)

    def last_error(self):
        return (1, "Success")


class MT5HistoryWarmupTests(unittest.TestCase):
    def test_short_chart_history_requests_an_older_server_range(self) -> None:
        bridge = MT5Bridge(environment=SIMULATOR)
        fake = FakeHistoryMT5()
        bridge._mt5 = fake
        bridge.connected = True
        candles = bridge.fetch_candles("BBSEU434", "1m", limit=2001)
        self.assertEqual(len(candles), 250)
        self.assertEqual(fake.range_calls, 1)


class FakeProfitMT5:
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def account_info(self):
        return SimpleNamespace(login=1)

    def order_calc_profit(self, order_type, symbol, volume, open_price, close_price):
        direction = 1 if order_type == self.ORDER_TYPE_BUY else -1
        return direction * (close_price - open_price) * volume * 100000


class TradeValueTests(unittest.TestCase):
    def test_financial_estimate_uses_terminal_formula(self) -> None:
        bridge = MT5Bridge(environment=REAL)
        bridge._mt5 = FakeProfitMT5()
        bridge.connected = True
        value = bridge.estimate_trade_profit("EURUSD", "BUY", 1.5, 1.1000, 1.1010)
        self.assertAlmostEqual(value, 150.0)


if __name__ == "__main__":
    unittest.main()
