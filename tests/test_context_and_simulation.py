from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from prime_ai_trader.app.controller import (
    SIMULATION_EXECUTION_MODE, TradingController,
)
from prime_ai_trader.core.models import Direction, Market, Signal, SignalState
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.news.provider import (
    AssetNewsContext, NewsItem, summarize_asset_news,
)
from tests.helpers import synthetic_candles


class CandleContextTests(unittest.TestCase):
    def test_open_candle_uses_prior_200_closed_candles(self) -> None:
        controller = TradingController.__new__(TradingController)
        controller.settings = type("Settings", (), {
            "horizon_minutes": 1, "sensitivity": "RÁPIDO", "mode": "CONFIRMAÇÃO",
        })()
        candles = synthetic_candles(201)
        candles[-1].closed = False
        with patch(
            "prime_ai_trader.app.controller.use_last_closed_candle_for_entry",
            return_value=True,
        ):
            chart, decision, next_entry = controller._live_analysis_windows(candles, "1m")
        self.assertEqual(len(chart), 200)
        self.assertEqual(len(decision), 200)
        self.assertTrue(next_entry)
        self.assertTrue(all(candle.closed for candle in decision))

    def test_open_candle_without_200_closed_candles_is_rejected(self) -> None:
        controller = TradingController.__new__(TradingController)
        controller.settings = type("Settings", (), {
            "horizon_minutes": 1, "sensitivity": "RÁPIDO", "mode": "CONFIRMAÇÃO",
        })()
        candles = synthetic_candles(200)
        candles[-1].closed = False
        with patch(
            "prime_ai_trader.app.controller.use_last_closed_candle_for_entry",
            return_value=True,
        ), self.assertRaisesRegex(ValueError, "200 candles analíticos fechados"):
            controller._live_analysis_windows(candles, "1m")


class AssetNewsContextTests(unittest.TestCase):
    def test_generic_feed_items_are_filtered_by_asset_relevance(self) -> None:
        now = datetime.now(timezone.utc)
        items = [
            NewsItem("Bitcoin rally gains momentum", "https://one.test", now, "POSITIVA", False, "Fonte A"),
            NewsItem("Crypto exchange hack causes losses", "https://two.test", now, "NEGATIVA", True, "Fonte B"),
            NewsItem("Ethereum adoption reaches record", "https://three.test", now, "POSITIVA", False, "Fonte C"),
        ]
        context, relevant = summarize_asset_news(
            items, "BTC/USDT", Market.CRYPTO.value, now=now,
        )
        self.assertEqual(len(relevant), 2)
        self.assertEqual(context.asset_specific_count, 1)
        self.assertEqual(context.market_wide_count, 1)
        self.assertEqual(context.high_risk_count, 1)
        self.assertNotIn("Ethereum", " ".join(item.title for item in relevant))

    def test_strong_crypto_news_conflict_can_block_direction(self) -> None:
        context = AssetNewsContext(
            symbol="BTC/USDT", label="NEGATIVO", summary="contexto negativo",
            relevant_count=3, asset_specific_count=3, market_wide_count=0,
            fresh_count=3, positive_count=0, negative_count=3, neutral_count=0,
            high_risk_count=0, latest_at=datetime.now(timezone.utc),
            latest_age_minutes=1.0, sources=["Fonte"], directional_bias="VENDA",
        )
        signal = Signal(
            Direction.BUY, SignalState.CONFIRMED, 84, {"COMPRA": 0.8}, 100.0, 1,
        )
        TradingController._apply_news_context(signal, context, strict=True)
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertEqual(signal.state, SignalState.BLOCKED)
        self.assertTrue(signal.blockers)


class SimulationSessionTests(unittest.TestCase):
    def test_simulation_stops_after_profit_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"XDG_DATA_HOME": temp},
        ):
            controller = TradingController()
            controller.settings.session_stop_loss = 50.0
            controller.settings.session_profit_target = 20.0
            controller.configure_execution_mode(SIMULATION_EXECUTION_MODE)
            completed = Signal(
                Direction.SELL, SignalState.CONFIRMED, 82, {"VENDA": 0.8}, 100.0, 1,
                payout_percent=80,
            )
            signal_id = controller.repository.save_signal(
                completed, Market.CRYPTO.value, "BTC/USDT", "1m", {"atr_14": 1.0},
                "CONFIRMAÇÃO", platform="SIMULAÇÃO", stake_amount=25.0,
            )
            controller.repository.set_result(signal_id, 99.0, "WIN")
            summary = controller.simulation_summary()
            self.assertEqual(summary.status, "META ATINGIDA")
            self.assertFalse(summary.can_open)
            self.assertEqual(summary.profit_loss, 20.0)

    def test_simulation_stops_after_session_loss_limit_and_keeps_signal_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"XDG_DATA_HOME": temp},
        ):
            controller = TradingController()
            controller.settings.session_stop_loss = 20.0
            controller.settings.session_profit_target = 50.0
            controller.settings.stake_amount = 20.0
            controller.configure_execution_mode(SIMULATION_EXECUTION_MODE)
            completed = Signal(
                Direction.BUY, SignalState.CONFIRMED, 80, {"COMPRA": 0.8}, 100.0, 1,
            )
            signal_id = controller.repository.save_signal(
                completed, Market.CRYPTO.value, "BTC/USDT", "1m", {"atr_14": 1.0},
                "CONFIRMAÇÃO", platform="SIMULAÇÃO", stake_amount=20.0,
            )
            controller.repository.set_result(signal_id, 99.0, "LOSS")
            summary = controller.simulation_summary()
            self.assertEqual(summary.status, "STOP ATINGIDO")
            self.assertFalse(summary.can_open)
            self.assertEqual(summary.profit_loss, -20.0)

            candles = synthetic_candles(200)
            indicators = calculate_all(candles_frame(candles))
            next_signal = Signal(
                Direction.SELL, SignalState.CONFIRMED, 85, {"VENDA": 0.8},
                candles[-1].close, 1,
            )
            saved = controller._record_signal(
                next_signal, Market.CRYPTO.value, "BTC/USDT", "1m",
                candles, indicators, "CONFIRMAÇÃO",
            )
            self.assertIsNone(saved)
            self.assertEqual(next_signal.direction, Direction.SELL)
            self.assertEqual(next_signal.state, SignalState.CONFIRMED)
            self.assertTrue(any("Simulação pausada" in item for item in next_signal.warnings))


if __name__ == "__main__":
    unittest.main()
