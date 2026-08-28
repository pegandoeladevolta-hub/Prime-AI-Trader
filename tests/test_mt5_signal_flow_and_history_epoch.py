from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prime_ai_trader.app.mt5_history import initialize_mt5_history_epoch
from prime_ai_trader.core.models import Candle, Direction, Signal, SignalState
from prime_ai_trader.database.repository import Repository
from prime_ai_trader.platform.mt5_positions import MT5Bridge


class MT5SignalFlowAndHistoryEpochTests(unittest.TestCase):
    def test_stream_emits_closed_candle_before_new_open_candle(self):
        base = datetime(2026, 8, 27, 22, 0, tzinfo=timezone.utc)
        older = Candle(
            open_time=base - timedelta(minutes=1), open=99, high=100, low=98,
            close=99.5, volume=10, close_time=base, closed=True,
        )
        open_candle = Candle(
            open_time=base, open=100, high=101, low=99.5,
            close=100.5, volume=12, closed=False,
        )
        closed_candle = Candle(
            open_time=base, open=100, high=102, low=99.5,
            close=101.5, volume=18, close_time=base + timedelta(minutes=1),
            closed=True,
        )
        new_candle = Candle(
            open_time=base + timedelta(minutes=1), open=101.5, high=101.8,
            low=101.2, close=101.6, volume=2, closed=False,
        )

        bridge = MT5Bridge.__new__(MT5Bridge)
        snapshots = [
            [older, open_candle],
            [older, closed_candle, new_candle],
        ]
        call_index = {"value": 0}

        def fake_fetch(symbol, timeframe, limit=3):
            index = min(call_index["value"], len(snapshots) - 1)
            call_index["value"] += 1
            return snapshots[index]

        bridge.fetch_candles = fake_fetch
        stop = threading.Event()
        received = []

        def callback(candle):
            received.append((candle.open_time, candle.closed, candle.close))
            if candle.open_time == new_candle.open_time:
                stop.set()

        asyncio.run(asyncio.wait_for(
            bridge.stream_candles("USDJPY", "1m", callback, stop),
            timeout=3.0,
        ))

        self.assertGreaterEqual(len(received), 3)
        self.assertEqual(received[0][0], base)
        self.assertFalse(received[0][1])
        self.assertEqual(received[1][0], base)
        self.assertTrue(received[1][1])
        self.assertEqual(received[1][2], 101.5)
        self.assertEqual(received[2][0], base + timedelta(minutes=1))
        self.assertFalse(received[2][1])

    def test_history_epoch_clears_legacy_once_and_preserves_new_mt5_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = Repository(Path(tmp) / "prime.db")
            signal = Signal(
                direction=Direction.BUY,
                state=SignalState.CONFIRMED,
                score=80,
                probabilities={"COMPRA": 0.8, "VENDA": 0.2},
                entry=100.0,
                horizon_minutes=1,
            )
            signal_id = repository.save_signal(
                signal, "Forex", "USDJPY", "1m", {}, "PRICE ACTION",
                platform="VEX", strategy="FOREX", sensitivity="RÁPIDO",
            )
            repository.record_decision({
                "event_type": "SINAL CONFIRMADO",
                "signal_id": signal_id,
                "market": "Forex",
                "symbol": "USDJPY",
                "timeframe": "1m",
                "platform": "VEX",
                "direction": "COMPRA",
                "state": "SINAL CONFIRMADO",
                "score": 80,
            })

            reset = initialize_mt5_history_epoch(repository)
            self.assertTrue(reset.reset)
            self.assertEqual(reset.deleted_signals, 1)
            self.assertEqual(reset.deleted_decisions, 1)
            self.assertEqual(repository.recent(10), [])
            self.assertEqual(repository.decision_history(10), [])

            repository.save_signal(
                signal, "Forex", "USDJPY", "1m", {}, "PRICE ACTION",
                platform="MT5", strategy="FOREX", sensitivity="RÁPIDO",
            )
            second = initialize_mt5_history_epoch(repository)
            self.assertFalse(second.reset)
            rows = repository.recent(10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["platform"], "MT5")


if __name__ == "__main__":
    unittest.main()
