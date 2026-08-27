from __future__ import annotations

import unittest
from types import SimpleNamespace

from prime_ai_trader.platform.mt5 import MT5ExecutionError
from prime_ai_trader.platform.mt5_positions import MT5Bridge


class FakeMT5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    TRADE_ACTION_SLTP = 6
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self) -> None:
        self.requests = []
        self.position = SimpleNamespace(
            ticket=321,
            symbol="USDJPY",
            type=self.POSITION_TYPE_BUY,
            volume=0.10,
            price_open=159.038,
            sl=159.000,
            tp=159.100,
            time=1_700_000_000,
        )

    def account_info(self):
        return SimpleNamespace(login=123)

    def positions_get(self, **kwargs):
        if int(kwargs.get("ticket", 0)) == int(self.position.ticket):
            return (self.position,)
        return ()

    def symbol_info(self, symbol):
        return SimpleNamespace(
            name=symbol,
            digits=3,
            point=0.001,
            trade_stops_level=10,
            trade_freeze_level=0,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=159.040, ask=159.042)

    def order_send(self, request):
        self.requests.append(dict(request))
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            order=0,
            deal=0,
            volume=0.0,
            price=0.0,
            comment="Done",
        )

    def last_error(self):
        return (0, "ok")


class PositionProtectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeMT5()
        self.bridge = MT5Bridge()
        self.bridge._mt5 = self.fake
        self.bridge.connected = True

    def test_buy_position_updates_sl_and_tp_with_sltp_action(self):
        result = self.bridge.modify_position_protection(
            321, sl=159.000, tp=159.100, armed=True,
        )
        self.assertTrue(result.ok)
        self.assertEqual(len(self.fake.requests), 1)
        request = self.fake.requests[0]
        self.assertEqual(request["action"], self.fake.TRADE_ACTION_SLTP)
        self.assertEqual(request["position"], 321)
        self.assertEqual(request["sl"], 159.000)
        self.assertEqual(request["tp"], 159.100)

    def test_buy_rejects_stop_above_current_bid(self):
        with self.assertRaisesRegex(MT5ExecutionError, "abaixo"):
            self.bridge.modify_position_protection(
                321, sl=159.050, tp=159.100, armed=True,
            )
        self.assertEqual(self.fake.requests, [])

    def test_rejects_protection_closer_than_broker_minimum(self):
        with self.assertRaisesRegex(MT5ExecutionError, "10 pontos"):
            self.bridge.modify_position_protection(
                321, sl=159.035, tp=159.100, armed=True,
            )
        self.assertEqual(self.fake.requests, [])

    def test_requires_execution_to_be_armed(self):
        with self.assertRaisesRegex(MT5ExecutionError, "desarmada"):
            self.bridge.modify_position_protection(
                321, sl=159.000, tp=159.100, armed=False,
            )


if __name__ == "__main__":
    unittest.main()
