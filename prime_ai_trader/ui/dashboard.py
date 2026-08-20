from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
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
        self._build_variables()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(500, self._load_health)

    def _build_variables(self) -> None:
        settings = self.controller.settings
        self.market_var = tk.StringVar(value=settings.market)
        self.symbol_var = tk.StringVar(value=self.controller.symbol())
        self.timeframe_var = tk.StringVar(value=settings.timeframe)
        self.horizon_var = tk.StringVar(value=str(settings.horizon_minutes))
        self.sensitivity_var = tk.StringVar(value=settings.sensitivity)
        self.mode_var = tk.StringVar(value=settings.mode)
        self.audio_var = tk.BooleanVar(value=settings.audio_enabled)
        self.audio_volume_var = tk.IntVar(value=settings.audio_volume)
        self.pre_voice_var = tk.BooleanVar(value=settings.voice_pre_signal)
        self.confirmed_voice_var = tk.BooleanVar(value=settings.voice_confirmed)
        self.alert_voice_var = tk.BooleanVar(value=settings.voice_alerts)
        self.impact_block_var = tk.StringVar(value=str(settings.high_impact_block_minutes))
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
        ttk.Label(header, text="v0.3  •  PERFORMANCE", style="Badge.TLabel").pack(side="left", padx=(12, 0))
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
        self._combo(panel, "Sensibilidade", self.sensitivity_var, ["CONSERVADOR", "EQUILIBRADO", "RÁPIDO"], self._save_form)
        self._combo(panel, "Modo", self.mode_var, ["CONFIRMAÇÃO", "PRICE ACTION", "QUANTITATIVO"], self._save_form)
        ttk.Label(panel, text="RÁPIDO gera mais sinais e pode aumentar falsos positivos.", style="Muted.TLabel", wraplength=205).pack(anchor="w", pady=(2, 10))
        ttk.Button(panel, text="▶  INICIAR ANÁLISE", style="Accent.TButton", command=self.start_analysis).pack(fill="x", pady=(3, 4))
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
        self._combo(panel, "Bloquear antes de evento", self.impact_block_var, ["5", "10", "15"], self._save_form)
        tools = ttk.Frame(panel, style="Panel.TFrame")
        tools.pack(fill="x", pady=(12, 4))
        ttk.Button(tools, text="APIs", command=self.open_api_settings).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(tools, text="LOGS", command=self.open_logs).pack(side="left", fill="x", expand=True, padx=3)
        ttk.Button(tools, text="DESEMPENHO", command=lambda: PerformanceDialog(self, self.controller.repository.statistics())).pack(side="left", fill="x", expand=True, padx=(3, 0))
        ttk.Button(panel, text="MONITOR DE SAÚDE", command=self.open_health).pack(fill="x", pady=(0, 3))

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
        self.signal_score = ttk.Label(hero, text="Score do modelo: —", style="Card.TLabel", font=("Segoe UI Semibold", 11))
        self.signal_score.pack(anchor="w")
        self.score_bar = ttk.Progressbar(hero, style="Score.Horizontal.TProgressbar", maximum=100, variable=self.score_var)
        self.score_bar.pack(fill="x", pady=(7, 10))
        self.probability_high_label = ttk.Label(hero, text="Probabilidade alta: —", style="CardMuted.TLabel")
        self.probability_high_label.pack(anchor="w")
        self.probability_low_label = ttk.Label(hero, text="Probabilidade baixa: —", style="CardMuted.TLabel")
        self.probability_low_label.pack(anchor="w")
        self.calibration_label = ttk.Label(hero, text="Confiança calibrada: histórico insuficiente", style="CardMuted.TLabel", wraplength=250)
        self.calibration_label.pack(anchor="w", pady=(2, 0))

        details = ttk.Frame(panel, style="Card.TFrame", padding=12)
        details.pack(fill="x", pady=(9, 0))
        ttk.Label(details, text="OPERAÇÃO", style="CardMuted.TLabel", font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(0, 5))
        self.entry_label = ttk.Label(details, text="Entrada: —", style="Card.TLabel")
        self.entry_label.pack(anchor="w", pady=2)
        self.horizon_label = ttk.Label(details, text="Horizonte: —", style="Card.TLabel")
        self.horizon_label.pack(anchor="w", pady=2)
        self.countdown_label = ttk.Label(details, text="Contagem: —", style="Card.TLabel", foreground=COLORS["accent2"])
        self.countdown_label.pack(anchor="w", pady=2)

        ttk.Label(panel, text="CONFLUÊNCIAS", style="Section.TLabel").pack(anchor="w", pady=(14, 7))
        self.confluence_frame = ttk.Frame(panel, style="Panel.TFrame")
        self.confluence_frame.pack(fill="x")
        self.confluence_labels: list[ttk.Label] = []
        self.blocker_label = ttk.Label(panel, text="", style="Panel.TLabel", foreground=COLORS["red"], wraplength=265)
        self.blocker_label.pack(anchor="w", pady=(10, 0))
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
        settings.sensitivity = self.sensitivity_var.get()
        settings.mode = self.mode_var.get()
        settings.audio_enabled = self.audio_var.get()
        settings.audio_volume = self.audio_volume_var.get()
        settings.voice_pre_signal = self.pre_voice_var.get()
        settings.voice_confirmed = self.confirmed_voice_var.get()
        settings.voice_alerts = self.alert_voice_var.get()
        settings.high_impact_block_minutes = int(self.impact_block_var.get())
        self.controller.save_settings()

    def _market_changed(self) -> None:
        values = CRYPTO_DEFAULTS if self.market_var.get() == Market.CRYPTO.value else FOREX_DEFAULTS
        self.symbol_combo.configure(values=values)
        self.symbol_var.set(values[0])
        self._save_form()
        if self.market_var.get() == Market.FOREX.value and not self.controller.secrets.get("twelve_data_key"):
            self.status_var.set("Forex selecionado • configure a chave Twelve Data em APIs")
            if not self._forex_prompted:
                self._forex_prompted = True
                self.after(100, self.open_api_settings)
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
        if self.market_var.get() == Market.FOREX.value and values.get("twelve_data_key") and self._analysis_active:
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
                self.after(0, lambda: self._task_success(result, on_success, quiet))
            except Exception as exc:
                self.controller.logger.exception("Falha na tarefa: %s", label)
                self.after(0, lambda err=str(exc): self._task_error(err, quiet))
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
        messagebox.showerror("Não foi possível concluir", f"{error}\n\nVerifique sua internet e as chaves de API. Você pode tentar novamente.", parent=self)

    def start_analysis(self) -> None:
        self._save_form()
        if self.market_var.get() == Market.FOREX.value and not self.controller.secrets.get("twelve_data_key"):
            self.status_var.set("Para ativar o Forex, configure a chave Twelve Data")
            self.open_api_settings()
            return
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

    def _analysis_ready(self, snapshot: AnalysisSnapshot, token: int, context: tuple[str, str, str]) -> None:
        current = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        if token != self._analysis_token or context != current or not self._analysis_active:
            return
        self.render_snapshot(snapshot)
        if snapshot.market == Market.FOREX.value:
            self.status_var.set(f"Forex ativo • {snapshot.symbol} • próxima atualização em cerca de 2 minutos")
        else:
            self.status_var.set(f"Análise ativa • {snapshot.symbol} • {snapshot.timeframe} • {snapshot.generated_at.astimezone().strftime('%H:%M:%S')}")
        if snapshot.market == Market.CRYPTO.value:
            self._start_crypto_stream(token, context)
        else:
            self._schedule_forex_poll(token)

    def _start_crypto_stream(self, token: int, context: tuple[str, str, str]) -> None:
        symbol, timeframe = self.controller.symbol(), self.controller.settings.timeframe
        stop_event = self._stop_event
        def on_candle(candle) -> None:
            if stop_event.is_set() or token != self._analysis_token:
                return
            self.controller.websocket_online = True
            now = time.monotonic()
            self.after(0, lambda c=candle: self._queue_live_chart(c, token))
            if candle.closed or now - self._last_live_analysis >= LIVE_ANALYSIS_INTERVAL_SECONDS:
                self._last_live_analysis = now
                self.after(0, lambda c=candle: self._process_live(c, token, context))
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
        messagebox.showinfo("Treinamento concluído", f"Modelo selecionado: {report.selected_model}\nAmostras: {report.samples}\nMacro F1 fora da amostra: {selected.macro_f1 * 100:.2f}%\nBalanced accuracy: {selected.balanced_accuracy * 100:.2f}%", parent=self)
        self._load_health()
        if self._analysis_active:
            self._schedule_analysis_restart()

    def run_backtest(self) -> None:
        self._save_form()
        self._run_task("Executando backtest walk-forward…", self.controller.backtest, lambda result: (self.status_var.set("Backtest concluído"), BacktestDialog(self, result)))

    def run_radar(self) -> None:
        self._save_form()
        self._run_task("Analisando ativos do radar…", self.controller.radar, lambda items: (self.status_var.set(f"Radar: {len(items)} ativos analisados"), RadarDialog(self, items, self._radar_analyze)))

    def open_health(self) -> None:
        self._run_task("Executando diagnóstico dos serviços…", self.controller.health,
                       lambda statuses: (self.status_var.set("Diagnóstico concluído"), HealthDialog(self, statuses)))

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
        self.signal_score.configure(text=f"Score do modelo: {signal.score}/100")
        self.score_var.set(signal.score)
        ordered = sorted(signal.probabilities.items(), key=lambda item: item[1], reverse=True)
        if ordered:
            self.probability_high_label.configure(text=f"Probabilidade alta: {ordered[0][0]} {ordered[0][1] * 100:.1f}%")
            self.probability_low_label.configure(text=f"Probabilidade baixa: {ordered[-1][0]} {ordered[-1][1] * 100:.1f}%")
        else:
            self.probability_high_label.configure(text="Probabilidade alta: —")
            self.probability_low_label.configure(text="Probabilidade baixa: —")
        if signal.calibrated_rate is not None:
            self.calibration_label.configure(text=f"Confiança calibrada: {signal.calibrated_rate * 100:.1f}% em {signal.calibrated_samples} operações semelhantes")
        else:
            self.calibration_label.configure(text=f"Confiança calibrada: histórico insuficiente ({signal.calibrated_samples}/30)")
        self.entry_label.configure(text=f"Entrada: {signal.entry:,.4f}" if signal.entry else "Entrada: —")
        self.horizon_label.configure(text=f"Horizonte: {signal.horizon_minutes} minuto(s)")
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
        self._start_countdown(snapshot)
        voice_signature = (
            snapshot.symbol,
            snapshot.candles[-1].open_time if snapshot.candles else snapshot.generated_at,
            signal.state.value,
            signal.direction.value,
            tuple(signal.blockers),
        )
        should_speak = voice_signature != self._last_voice_signature
        if self.audio_var.get() and should_speak:
            if signal.state == SignalState.CONFIRMED and self.confirmed_voice_var.get():
                self.voice.speak(f"Sinal de {signal.direction.value.lower()} confirmado em {snapshot.symbol}.", self.controller.settings.audio_volume)
            elif signal.state == SignalState.FORMING and self.pre_voice_var.get():
                self.voice.speak(f"Possível sinal de {signal.direction.value.lower()} em {snapshot.symbol}.", self.controller.settings.audio_volume)
            elif signal.blockers and self.alert_voice_var.get():
                self.voice.speak("Atenção. Notícia de alto impacto. Operações temporariamente bloqueadas.", self.controller.settings.audio_volume)
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
                    label.configure(foreground=COLORS["green"] if status.online else COLORS["red"], text=f"● {status.name}")
            if self.winfo_exists():
                if self._health_job is not None:
                    self.after_cancel(self._health_job)
                self._health_job = self.after(60_000, self._load_health)
        threading.Thread(target=lambda: self.after(0, update, self.controller.health()), daemon=True).start()

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
        self.controller.save_settings()
        self.destroy()
