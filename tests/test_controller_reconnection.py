from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.controller import TradingController
from prime_ai_trader.core.models import Direction, Market, Signal, SignalState
from prime_ai_trader.crypto.binance import BinanceSpotProvider
from prime_ai_trader.news.provider import NewsItem
from tests.helpers import synthetic_candles


class _FakeSocket:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def recv(self):
        return self.payload


class ControllerReconnectTests(unittest.TestCase):
    def test_risk_news_is_warning_by_default(self) -> None:
        risky = NewsItem("Fed interest rate decision", "https://example.test", datetime.now(timezone.utc), "NEUTRA", True)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            with patch.object(controller.binance, "fetch_candles", return_value=synthetic_candles(180)), patch.object(controller.news_provider, "fetch", return_value=[risky]):
                snapshot = controller.analyze()
            self.assertFalse(snapshot.signal.blockers)
            self.assertTrue(snapshot.signal.warnings)
            self.assertNotEqual(snapshot.signal.state, SignalState.BLOCKED)

    def test_risk_news_can_be_strictly_blocked(self) -> None:
        risky = NewsItem("Fed interest rate decision", "https://example.test", datetime.now(timezone.utc), "NEUTRA", True)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            controller.settings.strict_risk_blocks = True
            with patch.object(controller.binance, "fetch_candles", return_value=synthetic_candles(180)), patch.object(controller.news_provider, "fetch", return_value=[risky]):
                snapshot = controller.analyze()
            self.assertTrue(snapshot.signal.blockers)
            self.assertEqual(snapshot.signal.state, SignalState.BLOCKED)

    def test_weak_backtest_warns_without_blocking_live_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            key = (Market.CRYPTO.value, "BTC/USDT", "5m", 5)
            controller._quality_gate[key] = SimpleNamespace(
                quality="FRACA", accuracy=0.42, directional_operations=31,
            )
            original = Signal(Direction.BUY, SignalState.CONFIRMED, 82, {"COMPRA": 0.8}, 100.0, 5)
            guarded = controller._apply_quality_gate(original, *key)
            self.assertEqual(guarded.direction, Direction.BUY)
            self.assertEqual(guarded.state, SignalState.CONFIRMED)
            self.assertFalse(guarded.blockers)
            self.assertIn("Backtest fora da amostra", guarded.warnings[0])

    def test_controller_switches_asset_and_timeframe_without_stale_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            controller.settings.market = Market.CRYPTO.value
            controller.settings.crypto_symbol = "ETH/USDT"
            controller.settings.timeframe = "15m"
            candles = synthetic_candles(180)
            with patch.object(controller.binance, "fetch_candles", return_value=candles), patch.object(controller.news_provider, "fetch", return_value=[]):
                snapshot = controller.analyze()
            self.assertEqual(snapshot.symbol, "ETH/USDT")
            self.assertEqual(snapshot.timeframe, "15m")
            self.assertEqual(len(snapshot.candles), 180)

    def test_websocket_reconnects_after_transient_failure(self) -> None:
        provider = BinanceSpotProvider()
        stop_event = asyncio.Event()
        received = []
        payload = json.dumps({"k": {"t": 1000, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10", "T": 2000, "q": "15", "n": 3, "V": "6", "x": True}})
        calls = {"count": 0}

        def connect(*_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("falha temporária")
            return _FakeSocket(payload)

        def callback(candle):
            received.append(candle)
            stop_event.set()

        async def no_wait(_seconds):
            return None

        async def exercise():
            with patch("websockets.connect", side_effect=connect), patch("prime_ai_trader.crypto.binance.asyncio.sleep", side_effect=no_wait):
                await provider.stream_candles("BTC/USDT", "1m", callback, stop_event)

        asyncio.run(exercise())
        self.assertEqual(calls["count"], 2)
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].closed)


if __name__ == "__main__":
    unittest.main()
