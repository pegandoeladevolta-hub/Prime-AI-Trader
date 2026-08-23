from __future__ import annotations

import inspect
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from prime_ai_trader.config.settings import AppSettings
from prime_ai_trader.core.models import Market
from prime_ai_trader.platform.bullex import (
    BULLEX_ALLOWED_HOSTS, BULLEX_CVM_ALERT_URL, BullexBrowserBridge,
    snapshot_from_bullex_visible,
)
from prime_ai_trader.platform.vex import VISIBLE_TRADEROOM_SCRIPT, _is_loopback_endpoint
from prime_ai_trader.ui.dashboard import PrimeAITraderApp


class BullexVisiblePlatformTests(unittest.TestCase):
    @staticmethod
    def _payload(url: str = "https://trade.bull-ex.com/traderoom") -> dict:
        return {
            "url": url, "login": False,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "candidates": [
                {"kind": "asset", "text": "XRP", "context": "asset trade", "selected": True, "y": 40},
                {"kind": "percent", "text": "82%", "context": "payout", "selected": False, "y": 80},
                {"kind": "timer", "text": "00:43", "context": "remaining expiration", "selected": False, "y": 90},
                {"kind": "period", "text": "1 min", "context": "expiration", "selected": False, "y": 100},
                {"kind": "price", "text": "0,5312", "context": "price asset", "selected": False, "y": 110},
            ],
        }

    def test_bullex_extracts_only_authorized_visible_market_fields(self) -> None:
        snapshot = snapshot_from_bullex_visible(self._payload())
        self.assertTrue(snapshot.authenticated)
        self.assertEqual(snapshot.platform_name, "BULLEX")
        self.assertEqual((snapshot.asset, snapshot.market), ("XRP/USDT", Market.CRYPTO.value))
        self.assertEqual((snapshot.payout_percent, snapshot.remaining_seconds, snapshot.horizon_minutes), (82, 43, 1))
        self.assertAlmostEqual(snapshot.price or 0, 0.5312)

    def test_bullex_public_home_is_not_mistaken_for_authenticated_traderoom(self) -> None:
        payload = self._payload("https://www.bullex.com.br/pt")
        payload["candidates"] = payload["candidates"][:2]
        self.assertFalse(snapshot_from_bullex_visible(payload).authenticated)

    def test_untrusted_bullex_domain_is_rejected(self) -> None:
        self.assertFalse(snapshot_from_bullex_visible(self._payload("https://bullex.example/trade")).authenticated)

    def test_bullex_is_opt_in_and_cvm_warning_is_embedded(self) -> None:
        settings = AppSettings()
        self.assertFalse(settings.platform_sync_enabled)
        self.assertFalse(settings.bullex_sync_authorized)
        self.assertIn("gov.br/cvm", BULLEX_CVM_ALERT_URL)
        source = inspect.getsource(PrimeAITraderApp.connect_vex)
        self.assertIn("bullex_sync_authorized", source)
        self.assertIn("não possui autorização", source)

    def test_bullex_uses_separate_profile_and_explicit_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge = BullexBrowserBridge(Path(temporary) / "bullex-browser", lambda _: None, lambda _: None)
        self.assertEqual(bridge.platform_name, "BULLEX")
        self.assertEqual(bridge.allowed_hosts, BULLEX_ALLOWED_HOSTS)
        self.assertIn("bullex-browser", str(bridge.profile_dir))

    def test_local_debug_transport_stays_restricted_to_loopback(self) -> None:
        self.assertTrue(_is_loopback_endpoint("ws://127.0.0.1:9222/devtools/page/1", 9222))
        self.assertFalse(_is_loopback_endpoint("ws://0.0.0.0:9222/devtools/page/1", 9222))
        self.assertFalse(_is_loopback_endpoint("wss://example.com:9222/devtools/page/1", 9222))

    def test_visible_script_never_clicks_or_reads_browser_secrets(self) -> None:
        lowered = VISIBLE_TRADEROOM_SCRIPT.lower()
        for forbidden in (".click(", "document.cookie", "localstorage", "sessionstorage", "input.value"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
