from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from prime_ai_trader.crypto.binance import BinanceSpotProvider
from prime_ai_trader.forex.twelve_data import TwelveDataProvider
from prime_ai_trader.market.base import ProviderError


class ProviderUiContractTests(unittest.TestCase):
    @patch("prime_ai_trader.crypto.binance.get_json")
    def test_binance_parses_real_kline_shape(self, mocked) -> None:
        mocked.return_value = [[1499040000000, "1", "3", "0.5", "2", "10", 1499040059999, "20", 5, "6", "12", "0"]]
        candles = BinanceSpotProvider().fetch_candles("BTC/USDT", "1m", 1)
        self.assertEqual(candles[0].close, 2)
        self.assertEqual(candles[0].taker_buy_volume, 6)

    def test_forex_requires_key_with_clear_error(self) -> None:
        with self.assertRaisesRegex(ProviderError, "Configure a chave"):
            TwelveDataProvider("").fetch_candles("EUR/USD", "5m")

    def test_every_visible_button_declares_a_command(self) -> None:
        ui_dir = Path(__file__).parents[1] / "prime_ai_trader" / "ui"
        button_calls = 0
        for path in ui_dir.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Button":
                    button_calls += 1
                    self.assertTrue(any(keyword.arg == "command" for keyword in node.keywords), f"Botão sem command em {path.name}:{node.lineno}")
        self.assertGreater(button_calls, 10)


if __name__ == "__main__":
    unittest.main()

