from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

from prime_ai_trader.core.models import CRYPTO_DEFAULTS, FOREX_DEFAULTS
from prime_ai_trader.crypto.binance import BinanceSpotProvider
from prime_ai_trader.economic_calendar.finnhub import FinnhubEconomicCalendar
from prime_ai_trader.forex.twelve_data import TwelveDataProvider
from prime_ai_trader.market.base import ProviderError
from prime_ai_trader.news.provider import GdeltNewsProvider, classify_text
from prime_ai_trader.ui.chart import CandleChart


class ProviderUiContractTests(unittest.TestCase):
    def test_news_risk_terms_use_word_boundaries(self) -> None:
        self.assertFalse(classify_text("Second quarter results")[1])
        self.assertTrue(classify_text("SEC lawsuit against exchange")[1])

    def test_finnhub_country_is_normalized_to_pair_currency(self) -> None:
        self.assertEqual(FinnhubEconomicCalendar._currency({"country": "US"}), "USD")
        self.assertEqual(FinnhubEconomicCalendar._currency({"country": "GB"}), "GBP")
        self.assertEqual(FinnhubEconomicCalendar._currency({"currency": "EUR", "country": "EU"}), "EUR")

    @patch("prime_ai_trader.crypto.binance.get_json")
    def test_binance_parses_real_kline_shape(self, mocked) -> None:
        mocked.return_value = [[1499040000000, "1", "3", "0.5", "2", "10", 1499040059999, "20", 5, "6", "12", "0"]]
        candles = BinanceSpotProvider().fetch_candles("BTC/USDT", "1m", 1)
        self.assertEqual(candles[0].close, 2)
        self.assertEqual(candles[0].taker_buy_volume, 6)

    def test_forex_requires_key_with_clear_error(self) -> None:
        with self.assertRaisesRegex(ProviderError, "Configure a chave"):
            TwelveDataProvider("").fetch_candles("EUR/USD", "5m")

    @patch("prime_ai_trader.forex.twelve_data.get_json")
    def test_forex_parses_twelve_data_candles(self, mocked) -> None:
        mocked.return_value = {
            "values": [
                {"datetime": "2026-08-20 12:01:00", "open": "1.10", "high": "1.12", "low": "1.09", "close": "1.11"},
                {"datetime": "2026-08-20 12:00:00", "open": "1.09", "high": "1.11", "low": "1.08", "close": "1.10"},
            ]
        }
        candles = TwelveDataProvider("test-key").fetch_candles("EUR/USD", "1m", 2)
        self.assertEqual(len(candles), 2)
        self.assertAlmostEqual(candles[-1].close, 1.11)

    @patch("prime_ai_trader.forex.twelve_data.get_json")
    def test_forex_reuses_cache_to_preserve_free_credits(self, mocked) -> None:
        mocked.return_value = {"values": [{"datetime": "2026-08-20 12:00:00", "open": "1.09", "high": "1.11", "low": "1.08", "close": "1.10"}]}
        provider = TwelveDataProvider("test-key")
        provider.fetch_candles("EUR/USD", "1m", 1)
        provider.fetch_candles("EUR/USD", "1m", 1)
        mocked.assert_called_once()

    @patch("prime_ai_trader.forex.twelve_data.get_json")
    def test_forex_credit_error_is_actionable(self, mocked) -> None:
        mocked.return_value = {"status": "error", "code": 429, "message": "API credits exhausted"}
        with self.assertRaisesRegex(ProviderError, "Limite de créditos"):
            TwelveDataProvider("test-key").fetch_candles("EUR/USD", "1m", 1)

    @patch("prime_ai_trader.crypto.binance.get_json")
    def test_crypto_list_prioritizes_liquid_usdt_pairs(self, mocked) -> None:
        mocked.side_effect = [
            {"symbols": [
                {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
                {"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
                {"symbol": "USDCUSDT", "baseAsset": "USDC", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
            ]},
            [
                {"symbol": "BTCUSDT", "quoteVolume": "9000000"},
                {"symbol": "ETHUSDT", "quoteVolume": "12000000"},
                {"symbol": "USDCUSDT", "quoteVolume": "999000000"},
            ],
        ]
        symbols = BinanceSpotProvider().list_symbols()
        self.assertEqual(symbols, ["ETH/USDT", "BTC/USDT"])

    def test_default_market_lists_are_not_artificially_tiny(self) -> None:
        self.assertGreaterEqual(len(CRYPTO_DEFAULTS), 25)
        self.assertGreaterEqual(len(FOREX_DEFAULTS), 25)

    @patch("prime_ai_trader.news.provider.get_json")
    def test_news_success_is_cached(self, mocked) -> None:
        mocked.return_value = {"articles": [{"title": "Bitcoin rally", "url": "https://example.test", "seendate": "20260820T120000", "domain": "example.test"}]}
        provider = GdeltNewsProvider(cache_seconds=60)
        self.assertEqual(len(provider.fetch("bitcoin", 1)), 1)
        self.assertEqual(len(provider.fetch("bitcoin", 1)), 1)
        mocked.assert_called_once()

    @patch("prime_ai_trader.news.provider.get_json", side_effect=ProviderError("offline"))
    def test_news_failure_uses_fast_cooldown(self, mocked) -> None:
        provider = GdeltNewsProvider(failure_cooldown_seconds=60)
        with self.assertRaisesRegex(ProviderError, "offline"):
            provider.fetch("bitcoin", 1)
        with self.assertRaisesRegex(ProviderError, "offline"):
            provider.fetch("ethereum", 1)
        mocked.assert_called_once()

    def test_crosshair_does_not_redraw_entire_chart(self) -> None:
        source = inspect.getsource(CandleChart._crosshair)
        self.assertNotIn("self.redraw()", source)
        self.assertIn('self.delete("crosshair")', source)

    def test_live_tick_uses_partial_chart_redraw(self) -> None:
        source = inspect.getsource(CandleChart.update_last_candle)
        self.assertIn("_schedule_live_redraw", source)
        self.assertNotIn("schedule_redraw(80)", source)

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
