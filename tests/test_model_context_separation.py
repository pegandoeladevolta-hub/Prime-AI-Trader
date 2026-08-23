from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from prime_ai_trader.app.controller import TradingController
from prime_ai_trader.core.models import Market


class ModelContextSeparationTests(unittest.TestCase):
    def test_model_context_contains_every_required_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"PRIME_AI_TRADER_DATA_HOME": temporary},
        ):
            controller = TradingController()
            context = controller.model_context()
        self.assertEqual(
            set(context),
            {"market", "symbol", "timeframe", "horizon_minutes", "strategy",
             "sensitivity", "mode", "feature_schema"},
        )

    def test_crypto_and_forex_never_share_model_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"PRIME_AI_TRADER_DATA_HOME": temporary},
        ):
            controller = TradingController()
            crypto = controller.model_context()
            controller.settings.market = Market.FOREX.value
            forex = controller.model_context()
        self.assertNotEqual(crypto["market"], forex["market"])
        self.assertNotEqual(crypto["symbol"], forex["symbol"])
        self.assertNotEqual(crypto["strategy"], forex["strategy"])

    def test_sensitivity_and_mode_produce_distinct_storage_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"PRIME_AI_TRADER_DATA_HOME": temporary},
        ):
            controller = TradingController()
            first = controller.model_context()
            controller.settings.sensitivity = "RÁPIDO"
            second = controller.model_context()
            controller.settings.mode = "PRICE ACTION"
            third = controller.model_context()
        self.assertNotEqual(controller.model_manager._context_key(first), controller.model_manager._context_key(second))
        self.assertNotEqual(controller.model_manager._context_key(second), controller.model_manager._context_key(third))


if __name__ == "__main__":
    unittest.main()
