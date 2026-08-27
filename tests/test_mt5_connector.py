from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from prime_ai_trader.platform.mt5 import (
    MT5UnavailableError, MetaTrader5Gateway,
)


class FakeMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M3 = 3
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240

    def __init__(self, *, initialize_ok: bool = True, trade_mode: int = 0) -> None:
        self.initialize_ok = initialize_ok
        self.trade_mode = trade_mode
        self.initialize_calls = []
        self.shutdown_calls = 0

    def initialize(self, **kwargs):
        self.initialize_calls.append(kwargs)
        return self.initialize_ok

    def last_error(self):
        return (-1, "teste")

    def version(self):
        return (500, 5100, "27 Aug 2026")

    def terminal_info(self):
        return SimpleNamespace(
            connected=True, name="MetaTrader 5", path="C:/MT5", build=5100,
        )

    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.trade_mode, balance=300.0, equity=280.0,
            profit=-20.0, margin=50.0, margin_free=230.0, currency="BRL",
            server="Clear-Demo", company="Clear Corretora",
            trade_allowed=True, trade_expert=False,
        )

    def symbols_get(self):
        return (
            SimpleNamespace(name="WINV26", visible=True),
            SimpleNamespace(name="WDOV26", visible=True),
            SimpleNamespace(name="OCULTO", visible=False),
        )

    def copy_rates_from_pos(self, symbol, timeframe, start, limit):
        del symbol, timeframe, start
        base = 1_700_000_000
        return [
            {
                "time": base + index * 300, "open": 100.0 + index,
                "high": 101.0 + index, "low": 99.0 + index,
                "close": 100.5 + index, "tick_volume": 25 + index,
                "real_volume": 0,
            }
            for index in range(limit)
        ]

    def positions_get(self):
        return (SimpleNamespace(
            ticket=1, symbol="WINV26", type=0, volume=1.0,
            price_open=141000.0, price_current=141100.0,
            sl=140900.0, tp=141300.0, profit=20.0,
        ),)

    def history_deals_get(self, date_from, date_to):
        del date_from, date_to
        return (SimpleNamespace(
            ticket=2, order=3, time=1_700_000_000, symbol="WINV26",
            type=0, entry=0, volume=1.0, price=141000.0, profit=25.0,
            commission=-0.5, swap=0.0,
        ),)

    def shutdown(self):
        self.shutdown_calls += 1


class MetaTrader5GatewayTests(unittest.TestCase):
    def test_connect_reuses_terminal_session_without_credentials(self) -> None:
        fake = FakeMT5(trade_mode=0)
        gateway = MetaTrader5Gateway(fake)
        snapshot = gateway.connect()
        self.assertEqual(snapshot.account.mode, "DEMO")
        self.assertEqual(snapshot.account.balance, 300.0)
        self.assertEqual(snapshot.account.equity, 280.0)
        self.assertEqual(snapshot.account.server, "Clear-Demo")
        self.assertEqual(fake.initialize_calls, [{}])
        source = inspect.getsource(MetaTrader5Gateway)
        self.assertNotIn("password", source.casefold())
        self.assertNotIn("order_send", source)

    def test_real_account_is_visibly_distinguished(self) -> None:
        snapshot = MetaTrader5Gateway(FakeMT5(trade_mode=2)).connect()
        self.assertEqual(snapshot.account.mode, "REAL")

    def test_visible_symbols_are_loaded_from_terminal(self) -> None:
        gateway = MetaTrader5Gateway(FakeMT5())
        gateway.connect()
        self.assertEqual(gateway.symbols(), ["WDOV26", "WINV26"])

    def test_candles_are_converted_to_internal_model(self) -> None:
        gateway = MetaTrader5Gateway(FakeMT5())
        gateway.connect()
        candles = gateway.candles("WINV26", "5m", limit=200)
        self.assertEqual(len(candles), 200)
        self.assertEqual(candles[0].open, 100.0)
        self.assertEqual(candles[-1].volume, 224.0)
        self.assertTrue(all(candle.close_time is not None for candle in candles))

    def test_positions_and_history_are_read_only_views(self) -> None:
        gateway = MetaTrader5Gateway(FakeMT5())
        gateway.connect()
        self.assertEqual(gateway.positions()[0]["profit"], 20.0)
        history = gateway.history(
            datetime(2026, 8, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 27, tzinfo=timezone.utc),
        )
        self.assertEqual(history[0]["profit"], 25.0)

    def test_initialize_failure_is_actionable(self) -> None:
        with self.assertRaisesRegex(MT5UnavailableError, "Abra o MT5"):
            MetaTrader5Gateway(FakeMT5(initialize_ok=False)).connect()

    def test_disconnect_closes_only_the_python_bridge(self) -> None:
        fake = FakeMT5()
        gateway = MetaTrader5Gateway(fake)
        gateway.connect()
        gateway.disconnect()
        self.assertEqual(fake.shutdown_calls, 1)
        self.assertFalse(gateway.connected)


if __name__ == "__main__":
    unittest.main()
