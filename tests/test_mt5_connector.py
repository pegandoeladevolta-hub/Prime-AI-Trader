from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from prime_ai_trader.platform.mt5 import (
    MT5TradingDisabledError,
    MT5UnavailableError,
    MetaTrader5Gateway,
)


class FakeResult(SimpleNamespace):
    pass


class FakeMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M3 = 3
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PLACED = 10008

    def __init__(self, *, initialize_ok: bool = True, trade_mode: int = 0) -> None:
        self.initialize_ok = initialize_ok
        self.trade_mode = trade_mode
        self.initialize_calls = []
        self.shutdown_calls = 0
        self.sent_requests = []
        self.position = SimpleNamespace(
            ticket=77, symbol="WINV26", type=self.POSITION_TYPE_BUY, volume=1.0,
            price_open=141000.0, price_current=141100.0, sl=140900.0,
            tp=141300.0, profit=20.0, magic=260826, comment="PrimeTrader",
        )

    def initialize(self, **kwargs):
        self.initialize_calls.append(kwargs)
        return self.initialize_ok

    def last_error(self):
        return (-1, "teste")

    def version(self):
        return (5, 5100, "27 Aug 2026")

    def terminal_info(self):
        return SimpleNamespace(
            connected=True, trade_allowed=True,
            name="MetaTrader 5", path="C:/MT5", build=5100,
        )

    def account_info(self):
        return SimpleNamespace(
            login=12345, trade_mode=self.trade_mode,
            balance=300.0, equity=280.0, profit=-20.0,
            margin=50.0, margin_free=230.0, currency="BRL",
            server="CLEAR PRD" if self.trade_mode == 2 else "CLEAR DEMO",
            company="Clear Corretora", trade_allowed=True, trade_expert=True,
        )

    def symbols_get(self):
        return (
            SimpleNamespace(name="WINV26", visible=True),
            SimpleNamespace(name="WDOV26", visible=True),
            SimpleNamespace(name="OCULTO", visible=False),
        )

    def symbol_info(self, symbol):
        if symbol not in {"WINV26", "WDOV26"}:
            return None
        return SimpleNamespace(
            name=symbol, visible=True, volume_min=1.0, volume_max=100.0,
            volume_step=1.0, filling_mode=self.ORDER_FILLING_FOK,
        )

    def symbol_select(self, symbol, selected):
        return bool(symbol and selected)

    def symbol_info_tick(self, symbol):
        if symbol not in {"WINV26", "WDOV26"}:
            return None
        return SimpleNamespace(bid=141000.0, ask=141005.0)

    def copy_rates_from_pos(self, symbol, timeframe, start, limit):
        del symbol, start
        seconds = int(timeframe) * 60
        base = 1_700_000_000
        return [
            {
                "time": base + index * seconds,
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "tick_volume": 25 + index,
                "real_volume": 0,
            }
            for index in range(limit)
        ]

    def positions_get(self, symbol=None, ticket=None):
        if ticket is not None:
            return (self.position,) if int(ticket) == self.position.ticket else ()
        if symbol is not None and symbol != self.position.symbol:
            return ()
        return (self.position,)

    def history_deals_get(self, date_from, date_to):
        del date_from, date_to
        return (SimpleNamespace(
            ticket=2, order=3, time=1_700_000_000, symbol="WINV26",
            type=0, entry=0, volume=1.0, price=141000.0, profit=25.0,
            commission=-0.5, swap=0.0, magic=260826, comment="PrimeTrader",
        ),)

    def order_check(self, request):
        return SimpleNamespace(retcode=0, comment="Done", request=request)

    def order_send(self, request):
        self.sent_requests.append(dict(request))
        return FakeResult(
            retcode=self.TRADE_RETCODE_DONE,
            order=1001,
            deal=2002,
            volume=float(request["volume"]),
            price=float(request["price"]),
            comment="Request executed",
            request_id=9,
        )

    def shutdown(self):
        self.shutdown_calls += 1


class MetaTrader5GatewayTests(unittest.TestCase):
    def test_connect_reuses_terminal_session_without_requesting_credentials(self) -> None:
        fake = FakeMT5(trade_mode=2)
        gateway = MetaTrader5Gateway(fake)
        snapshot = gateway.connect()
        self.assertEqual(snapshot.account.mode, "REAL")
        self.assertEqual(snapshot.account.login, 12345)
        self.assertEqual(snapshot.account.server, "CLEAR PRD")
        self.assertEqual(fake.initialize_calls, [{}])

    def test_visible_symbols_come_from_terminal(self) -> None:
        gateway = MetaTrader5Gateway(FakeMT5())
        gateway.connect()
        self.assertEqual(gateway.symbols(), ["WDOV26", "WINV26"])

    def test_candles_are_converted_to_internal_model(self) -> None:
        gateway = MetaTrader5Gateway(FakeMT5())
        gateway.connect()
        candles = gateway.candles("WINV26", "1m", limit=201)
        self.assertEqual(len(candles), 201)
        self.assertEqual(candles[0].open, 100.0)
        self.assertEqual(candles[-1].volume, 225.0)
        self.assertTrue(all(candle.close_time is not None for candle in candles))

    def test_history_reads_real_terminal_deals(self) -> None:
        gateway = MetaTrader5Gateway(FakeMT5())
        gateway.connect()
        history = gateway.history(
            datetime(2026, 8, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 27, tzinfo=timezone.utc),
        )
        self.assertEqual(history[0]["profit"], 25.0)
        self.assertEqual(history[0]["symbol"], "WINV26")

    def test_real_order_is_blocked_until_explicitly_enabled(self) -> None:
        fake = FakeMT5(trade_mode=2)
        gateway = MetaTrader5Gateway(fake)
        gateway.connect()
        with self.assertRaises(MT5TradingDisabledError):
            gateway.place_market_order("WINV26", "BUY", 1)
        self.assertEqual(fake.sent_requests, [])

    def test_buy_order_uses_order_check_and_order_send_after_enable(self) -> None:
        fake = FakeMT5(trade_mode=2)
        gateway = MetaTrader5Gateway(fake)
        gateway.connect()
        gateway.set_live_trading_enabled(True)
        result = gateway.place_market_order(
            "WINV26", "BUY", 1,
            stop_loss=140900.0, take_profit=141300.0,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.order, 1001)
        request = fake.sent_requests[-1]
        self.assertEqual(request["type"], fake.ORDER_TYPE_BUY)
        self.assertEqual(request["symbol"], "WINV26")
        self.assertEqual(request["sl"], 140900.0)
        self.assertEqual(request["tp"], 141300.0)

    def test_sell_order_uses_bid_price(self) -> None:
        fake = FakeMT5()
        gateway = MetaTrader5Gateway(fake)
        gateway.connect()
        gateway.set_live_trading_enabled(True)
        gateway.place_market_order("WINV26", "SELL", 2)
        request = fake.sent_requests[-1]
        self.assertEqual(request["type"], fake.ORDER_TYPE_SELL)
        self.assertEqual(request["price"], 141000.0)
        self.assertEqual(request["volume"], 2.0)

    def test_close_position_sends_opposite_side_with_position_ticket(self) -> None:
        fake = FakeMT5()
        gateway = MetaTrader5Gateway(fake)
        gateway.connect()
        gateway.set_live_trading_enabled(True)
        result = gateway.close_position(77)
        self.assertTrue(result.ok)
        request = fake.sent_requests[-1]
        self.assertEqual(request["position"], 77)
        self.assertEqual(request["type"], fake.ORDER_TYPE_SELL)
        self.assertEqual(request["price"], 141000.0)

    def test_initialize_failure_is_actionable(self) -> None:
        with self.assertRaisesRegex(MT5UnavailableError, "Abra o MT5"):
            MetaTrader5Gateway(FakeMT5(initialize_ok=False)).connect()

    def test_disconnect_also_relocks_live_trading(self) -> None:
        fake = FakeMT5()
        gateway = MetaTrader5Gateway(fake)
        gateway.connect()
        gateway.set_live_trading_enabled(True)
        gateway.disconnect()
        self.assertEqual(fake.shutdown_calls, 1)
        self.assertFalse(gateway.connected)
        self.assertFalse(gateway.live_trading_enabled)


if __name__ == "__main__":
    unittest.main()
