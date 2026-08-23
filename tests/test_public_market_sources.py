from __future__ import annotations

import inspect
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from prime_ai_trader.core.models import CRYPTO_DEFAULTS, PLATFORM_CRYPTO_DEFAULTS, Candle
from prime_ai_trader.crypto.binance import BinanceSpotProvider
from prime_ai_trader.crypto.public import CoinbaseSpotProvider, KrakenSpotProvider, ResilientCryptoProvider
from prime_ai_trader.economic_calendar.finnhub import PublicEconomicCalendar
from prime_ai_trader.forex.public import (
    AlphaVantageForexProvider, ForexLiveQuote, FrankfurterReferenceProvider,
    ResilientForexProvider, YahooForexProvider, merge_forex_quote,
)
from prime_ai_trader.market.base import ProviderError
from prime_ai_trader.news.provider import CompositeNewsProvider, NewsItem, RssNewsProvider, classify_text, market_news_query
from prime_ai_trader.ui.dashboard import PrimeAITraderApp
from tests.helpers import synthetic_candles


class PublicMarketSourceTests(unittest.TestCase):
    def test_platform_crypto_assets_are_prioritized_and_include_stellar(self) -> None:
        self.assertEqual(CRYPTO_DEFAULTS[:10], PLATFORM_CRYPTO_DEFAULTS)
        self.assertEqual(PLATFORM_CRYPTO_DEFAULTS[-1], "XLM/USDT")
        self.assertEqual(len(set(PLATFORM_CRYPTO_DEFAULTS)), 10)

    @patch("prime_ai_trader.crypto.binance.get_json")
    def test_binance_tries_official_public_mirror_after_network_error(self, mocked) -> None:
        mocked.side_effect = [ProviderError("Falha de comunicação"), []]
        self.assertEqual(BinanceSpotProvider().fetch_candles("BTC/USDT", "1m", 1), [])
        self.assertIn("data-api.binance.vision", mocked.call_args.args[0])

    @patch("prime_ai_trader.crypto.binance.get_json")
    def test_binance_does_not_rotate_hosts_after_rate_limit(self, mocked) -> None:
        mocked.side_effect = ProviderError("API respondeu HTTP 429")
        with self.assertRaisesRegex(ProviderError, "429"):
            BinanceSpotProvider().fetch_candles("BTC/USDT", "1m", 1)
        mocked.assert_called_once()

    @patch("prime_ai_trader.crypto.public.get_json")
    def test_coinbase_public_candle_schema_is_parsed(self, mocked) -> None:
        timestamp = int(datetime.now(timezone.utc).timestamp()) - 120
        mocked.return_value = [[timestamp, 99.0, 103.0, 100.0, 102.0, 7.0]]
        result = CoinbaseSpotProvider().fetch_candles("BTC/USDT", "1m", 1)
        self.assertEqual(result[0].open, 100.0)
        self.assertEqual(result[0].close, 102.0)
        self.assertIn("BTC-USD", mocked.call_args.args[0])

    @patch("prime_ai_trader.crypto.public.get_json")
    def test_kraken_public_ohlc_schema_is_parsed(self, mocked) -> None:
        timestamp = int(datetime.now(timezone.utc).timestamp()) - 120
        mocked.return_value = {
            "error": [],
            "result": {"XXBTZUSD": [[timestamp, "100", "104", "99", "103", "102", "8", 3]], "last": timestamp},
        }
        result = KrakenSpotProvider().fetch_candles("BTC/USDT", "1m", 1)
        self.assertEqual(result[0].close, 103.0)
        self.assertEqual(result[0].trades, 3)

    def test_crypto_automatically_uses_backup_when_binance_fails(self) -> None:
        primary = BinanceSpotProvider()
        backup = CoinbaseSpotProvider()
        provider = ResilientCryptoProvider(primary, [backup])
        expected = synthetic_candles(80)
        with patch.object(primary, "fetch_candles", side_effect=ProviderError("offline")), patch.object(
            backup, "fetch_candles", return_value=expected,
        ):
            result = provider.fetch_candles("BTC/USDT", "1m", 80)
        self.assertEqual(result, expected)
        self.assertIn("Coinbase", provider.last_provider_name)

    @patch("prime_ai_trader.forex.public.get_json")
    def test_yahoo_forex_works_without_api_key(self, mocked) -> None:
        timestamp = int(datetime.now(timezone.utc).timestamp()) - 120
        mocked.return_value = {
            "chart": {"error": None, "result": [{
                "timestamp": [timestamp],
                "indicators": {"quote": [{"open": [1.10], "high": [1.12], "low": [1.09], "close": [1.11], "volume": [None]}]},
            }]},
        }
        result = YahooForexProvider().fetch_candles("EUR/USD", "1m", 1)
        self.assertEqual(result[0].close, 1.11)
        self.assertIn("EURUSD=X", mocked.call_args.args[0])

    def test_resilient_forex_does_not_require_twelve_data_key(self) -> None:
        provider = ResilientForexProvider()
        expected = synthetic_candles(90)
        with patch.object(provider.yahoo, "fetch_candles", return_value=expected):
            result = provider.fetch_candles("EUR/USD", "1m", 90)
        self.assertEqual(result, expected)
        self.assertIn("público", provider.last_provider_name.lower())

    @patch("prime_ai_trader.forex.public.get_json")
    def test_yahoo_live_forex_quote_uses_real_market_metadata(self, mocked) -> None:
        observed = int(datetime.now(timezone.utc).timestamp())
        mocked.return_value = {
            "chart": {"error": None, "result": [{
                "meta": {"regularMarketPrice": 1.10567, "regularMarketTime": observed,
                         "bid": 1.10565, "ask": 1.10569},
                "timestamp": [observed - 30],
                "indicators": {"quote": [{"close": [1.10541]}]},
            }]},
        }
        quote = YahooForexProvider().fetch_live_quote("EUR/USD")
        self.assertEqual(quote.symbol, "EUR/USD")
        self.assertAlmostEqual(quote.price, 1.10567)
        self.assertEqual(quote.observed_at, datetime.fromtimestamp(observed, timezone.utc))
        self.assertAlmostEqual(quote.spread or 0, 0.00004)
        self.assertEqual(mocked.call_args.args[1]["range"], "1d")

    @patch("prime_ai_trader.forex.public.get_json")
    def test_yahoo_live_forex_quote_uses_latest_real_candle_when_metadata_is_old(self, mocked) -> None:
        observed = int(datetime.now(timezone.utc).timestamp())
        mocked.return_value = {
            "chart": {"result": [{
                "meta": {"regularMarketPrice": 1.101, "regularMarketTime": observed - 90},
                "timestamp": [observed - 60, observed],
                "indicators": {"quote": [{"close": [1.102, 1.10456]}]},
            }]},
        }
        quote = YahooForexProvider().fetch_live_quote("EUR/USD")
        self.assertEqual(quote.price, 1.10456)
        self.assertEqual(int(quote.observed_at.timestamp()), observed)

    @patch("prime_ai_trader.forex.public.get_json")
    def test_live_forex_quote_cache_prevents_redundant_public_requests(self, mocked) -> None:
        observed = int(datetime.now(timezone.utc).timestamp())
        mocked.return_value = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 1.12345, "regularMarketTime": observed},
        }]}}
        provider = YahooForexProvider(quote_cache_seconds=20)
        self.assertEqual(provider.fetch_live_quote("EUR/USD"), provider.fetch_live_quote("EUR/USD"))
        mocked.assert_called_once()

    @patch("prime_ai_trader.forex.public.get_json")
    def test_invalid_public_forex_quote_is_not_fabricated(self, mocked) -> None:
        mocked.return_value = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 0, "regularMarketTime": 1234},
        }]}}
        with self.assertRaisesRegex(ProviderError, "inválida"):
            YahooForexProvider().fetch_live_quote("EUR/USD")

    def test_live_forex_uses_free_public_source_without_twelve_data_credits(self) -> None:
        provider = ResilientForexProvider("optional-key")
        quote = ForexLiveQuote("EUR/USD", 1.12345, datetime.now(timezone.utc), "Yahoo")
        with patch.object(provider.yahoo, "fetch_live_quote", return_value=quote) as public_quote, patch.object(
            provider.twelve_data, "fetch_candles",
        ) as paid_history:
            self.assertEqual(provider.fetch_live_quote("EUR/USD"), quote)
        public_quote.assert_called_once_with("EUR/USD")
        paid_history.assert_not_called()
        self.assertEqual(provider.recommended_quote_ms, 10_000)

    def test_live_forex_quote_updates_existing_candle_without_fake_volume(self) -> None:
        opened = datetime(2026, 8, 20, 12, 10, tzinfo=timezone.utc)
        previous = Candle(opened, 1.101, 1.103, 1.100, 1.102, 0.0)
        quote = ForexLiveQuote("EUR/USD", 1.10456, opened + timedelta(seconds=30), "Yahoo")
        candle = merge_forex_quote(previous, quote, "1m")
        self.assertIsNotNone(candle)
        self.assertEqual(candle.open_time, opened)
        self.assertAlmostEqual(candle.open, 1.101)
        self.assertAlmostEqual(candle.high, 1.10456)
        self.assertEqual(candle.volume, 0.0)
        self.assertFalse(candle.closed)

    def test_live_forex_quote_opens_next_real_candle_in_correct_timeframe(self) -> None:
        opened = datetime(2026, 8, 20, 12, 9, tzinfo=timezone.utc)
        previous = Candle(opened, 1.10, 1.11, 1.09, 1.105, 0.0)
        quote = ForexLiveQuote("EUR/USD", 1.108, opened + timedelta(minutes=4, seconds=20), "Yahoo")
        candle = merge_forex_quote(previous, quote, "3m")
        self.assertEqual(candle.open_time, datetime(2026, 8, 20, 12, 12, tzinfo=timezone.utc))
        self.assertEqual(candle.open, 1.108)
        self.assertEqual(candle.close, 1.108)
        self.assertEqual(candle.volume, 0.0)

    def test_stale_forex_quote_never_overwrites_newer_candle(self) -> None:
        opened = datetime(2026, 8, 20, 12, 10, tzinfo=timezone.utc)
        previous = Candle(opened, 1.10, 1.11, 1.09, 1.105, 0.0)
        quote = ForexLiveQuote("EUR/USD", 1.08, opened - timedelta(minutes=1), "Yahoo")
        self.assertIsNone(merge_forex_quote(previous, quote, "1m"))

    def test_forex_falls_back_when_twelve_data_credits_are_exhausted(self) -> None:
        provider = ResilientForexProvider("test-key")
        expected = synthetic_candles(90)
        with patch.object(provider.twelve_data, "fetch_candles", side_effect=ProviderError("limite")), patch.object(
            provider.yahoo, "fetch_candles", return_value=expected,
        ):
            result = provider.fetch_candles("EUR/USD", "1m", 90)
        self.assertEqual(result, expected)
        self.assertIn("Fonte principal indisponível", provider.last_warning)

    @patch("prime_ai_trader.forex.public.get_json")
    def test_alpha_vantage_optional_forex_schema_is_parsed(self, mocked) -> None:
        mocked.return_value = {"Time Series FX (5min)": {
            "2026-08-20 12:00:00": {"1. open": "1.1", "2. high": "1.12", "3. low": "1.09", "4. close": "1.11"},
        }}
        result = AlphaVantageForexProvider("free-key").fetch_candles("EUR/USD", "5m", 1)
        self.assertAlmostEqual(result[0].close, 1.11)

    @patch("prime_ai_trader.forex.public.get_json")
    def test_frankfurter_is_daily_reference_not_fake_intraday(self, mocked) -> None:
        mocked.return_value = {"rates": {"USD": 1.105}}
        provider = FrankfurterReferenceProvider()
        self.assertAlmostEqual(provider.fetch_reference_rate("EUR/USD"), 1.105)
        self.assertAlmostEqual(provider.fetch_reference_rate("EUR/USD"), 1.105)
        mocked.assert_called_once()

    @patch("prime_ai_trader.economic_calendar.finnhub.get_json")
    def test_public_economic_calendar_is_cached_for_one_hour(self, mocked) -> None:
        mocked.return_value = [{
            "title": "Federal Funds Rate", "country": "USD",
            "date": "2026-08-20T12:30:00-04:00", "impact": "High",
        }]
        provider = PublicEconomicCalendar()
        result = provider.fetch(date(2026, 8, 20), date(2026, 8, 21))
        self.assertEqual(result[0].currency, "USD")
        self.assertEqual(result[0].impact, "HIGH")
        provider.fetch(date(2026, 8, 20), date(2026, 8, 21))
        mocked.assert_called_once()

    @patch("prime_ai_trader.news.provider.get_text")
    def test_rss_news_titles_and_sentiment_are_parsed(self, mocked) -> None:
        mocked.return_value = (
            "<rss><channel><item><title>Bitcoin rally reaches record</title>"
            "<link>https://example.test/story</link>"
            "<pubDate>Thu, 20 Aug 2026 12:00:00 +0000</pubDate>"
            "</item></channel></rss>"
        )
        result = RssNewsProvider("Teste", "https://example.test/rss").fetch("bitcoin")
        self.assertEqual(result[0].sentiment, "POSITIVA")
        self.assertEqual(result[0].source, "Teste")

    def test_news_remains_available_when_gdelt_is_offline(self) -> None:
        provider = CompositeNewsProvider()
        item = NewsItem("Bitcoin em alta", "https://example.test", datetime.now(timezone.utc), "POSITIVA", False, "Google")
        with patch.object(provider.gdelt, "fetch", side_effect=ProviderError("offline")), patch.object(
            provider.google, "fetch", return_value=[item],
        ), patch.object(provider.cointelegraph, "fetch", return_value=[]), patch.object(
            provider.coindesk, "fetch", return_value=[],
        ):
            result = provider.fetch('(\"Bitcoin\" OR BTC OR cryptocurrency)', 5)
        self.assertEqual(result, [item])
        self.assertIn("Google Notícias", provider.last_sources)

    def test_market_news_search_expands_asset_name(self) -> None:
        self.assertIn("Stellar", market_news_query("XLM/USDT", "Criptomoedas"))
        self.assertIn("forex", market_news_query("EUR/USD", "Forex"))

    def test_generic_exchange_word_does_not_create_constant_yellow_warning(self) -> None:
        self.assertFalse(classify_text("Crypto exchange expands services")[1])

    def test_interface_no_longer_blocks_forex_without_a_key(self) -> None:
        source = inspect.getsource(PrimeAITraderApp.start_analysis)
        self.assertNotIn("twelve_data_key", source)

    def test_interface_has_live_news_and_manual_refresh(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_right)
        self.assertIn("NOTÍCIAS AO VIVO", source)
        self.assertIn("refresh_news_panel", source)


if __name__ == "__main__":
    unittest.main()
