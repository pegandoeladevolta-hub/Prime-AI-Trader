from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timezone
from tkinter import messagebox, ttk

import pandas as pd

from ..app.controller import AnalysisSnapshot, TradingController
from ..audio.voice import VoiceService
from ..config.settings import app_data_dir
from ..core.models import CRYPTO_DEFAULTS, FOREX_DEFAULTS, Direction, Market, SignalState, TIMEFRAMES
from ..forex.public import merge_forex_quote
from ..platform.bullex import BULLEX_CVM_ALERT_URL, BullexBrowserBridge
from ..platform.vex import VexBrowserBridge, VexPlatformSnapshot, compare_platform_market, merge_vex_quote
from ..priceaction.professional import live_refresh_interval
from ..signals.timing import preserve_recent_confirmed_signal
from ..signals.engine import sensitivity_profile
from .chart import CandleChart, market_price_decimals
from .dialogs import (
    ApiSettingsDialog, BacktestDialog, HealthDialog, ManualResultDialog,
    PerformanceDialog, RadarDialog,
)
from .theme import COLORS, configure_style


INDICATOR_LAYOUT = [
    ("EMA", "ema"), ("RSI", "rsi"), ("MACD", "macd"), ("BOLLINGER", "bb"),
    ("STOCH", "stoch"), ("ADX", "adx"), ("ATR", "atr"), ("VWAP", "vwap"),
    ("OBV", "obv"), ("CCI", "cci"), ("WILLIAMS %R", "williams"), ("FIBONACCI", "fib"),
    ("VOLUME", "volume"), ("PRICE ACTION", "price_action"), ("NEWS", "news"),
]

LIVE_ANALYSIS_INTERVAL_SECONDS = 30
FOREX_POLL_INTERVAL_MS = 125_000
FOREX_QUOTE_RETRY_MS = 30_000


def voice_message_for_signal(signal, symbol: str, sensitivity: str, *,
                             strict_risk_blocks: bool, voice_confirmed: bool,
                             voice_pre_signal: bool, voice_alerts: bool) -> tuple[str, float] | None:
    """Prioriza sinais; avisos informativos não interrompem a leitura do mercado."""
    if signal.state == SignalState.CONFIRMED and voice_confirmed:
        return f"Sinal de {signal.direction.value.lower()} confirmado em {symbol}.", 8.0
    if signal.state == SignalState.FORMING and signal.direction != Direction.WAIT:
        fast_reading = sensitivity_profile(sensitivity).early_reading and voice_confirmed
        if fast_reading:
            return f"Leitura rápida de {signal.direction.value.lower()} em {symbol}. Sinal em formação.", 20.0
        if voice_pre_signal:
            return f"Possível sinal de {signal.direction.value.lower()} em {symbol}.", 20.0
    if signal.blockers and strict_risk_blocks and voice_alerts:
        return "Atenção. Evento de alto impacto. Operações temporariamente bloqueadas.", 300.0
    return None


def recent_signal_display(row: dict) -> tuple[str, str, str, str]:
    raw_time = str(row.get("created_at") or "")
    try:
        parsed = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        hour = parsed.astimezone().strftime("%H:%M") if parsed.tzinfo else parsed.strftime("%H:%M")
    except (TypeError, ValueError):
        hour = "--:--"
    symbol = str(row.get("symbol") or "—").split("/", 1)[0]
    direction = "▲" if row.get("direction") == "COMPRA" else "▼" if row.get("direction") == "VENDA" else "—"
    result = {"WIN": "✓", "LOSS": "✕", "DRAW": "="}.get(row.get("result"), "◷")
    return hour, symbol, direction, result


class PrimeAITraderApp(tk.Tk):
    def __init__(self, controller: TradingController) -> None:
        super().__init__()
        self.controller = controller
        self.voice = VoiceService()
        self.title("PRIME AI TRADER")
        self.geometry("1660x960")
        self.minsize(1220, 760)
        self.configure(bg=COLORS["bg"])
        configure_style(self)
        self._apply_window_icon()
        self._stop_event = threading.Event()
        self._stream_thread: threading.Thread | None = None
        self._task_running = False
        self._analysis_active = False
        self._analysis_token = 0
        self._selection_job = None
        self._forex_poll_job = None
        self._forex_quote_job = None
        self._forex_quote_running = False
        self._live_ui_job = None
        self._pending_live_candle = None
        self._health_job = None
        self._health_running = False
        self._last_live_analysis = 0.0
        self._last_voice_signature = None
        self._forex_prompted = False
        self._countdown_job = None
        self._countdown_signature = None
        self._countdown_target: float | None = None
        self._platform_bridge: VexBrowserBridge | None = None
        self._platform_snapshot: VexPlatformSnapshot | None = None
        self._platform_change_job = None
        self._news_refresh_job = None
        self._news_refresh_running = False
        self._history_refresh_running = False
        self._advanced_visible = False
        self._ui_events = queue.Queue()
        self._ui_events_job = None
        self._build_variables()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._ui_events_job = self.after(25, self._drain_ui_events)
        self.after(500, self._load_health)

    def _build_variables(self) -> None:
        settings = self.controller.settings
        self.market_var = tk.StringVar(value=settings.market)
        self.symbol_var = tk.StringVar(value=self.controller.symbol())
        self.timeframe_var = tk.StringVar(value=settings.timeframe)
        self.horizon_var = tk.StringVar(value=str(settings.horizon_minutes))
        self.payout_var = tk.StringVar(value=str(settings.payout_percent))
        self.stake_var = tk.StringVar(value=f"{settings.stake_amount:.2f}")
        self.platform_var = tk.StringVar(value=settings.platform_name)
        self.sensitivity_var = tk.StringVar(value=settings.sensitivity)
        self.profile_hint_var = tk.StringVar(value=sensitivity_profile(settings.sensitivity).description)
        self.mode_var = tk.StringVar(value=settings.mode)
        self.audio_var = tk.BooleanVar(value=settings.audio_enabled)
        self.audio_volume_var = tk.IntVar(value=settings.audio_volume)
        self.pre_voice_var = tk.BooleanVar(value=settings.voice_pre_signal)
        self.confirmed_voice_var = tk.BooleanVar(value=settings.voice_confirmed)
        self.alert_voice_var = tk.BooleanVar(value=settings.voice_alerts)
        self.impact_block_var = tk.StringVar(value=str(settings.high_impact_block_minutes))
        self.strict_risk_blocks_var = tk.BooleanVar(value=settings.strict_risk_blocks)
        self.status_var = tk.StringVar(value="Pronto para iniciar")
        self.ohlc_var = tk.StringVar(value="OHLC aparecerá ao mover o cursor no gráfico")
        self.context_var = tk.StringVar(value="SELECIONE UM ATIVO")
        self.updated_var = tk.StringVar(value="Aguardando análise")
        self.score_var = tk.DoubleVar(value=0)
        self.platform_status_var = tk.StringVar(
            value=f"{settings.platform_name} não conectada • pagamento manual"
        )

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_header()
        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        self._build_left(content)
        self._build_center(content)
        self._build_right(content)
        footer = tk.Frame(self, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 9))
        ttk.Label(footer, text="●", style="Muted.TLabel", foreground=COLORS["green"], font=("Segoe UI", 11)).pack(side="left", padx=(11, 3), pady=6)
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel", font=("Segoe UI", 9)).pack(side="left")
        ttk.Label(footer, text="◈ PROTEGIDO", style="Muted.TLabel", foreground=COLORS["text"]).pack(side="right", padx=(8, 12))
        ttk.Label(footer, text="VERSÃO 1.2.1", style="Muted.TLabel").pack(side="right", padx=12)
        self.task_progress = ttk.Progressbar(footer, mode="indeterminate", length=116)
        self.task_progress.pack(side="right", padx=8)

    def _build_header(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(16, 8))
        header.grid(row=0, column=0, sticky="ew")
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.pack(side="left")
        ttk.Label(brand, text="◈", style="Title.TLabel", foreground=COLORS["accent2"], font=("Segoe UI", 27, "bold")).pack(side="left", padx=(0, 7))
        ttk.Label(brand, text="PRIME", style="Title.TLabel").pack(side="left")
        ttk.Label(brand, text="AI", style="Title.TLabel", foreground=COLORS["accent2"]).pack(side="left")
        ttk.Label(brand, text="TRADER", style="Title.TLabel").pack(side="left")
        self.health_labels = {}
        for name in ("ÁUDIO", "DATABASE", "NEWS", "IA", "WEBSOCKET", "FOREX", "BINANCE"):
            label = ttk.Label(header, text=f"{name} ●", style="Status.TLabel", foreground=COLORS["muted"], font=("Segoe UI", 9))
            label.pack(side="right", padx=8)
            self.health_labels[name] = label

    def _build_left(self, parent) -> None:
        outer = tk.Frame(parent, bg=COLORS["panel"], width=286, highlightbackground=COLORS["border"], highlightthickness=1)
        outer.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        outer.grid_propagate(False)
        canvas = tk.Canvas(outer, bg=COLORS["panel"], highlightthickness=0, width=269, bd=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        panel = ttk.Frame(canvas, style="Panel.TFrame", padding=(12, 9))
        window_id = canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units")))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))
        self.market_combo = self._combo(panel, "Mercado", self.market_var, [Market.CRYPTO.value, Market.FOREX.value], self._market_changed)
        self.symbol_combo = self._combo(panel, "Ativo", self.symbol_var, CRYPTO_DEFAULTS, self._selection_changed)
        self._combo(panel, "Gráfico", self.timeframe_var, TIMEFRAMES, self._selection_changed)
        self._combo(panel, "Expiração", self.horizon_var, ["1", "2", "3", "5", "10", "15", "30", "60", "240"], self._save_form)
        self._combo(panel, "Sensibilidade", self.sensitivity_var, ["CONSERVADOR", "EQUILIBRADO", "RÁPIDO"], self._save_form)
        self._combo(panel, "Modo", self.mode_var, ["CONFIRMAÇÃO", "PRICE ACTION", "QUANTITATIVO"], self._save_form)
        ttk.Button(panel, text="▶   INICIAR ANÁLISE", style="Accent.TButton", command=self.start_analysis).pack(fill="x", pady=(11, 4))
        ttk.Button(panel, text="Ⅱ   PAUSAR", style="Danger.TButton", command=self.pause_analysis).pack(fill="x", pady=3)
        ttk.Button(panel, text="▧   BACKTEST", style="Backtest.TButton", command=self.run_backtest).pack(fill="x", pady=3)
        ttk.Button(panel, text="◈   TREINAR IA", style="Train.TButton", command=self.train_ai).pack(fill="x", pady=3)
        quick = ttk.Frame(panel, style="Panel.TFrame")
        quick.pack(fill="x", pady=(4, 4))
        ttk.Button(quick, text="↻ GRÁFICO", style="Secondary.TButton", command=self.refresh_analysis).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(quick, text="◎ RADAR", style="Secondary.TButton", command=self.run_radar).pack(side="left", fill="x", expand=True, padx=(3, 0))
        self.platform_combo = self._combo(
            panel, "Plataforma (sincronização visual)", self.platform_var,
            ["VEX", "BULLEX"], self._platform_changed,
        )
        initial_platform_button = (
            "◉   CONECTAR VEX INVEST" if self.platform_var.get() == "VEX"
            else "◉   CONECTAR BULLEX"
        )
        self.vex_button = ttk.Button(panel, text=initial_platform_button, style="Secondary.TButton", command=self.connect_vex)
        self.vex_button.pack(fill="x", pady=(4, 2))
        ttk.Label(panel, textvariable=self.platform_status_var, style="Muted.TLabel", wraplength=238, justify="left").pack(anchor="w", pady=(0, 4))
        self._advanced_button = ttk.Button(panel, text="AJUSTES AVANÇADOS  ▾", style="Tool.TButton", command=self._toggle_advanced)
        self._advanced_button.pack(fill="x", pady=(4, 4))
        self.advanced_panel = ttk.Frame(panel, style="Panel.TFrame")
        self.payout_combo = self._combo(self.advanced_panel, "Pagamento da plataforma (%)", self.payout_var, ["70", "74", "75", "78", "80", "82", "85", "90", "95"], self._save_form)
        self._combo(self.advanced_panel, "Valor da entrada (R$)", self.stake_var, ["10.00", "20.00", "50.00", "80.00", "100.00"], self._save_form)
        self._combo(self.advanced_panel, "Janela de risco antes de evento", self.impact_block_var, ["5", "10", "15"], self._save_form)
        ttk.Button(self.advanced_panel, text="↻  CARREGAR ATIVOS DISPONÍVEIS", style="Secondary.TButton", command=self.refresh_symbols).pack(fill="x", pady=(3, 6))
        ttk.Checkbutton(self.advanced_panel, text="Bloquear automaticamente por notícia/evento", variable=self.strict_risk_blocks_var, command=self._save_form).pack(anchor="w", pady=(2, 4))
        ttk.Label(self.advanced_panel, textvariable=self.profile_hint_var, style="Muted.TLabel", wraplength=238).pack(anchor="w", pady=(2, 7))
        ttk.Separator(panel).pack(fill="x", pady=(6, 8))
        audio_heading = ttk.Frame(panel, style="Panel.TFrame")
        audio_heading.pack(fill="x")
        ttk.Label(audio_heading, text="Alertas de voz", style="Section.TLabel").pack(side="left")
        ttk.Checkbutton(audio_heading, text="●", variable=self.audio_var, command=self._save_form).pack(side="right")
        ttk.Label(panel, text="◉  Português Brasil", style="Panel.TLabel", foreground=COLORS["green"], font=("Segoe UI", 10)).pack(anchor="w", pady=(7, 6))
        ttk.Checkbutton(panel, text="Pré-sinal", variable=self.pre_voice_var, command=self._save_form).pack(anchor="w")
        ttk.Checkbutton(panel, text="Sinal confirmado", variable=self.confirmed_voice_var, command=self._save_form).pack(anchor="w")
        ttk.Checkbutton(panel, text="Áudio de risco bloqueante", variable=self.alert_voice_var, command=self._save_form).pack(anchor="w")
        ttk.Label(panel, text="Volume da voz", style="Muted.TLabel").pack(anchor="w", pady=(6, 1))
        ttk.Scale(panel, from_=0, to=100, variable=self.audio_volume_var, command=lambda _: self._save_form()).pack(fill="x")
        tools = ttk.Frame(panel, style="Panel.TFrame")
        tools.pack(fill="x", pady=(10, 3))
        ttk.Button(tools, text="APIs", style="Tool.TButton", command=self.open_api_settings).pack(side="left", fill="x", expand=True)
        ttk.Button(tools, text="LOGS", style="Tool.TButton", command=self.open_logs).pack(side="left", fill="x", expand=True)
        ttk.Button(tools, text="RESULTADOS", style="Tool.TButton", command=self.open_performance).pack(side="left", fill="x", expand=True)
        ttk.Button(panel, text="REGISTRAR RESULTADO OBSERVADO", style="Secondary.TButton", command=self.open_manual_result).pack(fill="x", pady=(2, 3))
        ttk.Button(panel, text="MONITOR DE SAÚDE", style="Secondary.TButton", command=self.open_health).pack(fill="x", pady=(2, 3))
        ttk.Button(panel, text="LIMPAR CACHE / MODELOS ANTIGOS", style="Tool.TButton", command=self.clean_cache).pack(fill="x", pady=(2, 0))

    def _toggle_advanced(self) -> None:
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self.advanced_panel.pack(fill="x", after=self._advanced_button, pady=(2, 6))
            self._advanced_button.configure(text="AJUSTES AVANÇADOS  ▴")
        else:
            self.advanced_panel.pack_forget()
            self._advanced_button.configure(text="AJUSTES AVANÇADOS  ▾")

    def _combo(self, parent, label: str, variable, values, callback) -> ttk.Combobox:
        ttk.Label(parent, text=label, style="Field.TLabel").pack(anchor="w", pady=(4, 3))
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", font=("Segoe UI", 10))
        combo.pack(fill="x", pady=(0, 5))
        combo.bind("<<ComboboxSelected>>", lambda _: callback())
        return combo

    def _build_center(self, parent) -> None:
        center = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center.grid_rowconfigure(2, weight=1)
        center.grid_columnconfigure(0, weight=1)
        toolbar = ttk.Frame(center, style="Toolbar.TFrame", padding=(7, 5))
        toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=(4, 0))
        self.timeframe_buttons = {}
        for timeframe in ("1m", "3m", "5m", "15m", "30m", "1h", "4h"):
            button = ttk.Button(toolbar, text=timeframe, style="Timeframe.TButton", width=3,
                                command=lambda value=timeframe: self._set_timeframe(value))
            button.pack(side="left", padx=(0, 1))
            self.timeframe_buttons[timeframe] = button
        self._refresh_timeframe_buttons()
        ttk.Button(toolbar, text="IND", style="Tool.TButton", width=4, command=self._toggle_indicators).pack(side="right", padx=1)
        for text, name in (("S/R", "sr"), ("FIB", "fibonacci"), ("EMA", "ema"), ("BB", "bollinger"), ("TOPOS", "swings"), ("TEND", "trend"), ("SINAIS", "signals")):
            ttk.Button(toolbar, text=text, style="Tool.TButton", width=4 if len(text) <= 4 else 5,
                       command=lambda n=name: self._toggle_overlay(n)).pack(side="right", padx=1)
        ttk.Button(toolbar, text="FIT", style="Tool.TButton", width=3, command=lambda: self.chart.fit()).pack(side="right", padx=1)
        summary = ttk.Frame(center, style="Panel.TFrame", padding=(12, 5))
        summary.grid(row=1, column=0, sticky="ew")
        ttk.Label(summary, textvariable=self.context_var, style="Section.TLabel", font=("Segoe UI Semibold", 9)).pack(side="left")
        ttk.Label(summary, textvariable=self.ohlc_var, style="Muted.TLabel", font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))
        ttk.Label(summary, textvariable=self.updated_var, style="Muted.TLabel", foreground=COLORS["green"], font=("Segoe UI", 8)).pack(side="right")
        self.chart = CandleChart(center, on_ohlc=self.ohlc_var.set)
        self.chart.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 3))
        self._build_indicator_strip(center)
        self._build_insights(center)

    def _set_timeframe(self, timeframe: str) -> None:
        self.timeframe_var.set(timeframe)
        self._refresh_timeframe_buttons()
        self._selection_changed()

    def _refresh_timeframe_buttons(self) -> None:
        current = self.timeframe_var.get()
        for timeframe, button in self.timeframe_buttons.items():
            button.configure(style="ActiveTimeframe.TButton" if timeframe == current else "Timeframe.TButton")

    def _build_indicator_strip(self, parent) -> None:
        self.indicator_holder = ttk.Frame(parent, style="Panel.TFrame", height=89)
        self.indicator_holder.grid(row=3, column=0, sticky="ew", padx=4, pady=(2, 4))
        self.indicator_holder.grid_propagate(False)
        canvas = tk.Canvas(self.indicator_holder, bg=COLORS["panel"], highlightthickness=0, height=70)
        scrollbar = ttk.Scrollbar(self.indicator_holder, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=scrollbar.set)
        canvas.pack(fill="both", expand=True)
        scrollbar.pack(fill="x")
        inner = ttk.Frame(canvas, style="Panel.TFrame")
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        self.indicator_values = {}
        icons = {"ema": "◈", "rsi": "↗", "macd": "≋", "bb": "≋", "stoch": "∿", "adx": "△", "atr": "↕", "vwap": "≡", "obv": "▥", "cci": "◉", "williams": "%", "fib": "ƒ", "volume": "▥", "price_action": "⌇", "news": "◎"}
        for index, (title, key) in enumerate(INDICATOR_LAYOUT):
            card = ttk.Frame(inner, style="Card.TFrame", padding=(8, 5), width=152, height=63)
            card.grid(row=0, column=index, padx=3, pady=3, sticky="nsew")
            card.grid_propagate(False)
            heading = ttk.Frame(card, style="Card.TFrame")
            heading.pack(fill="x")
            ttk.Label(heading, text=icons.get(key, "◈"), style="Card.TLabel", foreground=COLORS["accent2"], font=("Segoe UI", 12)).pack(side="left")
            ttk.Label(heading, text=title, style="Card.TLabel", font=("Segoe UI Semibold", 8)).pack(side="left", padx=5)
            ttk.Label(heading, text="✓", style="Card.TLabel", foreground=COLORS["green"], font=("Segoe UI Semibold", 9)).pack(side="right")
            value = ttk.Label(card, text="Aguardando análise", style="CardMuted.TLabel", font=("Segoe UI", 8))
            value.pack(anchor="w", pady=(2, 0))
            self.indicator_values[key] = value

    def _build_insights(self, parent) -> None:
        holder = ttk.Frame(parent, style="Panel.TFrame", height=161)
        holder.grid(row=4, column=0, sticky="ew", padx=6, pady=(3, 6))
        holder.grid_propagate(False)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=6)
        holder.grid_columnconfigure(1, weight=4)
        holder.grid_columnconfigure(2, weight=2)

        explanation = ttk.Frame(holder, style="Card.TFrame", padding=(11, 9))
        explanation.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        heading = ttk.Frame(explanation, style="Card.TFrame")
        heading.pack(fill="x")
        ttk.Label(heading, text="◈", style="Card.TLabel", foreground=COLORS["accent2"], font=("Segoe UI", 15)).pack(side="left", padx=(0, 5))
        ttk.Label(heading, text="Explicação da IA", style="InsightTitle.TLabel").pack(side="left")
        ttk.Separator(explanation).pack(fill="x", pady=(5, 7))
        self.ai_explanation_label = ttk.Label(explanation, text="Inicie uma análise para visualizar as confluências, a estratégia e o contexto das notícias.", style="Card.TLabel", wraplength=325, justify="left", font=("Segoe UI", 9))
        self.ai_explanation_label.pack(anchor="w", fill="x")
        explanation.bind("<Configure>", lambda event: self.ai_explanation_label.configure(wraplength=max(120, event.width - 26)))

        recent = ttk.Frame(holder, style="Card.TFrame", padding=(10, 9))
        recent.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
        ttk.Label(recent, text="Últimos sinais", style="InsightTitle.TLabel").pack(anchor="w")
        ttk.Separator(recent).pack(fill="x", pady=(5, 4))
        self.recent_signal_labels = []
        for _ in range(3):
            line = ttk.Frame(recent, style="Card.TFrame")
            line.pack(fill="x", pady=2)
            hour = ttk.Label(line, text="--:--", style="CardMuted.TLabel", font=("Segoe UI", 8))
            asset = ttk.Label(line, text="—", style="Card.TLabel", font=("Segoe UI Semibold", 8))
            direction = ttk.Label(line, text="—", style="Card.TLabel", foreground=COLORS["muted"], font=("Segoe UI Semibold", 10))
            result = ttk.Label(line, text="—", style="Card.TLabel", foreground=COLORS["muted"], font=("Segoe UI Semibold", 9))
            hour.pack(side="left")
            asset.pack(side="left", padx=(8, 0))
            result.pack(side="right")
            direction.pack(side="right", padx=(0, 7))
            self.recent_signal_labels.append((hour, asset, direction, result))

        audio = ttk.Frame(holder, style="Card.TFrame", padding=(7, 6))
        audio.grid(row=0, column=2, sticky="nsew")
        audio.grid_rowconfigure(1, weight=1)
        audio.grid_columnconfigure(1, weight=1)
        self.audio_card = audio
        icon = tk.Canvas(audio, width=42, height=42, bg=COLORS["card"], highlightthickness=0)
        self.audio_icon = icon
        icon.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 5))
        icon.create_oval(3, 3, 39, 39, outline=COLORS["green"], width=2, fill=COLORS["green_dark"])
        icon.create_polygon(10, 17, 16, 17, 24, 11, 24, 31, 16, 25, 10, 25, fill=COLORS["green"])
        icon.create_arc(22, 11, 34, 31, start=290, extent=140, outline=COLORS["green"], style="arc", width=2)
        text_holder = ttk.Frame(audio, style="Card.TFrame")
        text_holder.grid(row=0, column=1, sticky="w")
        self.audio_title_label = ttk.Label(text_holder, text="Alertas de voz ativos", style="Card.TLabel", font=("Segoe UI Semibold", 8))
        self.audio_title_label.pack(anchor="w")
        self.audio_detail_label = ttk.Label(text_holder, text="Aguardando próximo sinal", style="CardMuted.TLabel", wraplength=128, justify="left", font=("Segoe UI", 8))
        self.audio_detail_label.pack(anchor="w")
        self.audio_wave = tk.Canvas(audio, width=118, height=22, bg=COLORS["card"], highlightthickness=0)
        self.audio_wave.grid(row=1, column=1, sticky="ew")
        self.audio_wave.bind("<Configure>", lambda _: self._draw_audio_wave())

    def _draw_audio_wave(self, color: str | None = None) -> None:
        if not hasattr(self, "audio_wave"):
            return
        canvas = self.audio_wave
        canvas.delete("wave")
        width, height = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        for index in range(max(8, min(width // 4, 58))):
            x = 3 + index * 4
            amplitude = 3 + ((index * 11 + index // 3 * 7) % 17)
            canvas.create_line(x, height / 2 - amplitude / 2, x, height / 2 + amplitude / 2,
                               fill=color or COLORS["green"], width=1, tags="wave")

    def _build_right(self, parent) -> None:
        outer = tk.Frame(parent, bg=COLORS["panel"], width=338, highlightbackground=COLORS["border"], highlightthickness=1)
        outer.grid(row=0, column=2, sticky="nse")
        outer.grid_propagate(False)
        canvas = tk.Canvas(outer, bg=COLORS["panel"], highlightthickness=0, width=320, bd=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        panel = ttk.Frame(canvas, style="Panel.TFrame", padding=(11, 11))
        window_id = canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))

        title = ttk.Frame(panel, style="Panel.TFrame")
        title.pack(fill="x", pady=(1, 9))
        ttk.Label(title, text="✦", style="Panel.TLabel", foreground=COLORS["accent2"], font=("Segoe UI", 17)).pack(side="left", padx=(0, 7))
        ttk.Label(title, text="SINAL DA IA", style="Section.TLabel", font=("Segoe UI Semibold", 12)).pack(side="left")
        hero = ttk.Frame(panel, style="Card.TFrame", padding=(11, 10))
        hero.pack(fill="x")
        self.signal_state = ttk.Label(hero, text="SEM SINAL", style="Card.TLabel", foreground=COLORS["muted"], font=("Segoe UI Semibold", 9))
        self.signal_state.pack(anchor="w")
        direction_row = ttk.Frame(hero, style="Card.TFrame")
        direction_row.pack(fill="x", pady=(5, 7))
        self.signal_orb = tk.Canvas(direction_row, width=32, height=32, bg=COLORS["card"], highlightthickness=0)
        self.signal_orb.pack(side="left", padx=(0, 7))
        self.signal_orb.create_oval(3, 3, 29, 29, fill=COLORS["amber"], outline="", tags="orb")
        self.signal_direction = ttk.Label(direction_row, text="AGUARDAR", style="Card.TLabel", foreground=COLORS["amber"], font=("Segoe UI", 23, "bold"))
        self.signal_direction.pack(side="left")
        confidence = ttk.Frame(hero, style="Inset.TFrame", padding=(8, 7))
        confidence.pack(fill="x", pady=(0, 8))
        self.signal_score = ttk.Label(confidence, text="Score combinado: — / 100", style="Inset.TLabel", font=("Segoe UI Semibold", 10), wraplength=264)
        self.signal_score.pack(anchor="w")
        self.score_bar = ttk.Progressbar(confidence, style="Score.Horizontal.TProgressbar", maximum=100, variable=self.score_var)
        self.score_bar.pack(fill="x", pady=(7, 1))
        self.probability_high_label = ttk.Label(hero, text="Cenário dominante: —", style="CardMuted.TLabel")
        self.probability_high_label.pack(anchor="w")
        self.probability_low_label = ttk.Label(hero, text="Probabilidade baixa: —", style="CardMuted.TLabel")
        self.probability_low_label.pack(anchor="w")
        self.calibration_label = ttk.Label(hero, text="Confiança calibrada: histórico insuficiente", style="CardMuted.TLabel", wraplength=250)
        self.calibration_label.pack(anchor="w", pady=(2, 0))
        self.validation_label = ttk.Label(hero, text="", style="CardMuted.TLabel", wraplength=250)
        self.validation_label.pack(anchor="w", pady=(3, 0))
        self.setup_label = ttk.Label(hero, text="Estratégia: análise em formação", style="CardMuted.TLabel", wraplength=250)
        self.setup_label.pack(anchor="w", pady=(3, 0))

        details = ttk.Frame(panel, style="Card.TFrame", padding=(11, 8))
        details.pack(fill="x", pady=(9, 0))
        ttk.Label(details, text="OPERAÇÃO", style="CardMuted.TLabel", font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(0, 3))
        self.entry_label = ttk.Label(details, text="Entrada: —", style="Card.TLabel")
        self.entry_label.pack(anchor="w", pady=2)
        self.horizon_label = ttk.Label(details, text="Horizonte: —", style="Card.TLabel")
        self.horizon_label.pack(anchor="w", pady=2)
        self.payout_label = ttk.Label(details, text="Pagamento / equilíbrio: —", style="CardMuted.TLabel", wraplength=250)
        self.payout_label.pack(anchor="w", pady=(4, 1))

        timer = tk.Frame(panel, bg=COLORS["card_alt"], highlightbackground=COLORS["green"], highlightthickness=1)
        timer.pack(fill="x", pady=(10, 8))
        ttk.Label(timer, text="TEMPO RESTANTE", style="InsetMuted.TLabel").pack(pady=(7, 0))
        self.countdown_label = ttk.Label(timer, text="--:--", style="Inset.TLabel", foreground=COLORS["green"], font=("Segoe UI", 30, "bold"))
        self.countdown_label.pack(pady=(0, 5))

        reasons = ttk.Frame(panel, style="Card.TFrame", padding=(10, 8))
        reasons.pack(fill="x", pady=(3, 0))
        ttk.Label(reasons, text="Motivos da análise", style="InsightTitle.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Separator(reasons).pack(fill="x", pady=(0, 5))
        self.confluence_frame = ttk.Frame(reasons, style="Card.TFrame")
        self.confluence_frame.pack(fill="x")
        self.confluence_labels: list[ttk.Label] = []
        self.blocker_label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["red"], wraplength=265)
        self.blocker_label.pack(anchor="w", pady=(10, 0))
        self.warning_label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["amber"], wraplength=265)
        self.warning_label.pack(anchor="w", pady=(6, 0))
        self.waiting_label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["muted"], wraplength=265, justify="left")
        self.waiting_label.pack(anchor="w", pady=(6, 0))
        ttk.Separator(panel).pack(fill="x", pady=(12, 9))
        news_header = ttk.Frame(panel, style="Panel.TFrame")
        news_header.pack(fill="x")
        ttk.Label(news_header, text="NOTÍCIAS AO VIVO", style="Section.TLabel").pack(side="left")
        ttk.Button(news_header, text="↻", style="Tool.TButton", width=3, command=self.refresh_news_panel).pack(side="right")
        self.news_source_label = ttk.Label(panel, text="Aguardando fontes públicas…", style="Muted.TLabel", wraplength=265)
        self.news_source_label.pack(anchor="w", pady=(3, 6))
        self.news_labels: list[ttk.Label] = []
        self._news_items = []
        for index in range(5):
            label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["accent2"], wraplength=265, justify="left", cursor="hand2")
            label.bind("<Button-1>", lambda _, position=index: self._open_news(position))
            self.news_labels.append(label)
        ttk.Separator(panel).pack(fill="x", pady=11)
        warning = ttk.Label(panel, text="Assistente de análise. Não executa ordens e não garante lucro.", style="Muted.TLabel", wraplength=265, justify="left")
        warning.pack(anchor="w")

    def _save_form(self) -> None:
        settings = self.controller.settings
        settings.market = self.market_var.get()
        if settings.market == Market.CRYPTO.value:
            settings.crypto_symbol = self.symbol_var.get()
        else:
            settings.forex_symbol = self.symbol_var.get()
        settings.timeframe = self.timeframe_var.get()
        settings.horizon_minutes = int(self.horizon_var.get())
        settings.payout_percent = int(self.payout_var.get())
        try:
            settings.stake_amount = max(0.01, float(self.stake_var.get().replace(",", ".")))
        except ValueError:
            settings.stake_amount = 80.0
            self.stake_var.set("80.00")
        settings.platform_name = self.platform_var.get()
        settings.sensitivity = self.sensitivity_var.get()
        self.profile_hint_var.set(sensitivity_profile(settings.sensitivity).description)
        settings.mode = self.mode_var.get()
        settings.audio_enabled = self.audio_var.get()
        settings.audio_volume = self.audio_volume_var.get()
        settings.voice_pre_signal = self.pre_voice_var.get()
        settings.voice_confirmed = self.confirmed_voice_var.get()
        settings.voice_alerts = self.alert_voice_var.get()
        settings.high_impact_block_minutes = int(self.impact_block_var.get())
        settings.strict_risk_blocks = self.strict_risk_blocks_var.get()
        self.controller.save_settings()

    def _platform_changed(self) -> None:
        if self._platform_bridge and self._platform_bridge.running:
            self.connect_vex()
        name = self.platform_var.get()
        self.controller.settings.platform_name = name
        self.controller.save_settings()
        button = "◉   CONECTAR VEX INVEST" if name == "VEX" else "◉   CONECTAR BULLEX"
        self.vex_button.configure(text=button)
        suffix = (
            " • exige aceite do alerta CVM"
            if name == "BULLEX" and not self.controller.settings.bullex_sync_authorized else ""
        )
        self.platform_status_var.set(f"{name} não conectada • pagamento manual{suffix}")

    def _market_changed(self) -> None:
        values = CRYPTO_DEFAULTS if self.market_var.get() == Market.CRYPTO.value else FOREX_DEFAULTS
        self.symbol_combo.configure(values=values)
        self.symbol_var.set(values[0])
        self._save_form()
        if self.market_var.get() == Market.FOREX.value and not self.controller.secrets.get("twelve_data_key"):
            self.status_var.set("Forex público sem chave ativo • Twelve Data é opcional")
        if self._analysis_active:
            self._schedule_analysis_restart()

    def _selection_changed(self) -> None:
        if hasattr(self, "timeframe_buttons"):
            self._refresh_timeframe_buttons()
        self._save_form()
        if self._analysis_active:
            self._schedule_analysis_restart()

    def connect_vex(self) -> None:
        platform_name = self.platform_var.get()
        if self._platform_bridge and self._platform_bridge.running:
            self._platform_bridge.stop()
            self._platform_snapshot = None
            self.controller.platform_snapshot = None
            self.controller.settings.platform_sync_enabled = False
            self.controller.save_settings()
            connect_text = "◉   CONECTAR VEX INVEST" if platform_name == "VEX" else "◉   CONECTAR BULLEX"
            self.vex_button.configure(text=connect_text)
            self.platform_status_var.set(f"{platform_name} desconectada • pagamento manual")
            self.status_var.set(f"Sincronização com a {platform_name} desativada")
            return
        if platform_name == "BULLEX" and not self.controller.settings.bullex_sync_authorized:
            accepted = messagebox.askyesno(
                "Alerta regulatório CVM — BullEx",
                "A CVM informou que Digital Smart LLC/BULLEX não possui autorização para "
                "intermediar valores mobiliários ou captar recursos no Brasil.\n\n"
                "Esta conexão é somente leitura visual: não deposita, não acessa senha, "
                "não clica e não executa operações. Deseja habilitá-la conscientemente?",
                parent=self,
            )
            if not accepted:
                self.platform_status_var.set("BULLEX continua desativada • consulte o alerta da CVM")
                webbrowser.open(BULLEX_CVM_ALERT_URL)
                return
            self.controller.settings.bullex_sync_authorized = True
            self.controller.save_settings()
        bridge_type = VexBrowserBridge if platform_name == "VEX" else BullexBrowserBridge
        self._platform_bridge = bridge_type(
            app_data_dir() / f"{platform_name.lower()}-browser",
            lambda snapshot: self._post_ui(self._vex_snapshot_ready, snapshot),
            lambda status: self._post_ui(self._vex_status_ready, status),
        )
        try:
            self._platform_bridge.start()
        except Exception as exc:
            self.platform_status_var.set(f"{platform_name} não conectada")
            messagebox.showerror(f"Conectar {platform_name}", str(exc), parent=self)
            return
        self.controller.settings.platform_sync_enabled = True
        self.controller.save_settings()
        self.vex_button.configure(text=f"◉   DESCONECTAR {platform_name}")
        self.platform_status_var.set(f"Abrindo {platform_name} • entre na sua conta no navegador")
        self.status_var.set(f"Entre na {platform_name} pelo navegador dedicado; o robô não solicita sua senha")

    def _vex_status_ready(self, status: str) -> None:
        self.platform_status_var.set(status)

    def _vex_snapshot_ready(self, snapshot: VexPlatformSnapshot) -> None:
        if not self._platform_bridge or not self._platform_bridge.running:
            return
        self._platform_snapshot = snapshot
        self.controller.platform_snapshot = snapshot
        settings = self.controller.settings
        changed = False
        if settings.platform_auto_payout and snapshot.payout_percent is not None:
            payout = str(snapshot.payout_percent)
            if self.payout_var.get() != payout:
                choices = list(self.payout_combo.cget("values"))
                if payout not in choices:
                    choices.append(payout)
                    self.payout_combo.configure(values=sorted(choices, key=int))
                self.payout_var.set(payout)
                settings.payout_percent = snapshot.payout_percent
                changed = True
        if settings.platform_auto_asset and snapshot.asset and snapshot.market:
            if self.market_var.get() != snapshot.market:
                self.market_var.set(snapshot.market)
                defaults = CRYPTO_DEFAULTS if snapshot.market == Market.CRYPTO.value else FOREX_DEFAULTS
                self.symbol_combo.configure(values=defaults)
                changed = True
            if self.symbol_var.get() != snapshot.asset:
                choices = list(self.symbol_combo.cget("values"))
                if snapshot.asset not in choices:
                    self.symbol_combo.configure(values=[snapshot.asset, *choices])
                self.symbol_var.set(snapshot.asset)
                changed = True
        if settings.platform_auto_horizon and snapshot.horizon_minutes is not None:
            horizon = str(snapshot.horizon_minutes)
            if self.horizon_var.get() != horizon:
                self.horizon_var.set(horizon)
                changed = True
        details = [snapshot.asset or "identificando ativo"]
        if snapshot.payout_percent is not None:
            details.append(f"payout {snapshot.payout_percent}%")
        if snapshot.remaining_seconds is not None:
            seconds = snapshot.remaining_seconds
            details.append(f"{seconds // 60:02d}:{seconds % 60:02d}")
        if snapshot.otc:
            details.append("OTC não compatível")
        platform_name = snapshot.platform_name
        self.platform_status_var.set(f"{platform_name} ● " + " • ".join(details))
        if changed:
            self._save_form()
            if self._analysis_active:
                if self._platform_change_job is not None:
                    self.after_cancel(self._platform_change_job)
                self._platform_change_job = self.after(300, self._restart_for_vex_change)
        current = self.controller.snapshot
        if current and current.market == self.market_var.get() and current.symbol == self.symbol_var.get():
            reasons = compare_platform_market(snapshot, current.market, current.symbol,
                                              float(current.indicators["close"].iloc[-1]))
            if reasons and settings.platform_block_mismatch:
                self.controller._apply_platform_alignment(current.signal, current.market, current.symbol,
                                                          float(current.indicators["close"].iloc[-1]))
                self._render_signal(current)
            else:
                self._start_countdown(current)
                if self._analysis_active and snapshot.price is not None and self.chart.candles:
                    candle = merge_vex_quote(self.chart.candles[-1], snapshot, current.timeframe)
                    if candle is not None:
                        self._queue_live_chart(candle, self._analysis_token)
                        self.updated_var.set(
                            f"{platform_name} • PREÇO VISÍVEL AO VIVO {snapshot.observed_at.astimezone().strftime('%H:%M:%S')}"
                        )
                        now = time.monotonic()
                        interval = live_refresh_interval(current.timeframe, settings.sensitivity)
                        if now - self._last_live_analysis >= interval and not self._task_running:
                            self._last_live_analysis = now
                            context = (current.market, current.symbol, current.timeframe)
                            self._process_live(candle, self._analysis_token, context)

    def _restart_for_vex_change(self) -> None:
        self._platform_change_job = None
        if self._analysis_active:
            self._schedule_analysis_restart()

    def _schedule_analysis_restart(self) -> None:
        self._stop_feeds()
        self._analysis_token += 1
        if self._selection_job is not None:
            self.after_cancel(self._selection_job)
        self.status_var.set("Trocando ativo e atualizando gráfico…")
        self._selection_job = self.after(250, self._restart_when_idle)

    def _restart_when_idle(self) -> None:
        self._selection_job = None
        if self._task_running:
            self._selection_job = self.after(150, self._restart_when_idle)
            return
        self.start_analysis()

    def open_api_settings(self) -> None:
        ApiSettingsDialog(self, self.controller.secrets, self._save_api_keys)

    def _save_api_keys(self, values: dict[str, str]) -> None:
        self.controller.save_secrets(values)
        self.status_var.set("Chaves protegidas e provedores atualizados")
        self._load_health()
        if self.market_var.get() == Market.FOREX.value and self._analysis_active:
            self._schedule_analysis_restart()

    def refresh_symbols(self) -> None:
        self._save_form()
        def ready(symbols) -> None:
            self.symbol_combo.configure(values=symbols)
            self.status_var.set(f"{len(symbols)} ativos líquidos disponíveis")
        self._run_task("Atualizando lista de ativos…", self.controller.refresh_symbols, ready)

    def _toggle_overlay(self, name: str) -> None:
        value = not self.controller.settings.overlays.get(name, True)
        self.controller.settings.overlays[name] = value
        self.controller.save_settings()
        self.chart.set_overlay(name, value)
        self.status_var.set(f"{name.upper()}: {'ligado' if value else 'desligado'}")

    def _toggle_indicators(self) -> None:
        if self.indicator_holder.winfo_ismapped():
            self.indicator_holder.grid_remove()
            self.status_var.set("Cards de indicadores ocultos")
        else:
            self.indicator_holder.grid()
            self.status_var.set("Cards de indicadores visíveis")

    def _post_ui(self, callback, *args) -> None:
        self._ui_events.put((callback, args))

    def _drain_ui_events(self) -> None:
        self._ui_events_job = None
        try:
            while True:
                callback, args = self._ui_events.get_nowait()
                try:
                    callback(*args)
                except Exception as exc:
                    self.controller.logger.exception("Falha ao atualizar a interface: %s", exc)
                    if self.winfo_exists():
                        self.status_var.set("Falha ao atualizar a tela — consulte os logs")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._ui_events_job = self.after(25, self._drain_ui_events)

    def _run_task(self, label: str, function, on_success, quiet: bool = False) -> None:
        if self._task_running:
            if not quiet:
                messagebox.showinfo("PRIME AI TRADER", "Aguarde a tarefa atual terminar.", parent=self)
            return
        self._task_running = True
        if not quiet:
            self.status_var.set(label)
            self.task_progress.start(12)
        def worker() -> None:
            try:
                result = function()
                self._post_ui(self._task_success, result, on_success, quiet)
            except Exception as exc:
                self.controller.logger.exception("Falha na tarefa: %s", label)
                self._post_ui(self._task_error, str(exc), quiet)
        threading.Thread(target=worker, daemon=True).start()

    def _task_success(self, result, callback, quiet: bool = False) -> None:
        self._task_running = False
        if not quiet:
            self.task_progress.stop()
        callback(result)

    def _task_error(self, error: str, quiet: bool = False) -> None:
        self._task_running = False
        if quiet:
            self.status_var.set(f"Atualização temporariamente indisponível • {error[:80]}")
            if self._analysis_active and self.market_var.get() == Market.FOREX.value:
                lowered = error.lower()
                delay = 300_000 if "crédito" in lowered or "limite" in lowered or "429" in lowered else FOREX_POLL_INTERVAL_MS
                self._schedule_forex_poll(self._analysis_token, delay_ms=delay)
            return
        self.task_progress.stop()
        self.status_var.set("Falha — consulte os logs")
        messagebox.showerror(
            "Não foi possível concluir",
            f"{error}\n\nOs detalhes foram registrados nos logs. Atualize a análise e tente novamente. "
            "Se a mensagem citar uma API, verifique a conexão e a respectiva chave.",
            parent=self,
        )

    def start_analysis(self) -> None:
        self._save_form()
        if self._task_running:
            self.status_var.set("Aguardando a tarefa atual para atualizar o gráfico…")
            if self._selection_job is None:
                self._selection_job = self.after(200, self._restart_when_idle)
            return
        self._stop_feeds()
        self._analysis_active = True
        self._analysis_token += 1
        token = self._analysis_token
        context = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        self._stop_event = threading.Event()
        self._last_live_analysis = 0.0
        cached = self.controller.cached_snapshot()
        if cached is not None:
            self.render_snapshot(cached)
            self.status_var.set("Exibindo dados recentes enquanto atualiza…")
        self._run_task(
            "Carregando mercado e calculando indicadores…",
            self.controller.analyze,
            lambda snapshot: self._analysis_ready(snapshot, token, context),
        )

    def refresh_analysis(self) -> None:
        self.status_var.set("Atualização manual solicitada…")
        self.start_analysis()

    def _analysis_ready(self, snapshot: AnalysisSnapshot, token: int, context: tuple[str, str, str]) -> None:
        current = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        if token != self._analysis_token or context != current or not self._analysis_active:
            return
        self.render_snapshot(snapshot)
        if snapshot.market == Market.FOREX.value:
            source = snapshot.data_source or "fonte pública"
            self.status_var.set(f"Forex ativo • {source} • cotação pública a cada 10 segundos")
        else:
            self.status_var.set(f"Análise ativa • {snapshot.symbol} • {snapshot.timeframe} • {snapshot.generated_at.astimezone().strftime('%H:%M:%S')}")
        if snapshot.market == Market.CRYPTO.value:
            self._start_crypto_stream(token, context)
        else:
            self._schedule_forex_poll(token)
            self._schedule_forex_quote(token, delay_ms=750)
        self._schedule_news_refresh(token)

    def _start_crypto_stream(self, token: int, context: tuple[str, str, str]) -> None:
        symbol, timeframe = self.controller.symbol(), self.controller.settings.timeframe
        stop_event = self._stop_event
        def on_candle(candle) -> None:
            if stop_event.is_set() or token != self._analysis_token:
                return
            self.controller.websocket_online = True
            now = time.monotonic()
            platform = self._platform_snapshot
            if (not candle.closed and platform and platform.price is not None and platform.fresh()
                    and not compare_platform_market(platform, Market.CRYPTO.value, symbol, candle.close)):
                candle = merge_vex_quote(candle, platform, timeframe) or candle
            self._post_ui(self._queue_live_chart, candle, token)
            interval = live_refresh_interval(timeframe, self.controller.settings.sensitivity)
            if candle.closed or now - self._last_live_analysis >= interval:
                self._last_live_analysis = now
                self._post_ui(self._process_live, candle, token, context)
        async def run() -> None:
            await self.controller.binance.stream_candles(symbol, timeframe, on_candle, stop_event)
        self._stream_thread = threading.Thread(target=lambda: asyncio.run(run()), daemon=True)
        self._stream_thread.start()

    def _queue_live_chart(self, candle, token: int) -> None:
        if token != self._analysis_token or not self._analysis_active:
            return
        self._pending_live_candle = candle
        if self._live_ui_job is None:
            self._live_ui_job = self.after(100, lambda: self._flush_live_chart(token))

    def _flush_live_chart(self, token: int) -> None:
        self._live_ui_job = None
        if token != self._analysis_token or self._pending_live_candle is None:
            return
        candle = self._pending_live_candle
        self._pending_live_candle = None
        self.chart.update_last_candle(candle)
        platform = self._platform_snapshot
        if platform and platform.fresh() and platform.price is not None and platform.asset == self.symbol_var.get():
            self.updated_var.set(f"{platform.platform_name} • PREÇO VISÍVEL AO VIVO {datetime.now().strftime('%H:%M:%S')}")
        elif self.market_var.get() == Market.FOREX.value:
            if "FONTE COM ATRASO" not in self.updated_var.get():
                self.updated_var.set(f"FOREX • COTAÇÃO PÚBLICA {datetime.now().strftime('%H:%M:%S')}")
        else:
            self.updated_var.set(f"PREÇO AO VIVO • {datetime.now().strftime('%H:%M:%S')}")

    def _process_live(self, candle, token: int, context: tuple[str, str, str]) -> None:
        if self._stop_event.is_set() or self._task_running or token != self._analysis_token:
            return
        current_snapshot = self.controller.snapshot
        if current_snapshot and preserve_recent_confirmed_signal(
            current_snapshot.signal,
            candle_closed=candle.closed,
            timeframe=current_snapshot.timeframe,
            horizon_minutes=self.controller.settings.horizon_minutes,
            sensitivity=self.controller.settings.sensitivity,
            mode=self.controller.settings.mode,
        ):
            return
        def ready(snapshot) -> None:
            current = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
            if snapshot and token == self._analysis_token and context == current:
                self.render_snapshot(snapshot)
        self._run_task("Atualizando análise em tempo real…", lambda: self.controller.merge_live_candle(candle), ready, quiet=True)

    def _schedule_forex_poll(self, token: int, delay_ms: int = FOREX_POLL_INTERVAL_MS) -> None:
        if delay_ms == FOREX_POLL_INTERVAL_MS:
            delay_ms = self.controller.forex.recommended_poll_ms
        if self._forex_poll_job is not None:
            self.after_cancel(self._forex_poll_job)
        self._forex_poll_job = self.after(delay_ms, lambda: self._forex_poll(token))

    def _forex_poll(self, token: int) -> None:
        self._forex_poll_job = None
        if self._stop_event.is_set() or self.controller.settings.market != Market.FOREX.value or token != self._analysis_token:
            return
        context = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        self._run_task("Atualizando Forex…", self.controller.analyze,
                       lambda snapshot: self._analysis_ready(snapshot, token, context), quiet=True)

    def _schedule_forex_quote(self, token: int, delay_ms: int | None = None) -> None:
        if self._forex_quote_job is not None:
            self.after_cancel(self._forex_quote_job)
        interval = self.controller.forex.recommended_quote_ms if delay_ms is None else delay_ms
        self._forex_quote_job = self.after(interval, lambda: self._forex_quote(token))

    def _forex_quote(self, token: int) -> None:
        self._forex_quote_job = None
        if self._stop_event.is_set() or token != self._analysis_token or not self._analysis_active:
            return
        if self.controller.settings.market != Market.FOREX.value:
            return
        if self._forex_quote_running:
            self._schedule_forex_quote(token)
            return
        symbol = self.controller.symbol()
        context = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        self._forex_quote_running = True

        def worker() -> None:
            try:
                quote = self.controller.forex.fetch_live_quote(symbol)
                self._post_ui(self._forex_quote_ready, quote, token, context)
            except Exception as exc:
                self.controller.logger.debug("Cotação rápida Forex indisponível: %s", exc)
                self._post_ui(self._forex_quote_failed, token)

        threading.Thread(target=worker, daemon=True).start()

    def _forex_quote_ready(self, quote, token: int, context: tuple[str, str, str]) -> None:
        if token != self._analysis_token:
            return
        self._forex_quote_running = False
        current = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        if not self._analysis_active or context != current:
            return
        snapshot = self.controller.snapshot
        if snapshot is None or not self.chart.candles:
            self._schedule_forex_quote(token)
            return
        age_seconds = max(0, (datetime.now(timezone.utc) - quote.observed_at).total_seconds())
        candle = merge_forex_quote(self.chart.candles[-1], quote, snapshot.timeframe) if age_seconds <= 180 else None
        if candle is not None:
            self._queue_live_chart(candle, token)
            now = time.monotonic()
            interval = live_refresh_interval(snapshot.timeframe, self.controller.settings.sensitivity)
            if now - self._last_live_analysis >= interval:
                self._last_live_analysis = now
                self._process_live(candle, token, context)
        observed = quote.observed_at.astimezone().strftime("%H:%M:%S")
        spread_text = f" • spread {quote.spread:g}" if quote.spread is not None else ""
        if age_seconds > 180:
            self.updated_var.set(f"FOREX • ÚLTIMA COTAÇÃO {observed} • FONTE COM ATRASO")
            self._schedule_forex_quote(token, delay_ms=FOREX_QUOTE_RETRY_MS)
        else:
            self.updated_var.set(f"FOREX • COTAÇÃO PÚBLICA {observed}{spread_text}")
            self._schedule_forex_quote(token)

    def _forex_quote_failed(self, token: int) -> None:
        if token != self._analysis_token:
            return
        self._forex_quote_running = False
        if self._analysis_active:
            self._schedule_forex_quote(token, delay_ms=FOREX_QUOTE_RETRY_MS)

    def _stop_feeds(self) -> None:
        self._stop_event.set()
        self.controller.websocket_online = False
        if self._forex_poll_job is not None:
            self.after_cancel(self._forex_poll_job)
            self._forex_poll_job = None
        if self._forex_quote_job is not None:
            self.after_cancel(self._forex_quote_job)
            self._forex_quote_job = None
        self._forex_quote_running = False
        if self._live_ui_job is not None:
            self.after_cancel(self._live_ui_job)
            self._live_ui_job = None
        self._pending_live_candle = None
        if self._news_refresh_job is not None:
            self.after_cancel(self._news_refresh_job)
            self._news_refresh_job = None

    def pause_analysis(self, silent: bool = False) -> None:
        self._stop_feeds()
        self._analysis_active = False
        self._analysis_token += 1
        if self._selection_job is not None:
            self.after_cancel(self._selection_job)
            self._selection_job = None
        if not silent:
            self.status_var.set("Análise pausada")

    def train_ai(self) -> None:
        self._save_form()
        self._run_task("Treinando e validando modelos no tempo…", self.controller.train, self._training_ready)

    def _training_ready(self, report) -> None:
        selected = next(metric for metric in report.metrics if metric.model == report.selected_model)
        self.status_var.set(f"IA treinada • {report.selected_model} • versão {report.version}")
        messagebox.showinfo(
            "Treinamento concluído",
            f"Modelo selecionado: {report.selected_model}\nAmostras: {report.samples}\n"
            f"Acerto direcional seletivo: {selected.directional_accuracy * 100:.2f}% "
            f"em {selected.directional_operations} operações\nCobertura seletiva: {selected.coverage * 100:.2f}%\n"
            f"Macro F1 fora da amostra: {selected.macro_f1 * 100:.2f}%\n"
            f"Balanced accuracy: {selected.balanced_accuracy * 100:.2f}%",
            parent=self,
        )
        self._load_health()
        if self._analysis_active:
            self._schedule_analysis_restart()

    def run_backtest(self) -> None:
        self._save_form()
        self._run_task("Executando backtest walk-forward…", self.controller.backtest, lambda result: (self.status_var.set("Backtest concluído"), BacktestDialog(self, result)))

    def run_radar(self) -> None:
        self._save_form()
        self._run_task(
            "Analisando ativos do radar…", self.controller.radar,
            lambda items: (
                self.status_var.set(self.controller.last_radar_note or f"Radar: {len(items)} ativos analisados"),
                RadarDialog(self, items, self._radar_analyze),
            ),
        )

    def refresh_news_panel(self) -> None:
        if not self.controller.snapshot:
            self.status_var.set("Inicie uma análise para carregar as notícias do ativo")
            return
        self._run_task(
            "Atualizando notícias públicas…",
            lambda: self.controller.refresh_news(force=True),
            self._news_ready,
        )

    def _news_ready(self, snapshot) -> None:
        if snapshot:
            self._render_news(snapshot)
            self._render_indicators(snapshot)
            self.status_var.set(f"Notícias atualizadas • {len(snapshot.news)} manchetes")

    def _schedule_news_refresh(self, token: int, delay_ms: int = 90_000) -> None:
        if self._news_refresh_job is not None:
            self.after_cancel(self._news_refresh_job)
        self._news_refresh_job = self.after(delay_ms, lambda: self._auto_refresh_news(token))

    def _auto_refresh_news(self, token: int) -> None:
        self._news_refresh_job = None
        if token != self._analysis_token or not self._analysis_active:
            return
        if self._news_refresh_running or self._task_running:
            self._schedule_news_refresh(token, 15_000)
            return
        self._news_refresh_running = True

        def done(snapshot, error: str = "") -> None:
            self._news_refresh_running = False
            if token != self._analysis_token or not self._analysis_active:
                return
            if snapshot:
                self._render_news(snapshot)
                self._render_indicators(snapshot)
            elif error:
                self.controller.logger.warning("Atualização automática das notícias: %s", error)
            self._schedule_news_refresh(token)

        def worker() -> None:
            try:
                self._post_ui(done, self.controller.refresh_news())
            except Exception as exc:
                self._post_ui(done, None, str(exc))

        threading.Thread(target=worker, daemon=True, name="prime-news-ui").start()

    def _open_news(self, index: int) -> None:
        if 0 <= index < len(self._news_items) and self._news_items[index].url:
            webbrowser.open(self._news_items[index].url)

    def open_health(self) -> None:
        self._run_task("Executando diagnóstico dos serviços…", self.controller.health,
                       lambda statuses: (self.status_var.set("Diagnóstico concluído"), HealthDialog(self, statuses)))

    def open_performance(self) -> None:
        self._run_task(
            "Calculando desempenho real…", self.controller.repository.statistics,
            lambda stats: (self.status_var.set("Desempenho atualizado"), PerformanceDialog(self, stats)),
        )

    def open_manual_result(self) -> None:
        rows = self.controller.repository.recent(30)
        if not rows:
            messagebox.showinfo(
                "Resultado observado", "Ainda não há sinais salvos para registrar.", parent=self,
            )
            return

        def save(signal_id: int, result: str, payout: int, stake: float) -> None:
            self.controller.repository.record_manual_result(
                signal_id, result, payout_percent=payout, stake_amount=stake,
            )
            self.status_var.set(f"Resultado {result} registrado como observado na plataforma")
            self._refresh_recent_signals()

        ManualResultDialog(
            self, rows, save, int(self.payout_var.get()),
            float(self.stake_var.get().replace(",", ".")),
        )

    def clean_cache(self) -> None:
        confirmed = messagebox.askyesno(
            "Limpeza segura",
            "Esta limpeza remove cache e modelos de versões antigas.\n\n"
            "Suas chaves de API, configurações e histórico de sinais serão preservados. "
            "A IA precisará ser treinada novamente para cada ativo.\n\nContinuar?",
            parent=self,
        )
        if not confirmed:
            return
        self.pause_analysis(silent=True)
        self._run_task("Limpando cache e modelos antigos…", self.controller.cleanup_cache, self._cache_cleaned)

    def _cache_cleaned(self, result: dict) -> None:
        self.chart.candles = []
        self.chart.indicators = pd.DataFrame()
        self.chart.zones = []
        self.chart.fibonacci = None
        self.chart.structure = None
        self.chart.signal = None
        self.chart.schedule_redraw()
        self.context_var.set("CACHE LIMPO • INICIE UMA NOVA ANÁLISE")
        self.updated_var.set("Modelos antigos removidos")
        removed = ", ".join(result.get("removed", [])) or "nenhum arquivo antigo encontrado"
        failures = result.get("failures", [])
        self.status_var.set("Limpeza concluída com segurança")
        detail = f"Removido: {removed}.\n\nChaves, configurações e histórico foram preservados."
        if failures:
            detail += "\n\nAlguns itens em uso não puderam ser removidos; reinicie o Windows e use o limpador do menu Iniciar."
        messagebox.showinfo("Limpeza concluída", detail, parent=self)
        self._load_health()

    def _radar_analyze(self, symbol: str) -> None:
        self.symbol_var.set(symbol)
        self._save_form()
        self.start_analysis()

    def render_snapshot(self, snapshot: AnalysisSnapshot) -> None:
        zones = snapshot.structure.support_zones + snapshot.structure.resistance_zones
        for name, value in self.controller.settings.overlays.items():
            self.chart.overlays[name] = value
        context_key = f"{snapshot.market}|{snapshot.symbol}|{snapshot.timeframe}"
        self.chart.set_data(snapshot.candles, snapshot.indicators, zones, snapshot.fibonacci,
                            snapshot.structure, snapshot.signal, context_key=context_key)
        self.context_var.set(f"{snapshot.symbol}   •   {snapshot.market.upper()}   •   {snapshot.timeframe}")
        self.updated_var.set(f"ATUALIZADO {snapshot.generated_at.astimezone().strftime('%H:%M:%S')}")
        self._render_indicators(snapshot)
        self._render_signal(snapshot)
        self._render_news(snapshot)
        self._render_insights(snapshot)
        self._refresh_recent_signals()

    def _render_insights(self, snapshot: AnalysisSnapshot) -> None:
        signal = snapshot.signal
        reasons = [reason.rstrip(".") for reason in signal.confluences[:3] if reason]
        if signal.direction == Direction.WAIT and signal.waiting_reasons:
            reasons.insert(0, signal.waiting_reasons[0].rstrip("."))
        if not reasons:
            reasons = [signal.setup_name or "Mercado em análise"]
        risk_count = sum(item.high_risk for item in snapshot.news)
        news_note = f"{risk_count} notícia(s) de risco em acompanhamento" if risk_count else "Nenhuma notícia crítica no momento"
        self.ai_explanation_label.configure(text=". ".join(reasons[:3]) + f". {news_note}.")
        if not self.audio_var.get():
            title, detail, wave_color = "Alertas de voz desativados", "Ative a voz no painel lateral", COLORS["muted"]
        elif signal.direction == Direction.WAIT:
            title, detail, wave_color = "Alertas de voz ativos", "Aguardando próximo sinal confirmado", COLORS["accent2"]
        else:
            action = signal.direction.value.lower()
            title, detail = f"Sinal de {action}", f"{snapshot.symbol} • {signal.state.value.lower()}"
            wave_color = COLORS["green"] if signal.direction == Direction.BUY else COLORS["red"]
        self.audio_title_label.configure(text=title, foreground=wave_color)
        self.audio_detail_label.configure(text=detail)
        self._draw_audio_wave(wave_color)

    def _refresh_recent_signals(self) -> None:
        if self._history_refresh_running:
            return
        self._history_refresh_running = True

        def worker() -> None:
            try:
                self._post_ui(self._recent_signals_ready, self.controller.repository.recent(3))
            except Exception as exc:
                self.controller.logger.debug("Histórico visual de sinais indisponível: %s", exc)
                self._post_ui(self._recent_signals_ready, [])

        threading.Thread(target=worker, daemon=True, name="prime-signal-history-ui").start()

    def _recent_signals_ready(self, rows: list[dict]) -> None:
        self._history_refresh_running = False
        for index, widgets in enumerate(self.recent_signal_labels):
            hour, symbol, direction, result = recent_signal_display(rows[index]) if index < len(rows) else ("--:--", "—", "—", "—")
            hour_label, symbol_label, direction_label, result_label = widgets
            hour_label.configure(text=hour)
            symbol_label.configure(text=symbol)
            direction_color = COLORS["green"] if direction == "▲" else COLORS["red"] if direction == "▼" else COLORS["muted"]
            result_color = COLORS["green"] if result == "✓" else COLORS["red"] if result == "✕" else COLORS["muted"]
            direction_label.configure(text=direction, foreground=direction_color)
            result_label.configure(text=result, foreground=result_color)

    def _render_news(self, snapshot: AnalysisSnapshot) -> None:
        self._news_items = snapshot.news[: len(self.news_labels)]
        sources = getattr(self.controller.news_provider, "last_sources", [])
        summary = ", ".join(sources[:3]) if sources else snapshot.data_source or "Fontes públicas"
        self.news_source_label.configure(text=f"{len(snapshot.news)} manchetes • {summary}")
        for index, label in enumerate(self.news_labels):
            if index >= len(self._news_items):
                label.pack_forget()
                continue
            item = self._news_items[index]
            hour = item.published_at.astimezone().strftime("%H:%M")
            marker = "▲" if item.sentiment == "POSITIVA" else "▼" if item.sentiment == "NEGATIVA" else "●"
            label.configure(text=f"{marker} {hour} • {item.title[:105]}")
            label.pack(anchor="w", fill="x", pady=(3, 5))

    def _render_indicators(self, snapshot: AnalysisSnapshot) -> None:
        last = snapshot.indicators.iloc[-1]
        forex = snapshot.market == Market.FOREX.value
        price_digits = market_price_decimals(f"{snapshot.market}|{snapshot.symbol}") if forex else 2
        real_volume = not forex or any(candle.volume > 0 for candle in snapshot.candles[-90:])
        def f(key, digits=2):
            value = last.get(key)
            return "—" if pd.isna(value) else f"{float(value):,.{digits}f}"
        ema_trend = "ALTA" if last["ema_9"] > last["ema_21"] > last["ema_50"] else "BAIXA" if last["ema_9"] < last["ema_21"] < last["ema_50"] else "MISTA"
        values = {
            "ema": f"9/21/50  {ema_trend}", "rsi": f"14  {f('rsi_14', 1)}", "macd": f"Hist {f('macd_hist', 4)}",
            "bb": f"{f('bb_lower', price_digits)} – {f('bb_upper', price_digits)}", "stoch": f"K {f('stoch_k', 1)} / D {f('stoch_d', 1)}",
            "adx": f"14  {f('adx_14', 1)}", "atr": f"14  {f('atr_14', 5 if forex else 4)}",
            "vwap": f('vwap', price_digits if forex else 4) if real_volume else "SEM VOLUME REAL",
            "obv": f('obv', 0) if real_volume else "SEM VOLUME REAL", "cci": f"20  {f('cci_20', 1)}", "williams": f('williams_r', 1),
            "fib": f"{snapshot.fibonacci.nearest_ratio * 100:.1f}%  PRÓXIMO" if snapshot.fibonacci else "SEM SWING",
            "volume": f"Rel {f('volume_relative', 2)}x" if real_volume else "SEM VOLUME CENTRALIZADO",
            "price_action": f"{snapshot.structure.trend} {' '.join(snapshot.structure.sequence)}",
            "news": f"{sum(item.high_risk for item in snapshot.news)} alto risco / {len(snapshot.news)}",
        }
        for key, text in values.items():
            self.indicator_values[key].configure(text=text)

    def _render_signal(self, snapshot: AnalysisSnapshot) -> None:
        signal = snapshot.signal
        color = COLORS["green"] if signal.direction == Direction.BUY else COLORS["red"] if signal.direction == Direction.SELL else COLORS["amber"]
        self.signal_state.configure(text=signal.state.value)
        self.signal_direction.configure(text=signal.direction.value, foreground=color)
        self.signal_orb.itemconfigure("orb", fill=color)
        score_detail = f"Score combinado: {signal.score}/100 • técnico {signal.technical_score}"
        if signal.model_score is not None:
            score_detail += f" • IA {signal.model_score}/100"
        self.signal_score.configure(text=score_detail)
        self.score_var.set(signal.score)
        ordered = sorted(signal.probabilities.items(), key=lambda item: item[1], reverse=True)
        if ordered and signal.model_score is not None:
            self.probability_high_label.configure(text=f"Distribuição IA: {ordered[0][0]} {ordered[0][1] * 100:.1f}%")
            self.probability_low_label.configure(text=f"Menor classe IA: {ordered[-1][0]} {ordered[-1][1] * 100:.1f}%")
        elif ordered:
            self.probability_high_label.configure(text=f"Força técnica dominante: {ordered[0][0]} • {signal.technical_score}/100")
            self.probability_low_label.configure(text="IA probabilística: treine para este ativo e horizonte")
        else:
            self.probability_high_label.configure(text="Cenário dominante: —")
            self.probability_low_label.configure(text="Cenário secundário: —")
        if signal.calibrated_rate is not None:
            self.calibration_label.configure(text=f"Confiança calibrada: {signal.calibrated_rate * 100:.1f}% em {signal.calibrated_samples} operações semelhantes")
        else:
            self.calibration_label.configure(text=f"Histórico real em coleta: {signal.calibrated_samples}/30 • não bloqueia")
        self.validation_label.configure(text=signal.validation_note)
        regime = f" • {signal.market_regime}" if signal.market_regime else ""
        self.setup_label.configure(text=f"Estratégia: {signal.setup_name}{regime}")
        digits = market_price_decimals(f"{snapshot.market}|{snapshot.symbol}")
        self.entry_label.configure(text=f"Entrada: {signal.entry:,.{digits}f}" if signal.entry else "Entrada: —")
        self.horizon_label.configure(text=f"Expiração: {signal.horizon_minutes} minuto(s)")
        synced = self._platform_snapshot and self._platform_snapshot.fresh() and self._platform_snapshot.payout_percent == signal.payout_percent
        platform_name = self._platform_snapshot.platform_name if synced else ""
        payout_text = (
            f"{f'Payout {platform_name}' if synced else 'Pagamento'} {signal.payout_percent}% • equilíbrio "
            f"{signal.break_even_rate * 100:.2f}%"
        )
        if signal.expected_value is not None:
            payout_text += f" • expectativa {signal.expected_value * 100:+.1f}%"
        self.payout_label.configure(text=payout_text)
        for index, reason in enumerate(signal.confluences):
            if index >= len(self.confluence_labels):
                label = ttk.Label(self.confluence_frame, style="Card.TLabel", wraplength=265, justify="left", font=("Segoe UI", 9))
                self.confluence_labels.append(label)
            label = self.confluence_labels[index]
            label.configure(text=f"✓  {reason}", foreground=COLORS["text"])
            label.pack(anchor="w", pady=2)
        for label in self.confluence_labels[len(signal.confluences):]:
            label.pack_forget()
        self.blocker_label.configure(text="\n".join(f"⚠ {item}" for item in signal.blockers))
        self.warning_label.configure(text="\n".join(f"AVISO • {item}" for item in signal.warnings))
        waiting = "\n".join(f"• {reason}" for reason in signal.waiting_reasons)
        self.waiting_label.configure(text=f"POR QUE AGUARDAR\n{waiting}" if waiting else "")
        self._start_countdown(snapshot)
        voice_signature = (
            snapshot.symbol,
            snapshot.candles[-1].open_time if snapshot.candles else snapshot.generated_at,
            signal.state.value,
            signal.direction.value,
            tuple(signal.blockers) if self.controller.settings.strict_risk_blocks else (),
        )
        should_speak = voice_signature != self._last_voice_signature
        if self.audio_var.get() and should_speak:
            spoken = voice_message_for_signal(
                signal, snapshot.symbol, self.controller.settings.sensitivity,
                strict_risk_blocks=self.controller.settings.strict_risk_blocks,
                voice_confirmed=self.confirmed_voice_var.get(),
                voice_pre_signal=self.pre_voice_var.get(),
                voice_alerts=self.alert_voice_var.get(),
            )
            if spoken:
                message, interval = spoken
                self.voice.speak(message, self.controller.settings.audio_volume, min_interval=interval)
        self._last_voice_signature = voice_signature

    def _start_countdown(self, snapshot: AnalysisSnapshot) -> None:
        if self._countdown_job:
            self.after_cancel(self._countdown_job)
            self._countdown_job = None
        platform = self._platform_snapshot
        synchronized = bool(
            platform and platform.fresh() and platform.expires_at is not None
            and (not platform.asset or platform.asset == snapshot.symbol)
        )
        if synchronized:
            target = platform.expires_at.timestamp()
            self._countdown_signature = (platform.platform_name.lower(), snapshot.market, snapshot.symbol)
            self._countdown_target = target
        elif snapshot.signal.direction != Direction.WAIT:
            candle_time = snapshot.candles[-1].open_time if snapshot.candles else None
            signature = (snapshot.market, snapshot.symbol, snapshot.timeframe, candle_time,
                         snapshot.signal.direction.value, snapshot.signal.horizon_minutes)
            if signature != self._countdown_signature or self._countdown_target is None:
                created = snapshot.signal.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                self._countdown_target = created.timestamp() + snapshot.signal.horizon_minutes * 60
                self._countdown_signature = signature
            target = self._countdown_target
        else:
            self._countdown_signature = None
            self._countdown_target = None
            self.countdown_label.configure(text="--:--")
            return
        def tick() -> None:
            remaining = max(0, round(target - datetime.now(timezone.utc).timestamp()))
            self.countdown_label.configure(text=f"{remaining // 60:02d}:{remaining % 60:02d}")
            if remaining > 0:
                self._countdown_job = self.after(1000, tick)
        tick()

    def _load_health(self) -> None:
        if self._health_running:
            return
        self._health_running = True
        def update(statuses) -> None:
            self._health_running = False
            for status in statuses:
                label = self.health_labels.get(status.name)
                if label:
                    optional = not status.online and (
                        "CHAVE NÃO CONFIGURADA" in status.detail.upper()
                        or "RETREINAR" in status.detail.upper()
                    )
                    color = COLORS["green"] if status.online else COLORS["amber"] if optional else COLORS["red"]
                    suffix = " • OPCIONAL" if optional and status.name == "FOREX" else ""
                    label.configure(foreground=color, text=f"{status.name}{suffix} ●")
            if self.winfo_exists():
                if self._health_job is not None:
                    self.after_cancel(self._health_job)
                self._health_job = self.after(60_000, self._load_health)
        def failed(error: str) -> None:
            self._health_running = False
            self.controller.logger.warning("Monitor de saúde indisponível: %s", error)
            if self.winfo_exists():
                if self._health_job is not None:
                    self.after_cancel(self._health_job)
                self._health_job = self.after(60_000, self._load_health)
        def worker() -> None:
            try:
                statuses = self.controller.health()
                self._post_ui(update, statuses)
            except Exception as exc:
                self._post_ui(failed, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_window_icon(self) -> None:
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            icon_path = os.path.join(base, "assets", "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

    def open_logs(self) -> None:
        path = self.controller.logs_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            messagebox.showerror("Logs", f"Não foi possível abrir o arquivo.\n{path}\n\n{exc}", parent=self)

    def _close(self) -> None:
        self.pause_analysis(silent=True)
        if self._platform_bridge is not None:
            self._platform_bridge.stop()
        if self._platform_change_job is not None:
            self.after_cancel(self._platform_change_job)
            self._platform_change_job = None
        if self._ui_events_job is not None:
            self.after_cancel(self._ui_events_job)
            self._ui_events_job = None
        self.controller.save_settings()
        self.destroy()
