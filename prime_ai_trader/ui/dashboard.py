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
from ..core.models import CRYPTO_DEFAULTS, FOREX_DEFAULTS, Direction, Market, SignalState, TIMEFRAMES
from .chart import CandleChart
from .dialogs import ApiSettingsDialog, BacktestDialog, HealthDialog, PerformanceDialog, RadarDialog
from .theme import COLORS, configure_style


INDICATOR_LAYOUT = [
    ("EMA", "ema"), ("RSI", "rsi"), ("MACD", "macd"), ("BOLLINGER", "bb"),
    ("STOCH", "stoch"), ("ADX", "adx"), ("ATR", "atr"), ("VWAP", "vwap"),
    ("OBV", "obv"), ("CCI", "cci"), ("WILLIAMS %R", "williams"), ("FIBONACCI", "fib"),
    ("VOLUME", "volume"), ("PRICE ACTION", "price_action"), ("NEWS", "news"),
]

LIVE_ANALYSIS_INTERVAL_SECONDS = 30
FOREX_POLL_INTERVAL_MS = 125_000


class PrimeAITraderApp(tk.Tk):
    def __init__(self, controller: TradingController) -> None:
        super().__init__()
        self.controller = controller
        self.voice = VoiceService()
        self.title("PRIME AI TRADER")
        self.geometry("1500x900")
        self.minsize(1120, 680)
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
        self._live_ui_job = None
        self._pending_live_candle = None
        self._health_job = None
        self._health_running = False
        self._last_live_analysis = 0.0
        self._last_voice_signature = None
        self._forex_prompted = False
        self._countdown_job = None
        self._news_refresh_job = None
        self._news_refresh_running = False
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
        self.sensitivity_var = tk.StringVar(value=settings.sensitivity)
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

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_header()
        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        self._build_left(content)
        self._build_center(content)
        self._build_right(content)
        footer = ttk.Frame(self, style="Panel.TFrame", padding=(14, 6))
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel", font=("Segoe UI", 9)).pack(side="left")
        self.task_progress = ttk.Progressbar(footer, mode="indeterminate", length=140)
        self.task_progress.pack(side="right")

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(16, 12))
        header.grid(row=0, column=0, sticky="ew")
        brand = ttk.Frame(header)
        brand.pack(side="left")
        ttk.Label(brand, text="PRIME", style="Title.TLabel", foreground=COLORS["accent2"]).pack(side="left")
        ttk.Label(brand, text=" AI TRADER", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="v0.5.0  •  MULTIFONTE E PROFISSIONAL", style="Badge.TLabel").pack(side="left", padx=(12, 0))
        ttk.Label(header, text="ANÁLISE QUANTITATIVA • OPERAÇÃO MANUAL", foreground=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left", padx=(12, 0))
        self.health_labels = {}
        for name in ("ÁUDIO", "DATABASE", "NEWS", "IA", "WEBSOCKET", "FOREX", "BINANCE"):
            label = ttk.Label(header, text=f"● {name}", foreground=COLORS["muted"], font=("Segoe UI Semibold", 8))
            label.pack(side="right", padx=7)
            self.health_labels[name] = label

    def _build_left(self, parent) -> None:
        outer = ttk.Frame(parent, style="Panel.TFrame", width=258)
        outer.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        outer.grid_propagate(False)
        canvas = tk.Canvas(outer, bg=COLORS["panel"], highlightthickness=0, width=240)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        panel = ttk.Frame(canvas, style="Panel.TFrame", padding=14)
        window_id = canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units")))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))
        ttk.Label(panel, text="CENTRAL DE ANÁLISE", style="Section.TLabel").pack(anchor="w", pady=(0, 3))
        ttk.Label(panel, text="Mercado, ativo e estratégia", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        self.market_combo = self._combo(panel, "Mercado", self.market_var, [Market.CRYPTO.value, Market.FOREX.value], self._market_changed)
        self.symbol_combo = self._combo(panel, "Ativo", self.symbol_var, CRYPTO_DEFAULTS, self._selection_changed)
        ttk.Button(panel, text="↻  CARREGAR ATIVOS DISPONÍVEIS", style="Secondary.TButton", command=self.refresh_symbols).pack(fill="x", pady=(0, 7))
        self._combo(panel, "Timeframe do gráfico", self.timeframe_var, TIMEFRAMES, self._selection_changed)
        self._combo(panel, "Horizonte / previsão", self.horizon_var, ["1", "2", "3", "5", "10", "15", "30", "60", "240"], self._save_form)
        self._combo(panel, "Pagamento da plataforma (%)", self.payout_var, ["70", "74", "75", "78", "80", "82", "85", "90", "95"], self._save_form)
        self._combo(panel, "Sensibilidade", self.sensitivity_var, ["CONSERVADOR", "EQUILIBRADO", "RÁPIDO"], self._save_form)
        self._combo(panel, "Modo", self.mode_var, ["CONFIRMAÇÃO", "PRICE ACTION", "QUANTITATIVO"], self._save_form)
        ttk.Label(panel, text="RÁPIDO gera mais sinais e pode aumentar falsos positivos.", style="Muted.TLabel", wraplength=205).pack(anchor="w", pady=(2, 10))
        ttk.Button(panel, text="▶  INICIAR ANÁLISE", style="Accent.TButton", command=self.start_analysis).pack(fill="x", pady=(3, 4))
        ttk.Button(panel, text="↻  ATUALIZAR GRÁFICO AGORA", style="Secondary.TButton", command=self.refresh_analysis).pack(fill="x", pady=3)
        ttk.Button(panel, text="Ⅱ  PAUSAR", style="Danger.TButton", command=self.pause_analysis).pack(fill="x", pady=3)
        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(4, 0))
        ttk.Button(actions, text="BACKTEST", style="Secondary.TButton", command=self.run_backtest).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(actions, text="TREINAR ATIVO", style="Secondary.TButton", command=self.train_ai).pack(side="left", fill="x", expand=True, padx=(3, 0))
        ttk.Button(panel, text="RADAR DE MERCADO", style="Secondary.TButton", command=self.run_radar).pack(fill="x", pady=(6, 3))
        sep = ttk.Separator(panel)
        sep.pack(fill="x", pady=11)
        ttk.Label(panel, text="ÁUDIO E ALERTAS", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(panel, text="Voz brasileira", variable=self.audio_var, command=self._save_form).pack(anchor="w")
        ttk.Checkbutton(panel, text="Pré-sinal", variable=self.pre_voice_var, command=self._save_form).pack(anchor="w")
        ttk.Checkbutton(panel, text="Sinal confirmado", variable=self.confirmed_voice_var, command=self._save_form).pack(anchor="w")
        ttk.Checkbutton(panel, text="Alertas de risco", variable=self.alert_voice_var, command=self._save_form).pack(anchor="w")
        ttk.Label(panel, text="Volume da voz", style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Scale(panel, from_=0, to=100, variable=self.audio_volume_var, command=lambda _: self._save_form()).pack(fill="x")
        self._combo(panel, "Janela de risco antes de evento", self.impact_block_var, ["5", "10", "15"], self._save_form)
        ttk.Checkbutton(
            panel, text="Bloquear automaticamente por notícia/evento",
            variable=self.strict_risk_blocks_var, command=self._save_form,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(panel, text="Desligado: mostra aviso, mas não impede o sinal.", style="Muted.TLabel", wraplength=205).pack(anchor="w", pady=(2, 3))
        tools = ttk.Frame(panel, style="Panel.TFrame")
        tools.pack(fill="x", pady=(12, 4))
        ttk.Button(tools, text="APIs", command=self.open_api_settings).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(tools, text="LOGS", command=self.open_logs).pack(side="left", fill="x", expand=True, padx=3)
        ttk.Button(tools, text="DESEMPENHO", command=self.open_performance).pack(side="left", fill="x", expand=True, padx=(3, 0))
        ttk.Button(panel, text="MONITOR DE SAÚDE", command=self.open_health).pack(fill="x", pady=(0, 3))
        ttk.Button(panel, text="LIMPAR CACHE / MODELOS ANTIGOS", command=self.clean_cache).pack(fill="x", pady=(3, 0))

    def _combo(self, parent, label: str, variable, values, callback) -> ttk.Combobox:
        ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", pady=(4, 3))
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.pack(fill="x", pady=(0, 4))
        combo.bind("<<ComboboxSelected>>", lambda _: callback())
        return combo

    def _build_center(self, parent) -> None:
        center = ttk.Frame(parent, style="Panel.TFrame")
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center.grid_rowconfigure(2, weight=1)
        center.grid_columnconfigure(0, weight=1)
        summary = ttk.Frame(center, style="Panel.TFrame", padding=(12, 9))
        summary.grid(row=0, column=0, sticky="ew")
        ttk.Label(summary, textvariable=self.context_var, style="Section.TLabel", font=("Segoe UI Semibold", 12)).pack(side="left")
        ttk.Label(summary, textvariable=self.updated_var, style="Muted.TLabel").pack(side="right")
        toolbar = ttk.Frame(center, style="Toolbar.TFrame", padding=(9, 7))
        toolbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        ttk.Label(toolbar, textvariable=self.ohlc_var, style="Muted.TLabel").pack(side="left")
        ttk.Button(toolbar, text="IND", style="Tool.TButton", width=5, command=self._toggle_indicators).pack(side="right", padx=2)
        for text, name in (("S/R", "sr"), ("FIB", "fibonacci"), ("EMA", "ema"), ("BB", "bollinger"), ("TOPOS", "swings"), ("TEND", "trend"), ("SINAIS", "signals")):
            ttk.Button(toolbar, text=text, style="Tool.TButton", width=5, command=lambda n=name: self._toggle_overlay(n)).pack(side="right", padx=2)
        ttk.Button(toolbar, text="FIT", style="Tool.TButton", width=5, command=lambda: self.chart.fit()).pack(side="right", padx=2)
        self.chart = CandleChart(center, on_ohlc=self.ohlc_var.set)
        self.chart.grid(row=2, column=0, sticky="nsew", padx=8)
        self._build_indicator_strip(center)

    def _build_indicator_strip(self, parent) -> None:
        self.indicator_holder = ttk.Frame(parent, style="Panel.TFrame", height=178)
        self.indicator_holder.grid(row=3, column=0, sticky="ew", pady=(7, 0))
        self.indicator_holder.grid_propagate(False)
        canvas = tk.Canvas(self.indicator_holder, bg=COLORS["panel"], highlightthickness=0, height=150)
        scrollbar = ttk.Scrollbar(self.indicator_holder, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=scrollbar.set)
        canvas.pack(fill="both", expand=True)
        scrollbar.pack(fill="x")
        inner = ttk.Frame(canvas, style="Panel.TFrame")
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        self.indicator_values = {}
        for index, (title, key) in enumerate(INDICATOR_LAYOUT):
            card = ttk.Frame(inner, style="Card.TFrame", padding=10, width=164, height=68)
            card.grid(row=index % 2, column=index // 2, padx=3, pady=3, sticky="nsew")
            card.grid_propagate(False)
            ttk.Label(card, text=title, style="Card.TLabel", foreground=COLORS["muted"], font=("Segoe UI Semibold", 8)).pack(anchor="w")
            value = ttk.Label(card, text="—", style="Card.TLabel", font=("Segoe UI Semibold", 11))
            value.pack(anchor="w", pady=(4, 0))
            self.indicator_values[key] = value

    def _build_right(self, parent) -> None:
        outer = ttk.Frame(parent, style="Panel.TFrame", width=312)
        outer.grid(row=0, column=2, sticky="nse")
        outer.grid_propagate(False)
        canvas = tk.Canvas(outer, bg=COLORS["panel"], highlightthickness=0, width=292)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        panel = ttk.Frame(canvas, style="Panel.TFrame", padding=12)
        window_id = canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))

        ttk.Label(panel, text="SINAL DA IA", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        hero = ttk.Frame(panel, style="Card.TFrame", padding=14)
        hero.pack(fill="x")
        self.signal_state = ttk.Label(hero, text="SEM SINAL", style="Card.TLabel", foreground=COLORS["muted"], font=("Segoe UI Semibold", 9))
        self.signal_state.pack(anchor="w")
        self.signal_direction = ttk.Label(hero, text="AGUARDAR", style="Card.TLabel", foreground=COLORS["amber"], font=("Segoe UI Semibold", 28))
        self.signal_direction.pack(anchor="w", pady=(3, 8))
        self.signal_score = ttk.Label(hero, text="Score combinado: —", style="Card.TLabel", font=("Segoe UI Semibold", 10), wraplength=250)
        self.signal_score.pack(anchor="w")
        self.score_bar = ttk.Progressbar(hero, style="Score.Horizontal.TProgressbar", maximum=100, variable=self.score_var)
        self.score_bar.pack(fill="x", pady=(7, 10))
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

        details = ttk.Frame(panel, style="Card.TFrame", padding=12)
        details.pack(fill="x", pady=(9, 0))
        ttk.Label(details, text="OPERAÇÃO", style="CardMuted.TLabel", font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(0, 5))
        self.entry_label = ttk.Label(details, text="Entrada: —", style="Card.TLabel")
        self.entry_label.pack(anchor="w", pady=2)
        self.horizon_label = ttk.Label(details, text="Horizonte: —", style="Card.TLabel")
        self.horizon_label.pack(anchor="w", pady=2)
        self.countdown_label = ttk.Label(details, text="Contagem: —", style="Card.TLabel", foreground=COLORS["accent2"])
        self.countdown_label.pack(anchor="w", pady=2)
        self.payout_label = ttk.Label(details, text="Pagamento / equilíbrio: —", style="CardMuted.TLabel", wraplength=250)
        self.payout_label.pack(anchor="w", pady=(4, 1))

        ttk.Label(panel, text="CONFLUÊNCIAS", style="Section.TLabel").pack(anchor="w", pady=(14, 7))
        self.confluence_frame = ttk.Frame(panel, style="Panel.TFrame")
        self.confluence_frame.pack(fill="x")
        self.confluence_labels: list[ttk.Label] = []
        self.blocker_label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["red"], wraplength=265)
        self.blocker_label.pack(anchor="w", pady=(10, 0))
        self.warning_label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["amber"], wraplength=265)
        self.warning_label.pack(anchor="w", pady=(6, 0))
        self.waiting_label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["muted"], wraplength=265, justify="left")
        self.waiting_label.pack(anchor="w", pady=(6, 0))
        ttk.Separator(panel).pack(fill="x", pady=14)
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
        ttk.Separator(panel).pack(fill="x", pady=14)
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
        settings.sensitivity = self.sensitivity_var.get()
        settings.mode = self.mode_var.get()
        settings.audio_enabled = self.audio_var.get()
        settings.audio_volume = self.audio_volume_var.get()
        settings.voice_pre_signal = self.pre_voice_var.get()
        settings.voice_confirmed = self.confirmed_voice_var.get()
        settings.voice_alerts = self.alert_voice_var.get()
        settings.high_impact_block_minutes = int(self.impact_block_var.get())
        settings.strict_risk_blocks = self.strict_risk_blocks_var.get()
        self.controller.save_settings()

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
        self._save_form()
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
            self.status_var.set(f"Forex ativo • {source} • atualização automática")
        else:
            self.status_var.set(f"Análise ativa • {snapshot.symbol} • {snapshot.timeframe} • {snapshot.generated_at.astimezone().strftime('%H:%M:%S')}")
        if snapshot.market == Market.CRYPTO.value:
            self._start_crypto_stream(token, context)
        else:
            self._schedule_forex_poll(token)
        self._schedule_news_refresh(token)

    def _start_crypto_stream(self, token: int, context: tuple[str, str, str]) -> None:
        symbol, timeframe = self.controller.symbol(), self.controller.settings.timeframe
        stop_event = self._stop_event
        def on_candle(candle) -> None:
            if stop_event.is_set() or token != self._analysis_token:
                return
            self.controller.websocket_online = True
            now = time.monotonic()
            self._post_ui(self._queue_live_chart, candle, token)
            if candle.closed or now - self._last_live_analysis >= LIVE_ANALYSIS_INTERVAL_SECONDS:
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
        self.updated_var.set(f"PREÇO AO VIVO • {datetime.now().strftime('%H:%M:%S')}")

    def _process_live(self, candle, token: int, context: tuple[str, str, str]) -> None:
        if self._stop_event.is_set() or self._task_running or token != self._analysis_token:
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

    def _stop_feeds(self) -> None:
        self._stop_event.set()
        self.controller.websocket_online = False
        if self._forex_poll_job is not None:
            self.after_cancel(self._forex_poll_job)
            self._forex_poll_job = None
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
        def f(key, digits=2):
            value = last.get(key)
            return "—" if pd.isna(value) else f"{float(value):,.{digits}f}"
        ema_trend = "ALTA" if last["ema_9"] > last["ema_21"] > last["ema_50"] else "BAIXA" if last["ema_9"] < last["ema_21"] < last["ema_50"] else "MISTA"
        values = {
            "ema": f"9/21/50  {ema_trend}", "rsi": f"14  {f('rsi_14', 1)}", "macd": f"Hist {f('macd_hist', 4)}",
            "bb": f"{f('bb_lower', 2)} – {f('bb_upper', 2)}", "stoch": f"K {f('stoch_k', 1)} / D {f('stoch_d', 1)}",
            "adx": f"14  {f('adx_14', 1)}", "atr": f"14  {f('atr_14', 4)}", "vwap": f('vwap', 4),
            "obv": f('obv', 0), "cci": f"20  {f('cci_20', 1)}", "williams": f('williams_r', 1),
            "fib": f"{snapshot.fibonacci.nearest_ratio * 100:.1f}%  PRÓXIMO" if snapshot.fibonacci else "SEM SWING",
            "volume": f"Rel {f('volume_relative', 2)}x", "price_action": f"{snapshot.structure.trend} {' '.join(snapshot.structure.sequence)}",
            "news": f"{sum(item.high_risk for item in snapshot.news)} alto risco / {len(snapshot.news)}",
        }
        for key, text in values.items():
            self.indicator_values[key].configure(text=text)

    def _render_signal(self, snapshot: AnalysisSnapshot) -> None:
        signal = snapshot.signal
        color = COLORS["green"] if signal.direction == Direction.BUY else COLORS["red"] if signal.direction == Direction.SELL else COLORS["amber"]
        self.signal_state.configure(text=signal.state.value)
        self.signal_direction.configure(text=signal.direction.value, foreground=color)
        score_detail = f"Score: {signal.score}/100 • técnica {signal.technical_score}"
        if signal.model_score is not None:
            score_detail += f" • IA {signal.model_score}%"
        self.signal_score.configure(text=score_detail)
        self.score_var.set(signal.score)
        ordered = sorted(signal.probabilities.items(), key=lambda item: item[1], reverse=True)
        if ordered:
            self.probability_high_label.configure(text=f"Cenário dominante: {ordered[0][0]} {ordered[0][1] * 100:.1f}%")
            self.probability_low_label.configure(text=f"Cenário secundário: {ordered[-1][0]} {ordered[-1][1] * 100:.1f}%")
        else:
            self.probability_high_label.configure(text="Cenário dominante: —")
            self.probability_low_label.configure(text="Cenário secundário: —")
        if signal.calibrated_rate is not None:
            self.calibration_label.configure(text=f"Confiança calibrada: {signal.calibrated_rate * 100:.1f}% em {signal.calibrated_samples} operações semelhantes")
        else:
            self.calibration_label.configure(text=f"Histórico real em coleta: {signal.calibrated_samples}/30 • não bloqueia")
        self.validation_label.configure(text=signal.validation_note)
        self.setup_label.configure(text=f"Estratégia: {signal.setup_name}")
        self.entry_label.configure(text=f"Entrada: {signal.entry:,.4f}" if signal.entry else "Entrada: —")
        self.horizon_label.configure(text=f"Horizonte: {signal.horizon_minutes} minuto(s)")
        payout_text = (
            f"Pagamento {signal.payout_percent}% • equilíbrio "
            f"{signal.break_even_rate * 100:.2f}%"
        )
        if signal.expected_value is not None:
            payout_text += f" • expectativa {signal.expected_value * 100:+.1f}%"
        self.payout_label.configure(text=payout_text)
        for index, reason in enumerate(signal.confluences):
            if index >= len(self.confluence_labels):
                label = ttk.Label(self.confluence_frame, style="Panel.TLabel", wraplength=265, justify="left", font=("Segoe UI", 9))
                self.confluence_labels.append(label)
            label = self.confluence_labels[index]
            label.configure(text=f"● {reason}")
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
            tuple(signal.blockers),
            tuple(signal.warnings),
        )
        should_speak = voice_signature != self._last_voice_signature
        if self.audio_var.get() and should_speak:
            if signal.state == SignalState.CONFIRMED and self.confirmed_voice_var.get():
                self.voice.speak(f"Sinal de {signal.direction.value.lower()} confirmado em {snapshot.symbol}.", self.controller.settings.audio_volume)
            elif signal.state == SignalState.FORMING and self.pre_voice_var.get():
                self.voice.speak(f"Possível sinal de {signal.direction.value.lower()} em {snapshot.symbol}.", self.controller.settings.audio_volume)
            elif signal.blockers and self.alert_voice_var.get():
                self.voice.speak("Atenção. Notícia de alto impacto. Operações temporariamente bloqueadas.", self.controller.settings.audio_volume)
            elif signal.warnings and self.alert_voice_var.get():
                self.voice.speak("Atenção. Existe um aviso de risco para esta análise.", self.controller.settings.audio_volume)
        self._last_voice_signature = voice_signature

    def _start_countdown(self, snapshot: AnalysisSnapshot) -> None:
        if self._countdown_job:
            self.after_cancel(self._countdown_job)
        target = snapshot.generated_at.timestamp() + snapshot.signal.horizon_minutes * 60
        def tick() -> None:
            remaining = max(0, round(target - datetime.now(timezone.utc).timestamp()))
            self.countdown_label.configure(text=f"Contagem: {remaining // 60:02d}:{remaining % 60:02d}" if snapshot.signal.direction != Direction.WAIT else "Contagem: —")
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
                    label.configure(foreground=color, text=f"● {status.name}{suffix}")
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
        if self._ui_events_job is not None:
            self.after_cancel(self._ui_events_job)
            self._ui_events_job = None
        self.controller.save_settings()
        self.destroy()
