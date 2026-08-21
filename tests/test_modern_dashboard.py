from __future__ import annotations

import inspect
import logging
import os
import unittest
from unittest.mock import MagicMock, patch

from prime_ai_trader.app.controller import TradingController
from prime_ai_trader.config.settings import AppSettings
from prime_ai_trader.ui.dashboard import INDICATOR_LAYOUT, PrimeAITraderApp, recent_signal_display
from prime_ai_trader.ui.theme import COLORS, configure_style


class ModernDashboardTests(unittest.TestCase):
    def test_reference_layout_has_modern_three_column_dashboard(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_ui)
        self.assertIn("self._build_left(content)", source)
        self.assertIn("self._build_center(content)", source)
        self.assertIn("self._build_right(content)", source)
        self.assertIn("PROTEGIDO", source)

    def test_original_operational_actions_remain_available(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_left)
        for handler in (
            "start_analysis", "pause_analysis", "refresh_analysis", "run_backtest",
            "train_ai", "run_radar", "refresh_symbols", "open_api_settings",
            "open_logs", "open_performance", "open_health", "clean_cache",
        ):
            self.assertIn(f"self.{handler}", source, f"Função ausente da interface: {handler}")

    def test_advanced_controls_preserve_payout_events_and_risk_blocking(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_left)
        for variable in ("self.payout_var", "self.impact_block_var", "self.strict_risk_blocks_var"):
            self.assertIn(variable, source)
        self.assertIn("AJUSTES AVANÇADOS", source)

    def test_sensitivity_modes_and_voice_controls_remain_visible(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_left)
        for item in ("CONSERVADOR", "EQUILIBRADO", "RÁPIDO", "PRICE ACTION", "self.audio_var",
                     "self.pre_voice_var", "self.confirmed_voice_var", "self.alert_voice_var"):
            self.assertIn(item, source)

    def test_chart_has_timeframe_shortcuts_and_all_existing_overlays(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_center)
        for item in ('"1m"', '"5m"', '"15m"', '"1h"', '"4h"', '"sr"', '"fibonacci"',
                     '"ema"', '"bollinger"', '"swings"', '"trend"', '"signals"'):
            self.assertIn(item, source)
        self.assertIn("_build_insights", source)

    def test_bottom_cards_match_requested_reference(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_insights)
        self.assertIn("Explicação da IA", source)
        self.assertIn("Últimos sinais", source)
        self.assertIn("Alertas de voz", source)

    def test_audio_card_is_compact_and_prioritizes_the_other_cards(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_insights)
        self.assertIn("grid_columnconfigure(0, weight=6)", source)
        self.assertIn("grid_columnconfigure(1, weight=4)", source)
        self.assertIn("grid_columnconfigure(2, weight=2)", source)
        self.assertIn("width=42, height=42", source)
        self.assertIn("width=118, height=22", source)

    def test_balanced_confirmation_configuration_remains_unchanged(self) -> None:
        settings = AppSettings()
        self.assertEqual(settings.sensitivity, "EQUILIBRADO")
        self.assertEqual(settings.mode, "CONFIRMAÇÃO")

    def test_right_panel_retains_signal_confidence_timer_news_and_reasoning(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._build_right)
        for item in ("SINAL DA IA", "Confiança", "TEMPO RESTANTE", "Motivos da análise", "NOTÍCIAS AO VIVO"):
            self.assertIn(item, source)

    def test_signal_history_uses_database_without_blocking_ui(self) -> None:
        source = inspect.getsource(PrimeAITraderApp._refresh_recent_signals)
        worker = source.split("def worker()", 1)[1].split("threading.Thread", 1)[0]
        self.assertIn("repository.recent(3)", worker)
        self.assertIn("_post_ui", worker)
        self.assertNotIn("self.after(", worker)

    def test_signal_history_formats_real_buy_win(self) -> None:
        hour, symbol, direction, result = recent_signal_display({
            "created_at": "2026-08-20T12:41:00", "symbol": "BTC/USDT", "direction": "COMPRA", "result": "WIN",
        })
        self.assertEqual((hour, symbol, direction, result), ("12:41", "BTC", "▲", "✓"))

    def test_signal_history_formats_real_sell_loss(self) -> None:
        hour, symbol, direction, result = recent_signal_display({
            "created_at": "2026-08-20T14:35:00", "symbol": "EUR/USD", "direction": "VENDA", "result": "LOSS",
        })
        self.assertEqual((hour, symbol, direction, result), ("14:35", "EUR", "▼", "✕"))

    def test_signal_history_never_fabricates_missing_data(self) -> None:
        self.assertEqual(recent_signal_display({}), ("--:--", "—", "—", "◷"))

    def test_modern_palette_keeps_distinct_trading_states(self) -> None:
        self.assertEqual(COLORS["bg"], "#03070C")
        self.assertNotEqual(COLORS["green"], COLORS["red"])
        self.assertNotEqual(COLORS["accent2"], COLORS["purple"])
        source = inspect.getsource(configure_style)
        for style in ("Backtest.TButton", "Train.TButton", "ActiveTimeframe.TButton"):
            self.assertIn(style, source)

    @unittest.skipUnless(os.name == "nt", "Smoke test visual executado no build Windows")
    def test_windows_dashboard_constructs_without_tkinter_errors(self) -> None:
        controller = MagicMock(spec=TradingController)
        controller.settings = AppSettings()
        controller.symbol.return_value = "BTC/USDT"
        controller.secrets = {}
        controller.logger = logging.getLogger("prime_ai_trader.tests.visual")
        app = None
        try:
            with patch.object(PrimeAITraderApp, "_apply_window_icon", lambda _self: None):
                app = PrimeAITraderApp(controller)
            app.update_idletasks()
            self.assertTrue(app.chart.winfo_exists())
            self.assertEqual(len(app.indicator_values), len(INDICATOR_LAYOUT))
            self.assertEqual(len(app.recent_signal_labels), 3)
            self.assertEqual(app.countdown_label.cget("text"), "--:--")
            self.assertIn("CONECTAR VEX INVEST", app.vex_button.cget("text"))
            self.assertEqual(int(app.audio_icon.cget("width")), 42)
            self.assertEqual(int(app.audio_wave.cget("width")), 118)
            self.assertEqual(app.audio_card.master.grid_columnconfigure(2)["weight"], 2)
            self.assertFalse(app._advanced_visible)
            app._toggle_advanced()
            self.assertTrue(app._advanced_visible)
            self.assertEqual(app.advanced_panel.winfo_manager(), "pack")
            app._set_timeframe("1m")
            self.assertEqual(controller.settings.timeframe, "1m")
            self.assertEqual(app.timeframe_buttons["1m"].cget("style"), "ActiveTimeframe.TButton")
        finally:
            if app is not None:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
