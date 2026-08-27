from __future__ import annotations

import unittest
from types import SimpleNamespace

from prime_ai_trader.platform.mt5_robust import MT5Bridge


class FakeBrokerMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_INVALID_FILL = 10030

    def __init__(self):
        self.checked = []
        self.sent = []

    def initialize(self, **kwargs):
        return True

    def shutdown(self):
        return None

    def last_error(self):
        return (0, "ok")

    def account_info(self):
        return SimpleNamespace(
            login=1, server="DEMO", name="Tester", currency="USD",
            balance=10000.0, equity=10000.0, margin=0.0,
            margin_free=10000.0, trade_allowed=True,
        )

    def symbol_info(self, symbol):
        return SimpleNamespace(
            name=symbol,
            visible=True,
            filling_mode=self.SYMBOL_FILLING_FOK | self.SYMBOL_FILLING_IOC,
            trade_exemode=self.SYMBOL_TRADE_EXECUTION_MARKET,
            point=0.001,
            digits=3,
            trade_stops_level=10,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            description="US Dollar vs Japanese Yen",
            path="Forex\\Major",
            currency_base="USD",
            currency_profit="JPY",
            trade_mode=1,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=159.423, bid=159.421, last=159.422, time=0)

    def symbol_select(self, symbol, visible):
        return True

    def order_check(self, request):
        self.checked.append(dict(request))
        if request["type_filling"] == self.ORDER_FILLING_FOK:
            return SimpleNamespace(
                retcode=self.TRADE_RETCODE_INVALID_FILL,
                comment="Unsupported filling mode",
            )
        return SimpleNamespace(retcode=0, comment="Done")

    def order_send(self, request):
        self.sent.append(dict(request))
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            order=100, deal=200, volume=request["volume"],
            price=159.423, comment="Done",
        )

    def positions_get(self, **kwargs):
        return ()


class MT5FillingModeTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeBrokerMT5()
        self.bridge = MT5Bridge()
        self.bridge._mt5 = self.fake
        self.bridge.connected = True

    def test_retries_ioc_when_fok_is_rejected(self):
        result = self.bridge.buy("USDJPY", 0.46, armed=True)
        self.assertTrue(result.ok)
        self.assertGreaterEqual(len(self.fake.checked), 2)
        self.assertEqual(self.fake.checked[0]["type_filling"], self.fake.ORDER_FILLING_FOK)
        self.assertEqual(self.fake.checked[1]["type_filling"], self.fake.ORDER_FILLING_IOC)
        self.assertEqual(len(self.fake.sent), 1)
        self.assertEqual(self.fake.sent[0]["type_filling"], self.fake.ORDER_FILLING_IOC)
        # Market Execution não precisa do preço solicitado pelo cliente.
        self.assertNotIn("price", self.fake.sent[0])

    def test_manual_stop_and_target_are_points_not_absolute_prices(self):
        sl, tp = self.bridge.manual_protection_from_points(
            "USDJPY", "BUY", 40, 40,
        )
        self.assertEqual(sl, 159.383)
        self.assertEqual(tp, 159.463)

    def test_sell_points_are_mirrored(self):
        sl, tp = self.bridge.manual_protection_from_points(
            "USDJPY", "SELL", 40, 40,
        )
        self.assertEqual(sl, 159.461)
        self.assertEqual(tp, 159.381)


if __name__ == "__main__":
    unittest.main()
