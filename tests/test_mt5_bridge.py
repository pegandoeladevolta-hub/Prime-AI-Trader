from __future__ import annotations

import unittest
from types import SimpleNamespace

from prime_ai_trader.platform.mt5 import MT5Bridge, MT5ExecutionError


class _Result:
    def __init__(self, **values):
        self.__dict__.update(values)

    def _asdict(self):
        return dict(self.__dict__)


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self):
        self.requests = []
        self.shutdown_called = False

    def initialize(self, **kwargs):
        return True

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return (0, "ok")

    def account_info(self):
        return SimpleNamespace(
            login=12345, server="CLEAR DEMO", name="Teste", currency="BRL",
            balance=10000.0, equity=10020.0, margin=100.0,
            margin_free=9920.0, trade_allowed=True,
        )

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol, visible=True, filling_mode=self.ORDER_FILLING_RETURN)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=100.5, bid=100.4)

    def symbol_select(self, symbol, visible):
        return True

    def order_check(self, request):
        return SimpleNamespace(retcode=0, comment="Done")

    def order_send(self, request):
        self.requests.append(dict(request))
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE, order=111, deal=222,
            volume=request["volume"], price=request["price"], comment="Done",
        )

    def positions_get(self, **kwargs):
        if "ticket" in kwargs:
            return (_Result(
                ticket=kwargs["ticket"], symbol="WINQ26", volume=1.0,
                type=self.POSITION_TYPE_BUY,
            ),)
        return ()

    def history_deals_get(self, start, end):
        return ()

    def symbols_get(self):
        return (SimpleNamespace(name="WINQ26"), SimpleNamespace(name="WDOQ26"))


class MT5BridgeTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeMT5()
        self.bridge = MT5Bridge()
        self.bridge._mt5 = self.fake

    def test_connect_uses_authenticated_terminal_account(self):
        account = self.bridge.connect()
        self.assertEqual(account.login, 12345)
        self.assertEqual(account.server, "CLEAR DEMO")
        self.assertTrue(account.trade_allowed)

    def test_real_order_is_blocked_until_explicitly_armed(self):
        self.bridge.connect()
        with self.assertRaises(MT5ExecutionError):
            self.bridge.buy("WINQ26", 1.0, armed=False)
        self.assertEqual(self.fake.requests, [])

    def test_buy_sends_one_checked_market_order_when_armed(self):
        self.bridge.connect()
        result = self.bridge.buy("WINQ26", 1.0, sl=99.0, tp=102.0, armed=True)
        self.assertTrue(result.ok)
        self.assertEqual(result.deal, 222)
        self.assertEqual(len(self.fake.requests), 1)
        self.assertEqual(self.fake.requests[0]["type"], self.fake.ORDER_TYPE_BUY)
        self.assertEqual(self.fake.requests[0]["comment"], "Prime Trader")

    def test_close_position_sends_opposite_side(self):
        self.bridge.connect()
        result = self.bridge.close_position(777, armed=True)
        self.assertTrue(result.ok)
        self.assertEqual(self.fake.requests[-1]["position"], 777)
        self.assertEqual(self.fake.requests[-1]["type"], self.fake.ORDER_TYPE_SELL)


if __name__ == "__main__":
    unittest.main()
