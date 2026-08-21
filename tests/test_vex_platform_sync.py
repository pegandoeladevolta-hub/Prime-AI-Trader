from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from prime_ai_trader.app.controller import TradingController
from prime_ai_trader.config.settings import AppSettings
from prime_ai_trader.core.models import Direction, Market, Signal, SignalState
from prime_ai_trader.features.builder import build_features
from prime_ai_trader.fibonacci.auto import automatic_fibonacci
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.platform.vex import (
    VISIBLE_TRADEROOM_SCRIPT, VexPlatformSnapshot, _is_loopback_endpoint,
    compare_platform_market, normalize_vex_asset, parse_localized_price,
    parse_vex_countdown, parse_vex_percent, snapshot_from_visible,
)
from prime_ai_trader.priceaction.structure import analyze_structure
from prime_ai_trader.signals.engine import SignalEngine
from prime_ai_trader.ui.dashboard import PrimeAITraderApp
from tests.helpers import synthetic_candles


class VexVisiblePlatformTests(unittest.TestCase):
    def _snapshot(self, **changes) -> VexPlatformSnapshot:
        values = {
            "observed_at": datetime.now(timezone.utc),
            "url": "https://vexinvest.com/traderoom",
            "authenticated": True,
            "asset": "BTC/USDT",
            "market": Market.CRYPTO.value,
            "payout_percent": 82,
            "remaining_seconds": 43,
            "horizon_minutes": 1,
            "price": 100.0,
            "otc": False,
        }
        values.update(changes)
        return VexPlatformSnapshot(**values)

    def test_all_ten_platform_cryptocurrencies_are_normalized(self) -> None:
        assets = {
            "BITCOIN": "BTC/USDT", "LITECOIN": "LTC/USDT",
            "CARDANO": "ADA/USDT", "BNB": "BNB/USDT",
            "XRP": "XRP/USDT", "ETHEREUM": "ETH/USDT",
            "SOLANA": "SOL/USDT", "DOGE": "DOGE/USDT",
            "SUI": "SUI/USDT", "STELLAR": "XLM/USDT",
        }
        for label, expected in assets.items():
            with self.subTest(asset=label):
                self.assertEqual(normalize_vex_asset(label), (expected, Market.CRYPTO.value, False))

    def test_crypto_pair_is_normalized_to_public_usdt_symbol(self) -> None:
        self.assertEqual(normalize_vex_asset("ETH/USD"), ("ETH/USDT", Market.CRYPTO.value, False))

    def test_forex_pair_formats_are_normalized(self) -> None:
        for item in ("EUR/USD", "EUR-USD", "EURUSD", "eur / usd"):
            with self.subTest(pair=item):
                self.assertEqual(normalize_vex_asset(item), ("EUR/USD", Market.FOREX.value, False))

    def test_otc_is_recognized_without_pretending_to_be_public_market(self) -> None:
        self.assertEqual(normalize_vex_asset("EUR/USD OTC"), ("EUR/USD", Market.FOREX.value, True))

    def test_unknown_asset_is_not_fabricated(self) -> None:
        self.assertEqual(normalize_vex_asset("SALDO DISPONÍVEL"), (None, None, False))

    def test_reasonable_visible_payout_is_parsed(self) -> None:
        self.assertEqual(parse_vex_percent("Lucro 82%"), 82)
        self.assertEqual(parse_vex_percent("74,50%"), 74)

    def test_out_of_range_payout_is_rejected(self) -> None:
        for item in ("3%", "120%", "82", "—"):
            with self.subTest(value=item):
                self.assertIsNone(parse_vex_percent(item))

    def test_visible_minute_countdown_is_parsed(self) -> None:
        self.assertEqual(parse_vex_countdown("00:59"), 59)
        self.assertEqual(parse_vex_countdown("01:15"), 75)

    def test_visible_hour_countdown_is_parsed(self) -> None:
        self.assertEqual(parse_vex_countdown("1:02:03"), 3723)

    def test_invalid_countdown_is_rejected(self) -> None:
        for value in ("01:77", "2m", "0:99:02", "ontem"):
            with self.subTest(value=value):
                self.assertIsNone(parse_vex_countdown(value))

    def test_brazilian_price_format_is_parsed(self) -> None:
        self.assertAlmostEqual(parse_localized_price("67.298,20"), 67298.20)
        self.assertAlmostEqual(parse_localized_price("R$ 0,3045"), 0.3045)

    def test_international_price_format_is_parsed(self) -> None:
        self.assertAlmostEqual(parse_localized_price("67,298.20"), 67298.20)
        self.assertAlmostEqual(parse_localized_price("$ 1.08745"), 1.08745)

    def test_invalid_or_negative_price_is_rejected(self) -> None:
        self.assertIsNone(parse_localized_price("-24"))
        self.assertIsNone(parse_localized_price("saldo 50"))
        self.assertIsNone(parse_localized_price("0"))

    def test_visible_traderoom_snapshot_extracts_all_authorized_fields(self) -> None:
        payload = {
            "url": "https://vexinvest.com/traderoom",
            "login": False,
            "observed_at": "2026-08-21T12:00:00Z",
            "candidates": [
                {"kind": "asset", "text": "ETHEREUM", "context": "ativo mercado", "selected": True},
                {"kind": "percent", "text": "82%", "context": "lucro payout"},
                {"kind": "timer", "text": "00:43", "context": "tempo restante expiração"},
                {"kind": "period", "text": "1 minuto", "context": "expiração"},
                {"kind": "price", "text": "4.374,84", "context": "preço ativo"},
            ],
        }
        result = snapshot_from_visible(payload)
        self.assertTrue(result.authenticated)
        self.assertEqual(result.asset, "ETH/USDT")
        self.assertEqual(result.payout_percent, 82)
        self.assertEqual(result.remaining_seconds, 43)
        self.assertEqual(result.horizon_minutes, 1)
        self.assertAlmostEqual(result.price, 4374.84)

    def test_selected_asset_has_priority_over_asset_list(self) -> None:
        result = snapshot_from_visible({
            "url": "https://vexinvest.com/traderoom", "candidates": [
                {"kind": "asset", "text": "BITCOIN", "context": "ativo", "y": 80},
                {"kind": "asset", "text": "SOLANA", "context": "ativo", "selected": True, "y": 100},
            ],
        })
        self.assertEqual(result.asset, "SOL/USDT")

    def test_login_page_is_never_treated_as_authenticated(self) -> None:
        result = snapshot_from_visible({
            "url": "https://vexinvest.com/traderoom", "login": True,
            "candidates": [{"kind": "percent", "text": "95%", "context": "lucro"}],
        })
        self.assertFalse(result.authenticated)
        self.assertIsNone(result.payout_percent)

    def test_public_home_page_is_not_treated_as_live_traderoom(self) -> None:
        result = snapshot_from_visible({"url": "https://vexinvest.com/", "login": False})
        self.assertFalse(result.authenticated)

    def test_foreign_domain_is_rejected(self) -> None:
        result = snapshot_from_visible({"url": "https://fake-vex.example/traderoom", "login": False})
        self.assertFalse(result.authenticated)

    def test_expiration_uses_visible_platform_countdown(self) -> None:
        snapshot = self._snapshot(remaining_seconds=43)
        self.assertEqual(snapshot.expires_at, snapshot.observed_at + timedelta(seconds=43))

    def test_stale_platform_state_does_not_claim_real_time_alignment(self) -> None:
        stale = self._snapshot(observed_at=datetime.now(timezone.utc) - timedelta(seconds=20))
        self.assertFalse(stale.fresh())
        self.assertEqual(compare_platform_market(stale, Market.CRYPTO.value, "ETH/USDT", 100.0), [])

    def test_matching_asset_and_price_are_accepted(self) -> None:
        self.assertEqual(compare_platform_market(self._snapshot(), Market.CRYPTO.value, "BTC/USDT", 100.0), [])

    def test_wrong_platform_asset_prevents_misleading_signal(self) -> None:
        reasons = compare_platform_market(self._snapshot(asset="ETH/USDT"), Market.CRYPTO.value, "BTC/USDT", 100)
        self.assertTrue(any("Ativo diferente" in reason for reason in reasons))

    def test_otc_market_is_explicitly_explained(self) -> None:
        reasons = compare_platform_market(self._snapshot(otc=True), Market.CRYPTO.value, "BTC/USDT", 100)
        self.assertTrue(any("OTC" in reason for reason in reasons))

    def test_divergent_crypto_price_prevents_misleading_signal(self) -> None:
        reasons = compare_platform_market(self._snapshot(price=102), Market.CRYPTO.value, "BTC/USDT", 100)
        self.assertTrue(any("diverge" in reason for reason in reasons))

    def test_divergent_forex_price_has_stricter_tolerance(self) -> None:
        state = self._snapshot(asset="EUR/USD", market=Market.FOREX.value, price=1.103)
        reasons = compare_platform_market(state, Market.FOREX.value, "EUR/USD", 1.1)
        self.assertTrue(any("diverge" in reason for reason in reasons))

    def test_missing_platform_price_is_not_invented_or_blocked(self) -> None:
        reasons = compare_platform_market(self._snapshot(price=None), Market.CRYPTO.value, "BTC/USDT", 100)
        self.assertEqual(reasons, [])

    def test_debug_endpoint_accepts_only_dedicated_localhost_port(self) -> None:
        self.assertTrue(_is_loopback_endpoint("ws://127.0.0.1:9228/devtools/page/a", 9228))
        self.assertTrue(_is_loopback_endpoint("ws://localhost:9228/devtools/page/a", 9228))
        self.assertFalse(_is_loopback_endpoint("ws://example.com:9228/devtools/page/a", 9228))
        self.assertFalse(_is_loopback_endpoint("ws://127.0.0.1:9229/devtools/page/a", 9228))

    def test_browser_script_does_not_read_credentials_or_storage(self) -> None:
        for prohibited in ("document.cookie", "localStorage", "sessionStorage", "password.value", "input.value"):
            with self.subTest(field=prohibited):
                self.assertNotIn(prohibited, VISIBLE_TRADEROOM_SCRIPT)
        self.assertIn('input[type="password"]', VISIBLE_TRADEROOM_SCRIPT)

    def test_synchronization_is_opt_in_and_defaults_are_preserved(self) -> None:
        settings = AppSettings()
        self.assertFalse(settings.platform_sync_enabled)
        self.assertEqual(settings.sensitivity, "EQUILIBRADO")
        self.assertEqual(settings.mode, "CONFIRMAÇÃO")

    def test_dashboard_has_explicit_vex_connection_button(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_left)
        self.assertIn("CONECTAR VEX INVEST", source)
        self.assertIn("self.connect_vex", source)

    def test_countdown_no_longer_restarts_from_snapshot_refresh_time(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._start_countdown)
        self.assertNotIn("snapshot.generated_at.timestamp()", source)
        self.assertIn("snapshot.signal.created_at", source)
        self.assertIn("platform.expires_at", source)

    def test_untrained_technical_strength_is_not_called_ai_probability(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._render_signal)
        self.assertIn("Força técnica dominante", source)
        self.assertIn("signal.model_score is not None", source)

    def test_independent_confluence_categories_do_not_double_count_momentum(self) -> None:
        categories = SignalEngine._independent_confirmations([
            "MACD acima da linha de sinal", "Momentum comprador acelerando", "RSI comprador sem excesso",
        ])
        self.assertEqual(categories, {"momentum"})

    def test_higher_timeframe_conflict_prevents_balanced_confirmation(self) -> None:
        frame = candles_frame(synthetic_candles(220, seed=3))
        indicators = calculate_all(frame)
        structure = analyze_structure(indicators, float(indicators["atr_14"].iloc[-1]))
        manager = SimpleNamespace(is_compatible=lambda _: False)
        with patch("prime_ai_trader.signals.engine._higher_timeframe_bias", return_value=("BAIXA", "1h")):
            signal = SignalEngine(manager).generate(
                indicators, build_features(frame), structure, automatic_fibonacci(frame),
                1, "EQUILIBRADO", True, mode="CONFIRMAÇÃO",
            )
        self.assertEqual(signal.direction, Direction.WAIT)
        self.assertTrue(any("timeframe superior" in reason for reason in signal.waiting_reasons))

    def test_controller_holds_signal_when_vex_is_on_another_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            controller.settings.platform_sync_enabled = True
            controller.platform_snapshot = self._snapshot(asset="ETH/USDT")
            original = Signal(Direction.BUY, SignalState.CONFIRMED, 82, {"COMPRA": 0.7}, 100, 1)
            result = controller._apply_platform_alignment(original, Market.CRYPTO.value, "BTC/USDT", 100)
        self.assertEqual(result.direction, Direction.WAIT)
        self.assertIsNone(result.entry)
        self.assertTrue(any("Ativo diferente" in reason for reason in result.waiting_reasons))

    def test_disabled_platform_sync_never_changes_existing_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_DATA_HOME": temp}):
            controller = TradingController()
            controller.platform_snapshot = self._snapshot(asset="ETH/USDT")
            original = Signal(Direction.BUY, SignalState.CONFIRMED, 82, {"COMPRA": 0.7}, 100, 1)
            result = controller._apply_platform_alignment(original, Market.CRYPTO.value, "BTC/USDT", 100)
        self.assertEqual(result.direction, Direction.BUY)

    def test_news_refresh_preserves_the_original_analysis_clock(self) -> None:
        source = inspect.getsource(TradingController.refresh_news)
        self.assertNotIn("generated_at =", source)


if __name__ == "__main__":
    unittest.main()
