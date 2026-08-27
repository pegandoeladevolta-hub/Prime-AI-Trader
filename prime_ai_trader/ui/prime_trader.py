from __future__ import annotations

import os
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from ..core.models import Direction, SignalState
from ..platform.mt5 import (
    MT5TerminalSnapshot,
    MT5TradeResult,
    MetaTrader5Gateway,
)
from ..platform.mt5_analysis import MT5AnalysisAdapter
from .chart import CandleChart
from .dashboard import PrimeAITraderApp
from .theme import COLORS


class PrimeTraderApp(PrimeAITraderApp):
    """Prime Trader: motor analítico v1.2.6 com execução via MetaTrader 5.

    A tela principal segue a organização de um terminal de negociação: trilho
    lateral estreito, ativos no topo, gráfico dominante e boleta à direita.
    VEX/BullEx não fazem parte do fluxo desta interface.
    """

    MT5_POLL_MS = 2_000

    def __init__(self, controller) -> None:
        super().__init__(controller)
        self.title("PRIME TRADER")
        self.geometry("1660x930")
        self.minsize(1240, 760)

    def _build_variables(self) -> None:
        settings = self.controller.settings
        # A primeira abertura do Prime Trader aplica a combinação que foi
        # aprovada no uso da v1.2.6, sem alterar os defaults internos do motor.
        if not settings.prime_trader_profile_initialized:
            settings.timeframe = "1m"
            settings.horizon_minutes = 1
            settings.sensitivity = "RÁPIDO"
            settings.mode = "PRICE ACTION"
            settings.prime_trader_profile_initialized = True
        settings.platform_name = "MT5"
        settings.platform_sync_enabled = False
        settings.bullex_sync_authorized = False
        settings.platform_auto_asset = False
        settings.platform_auto_payout = False
        settings.platform_auto_horizon = False
        settings.platform_block_mismatch = False
        settings.execution_mode = "SINAIS MANUAIS"
        self.controller.settings_store.save(settings)
        super()._build_variables()
        self.mt5_status_var = tk.StringVar(value="MT5 DESCONECTADO")
        self.mt5_mode_var = tk.StringVar(value="SEM CONTA")
        self.mt5_balance_var = tk.StringVar(value="R$ —")
        self.mt5_equity_var = tk.StringVar(value="Patrimônio R$ —")
        self.mt5_profit_var = tk.StringVar(value="P&L R$ —")
        self.mt5_symbol_var = tk.StringVar(value=settings.mt5_symbol or "")
        self.mt5_contracts_var = tk.StringVar(value=str(max(1, settings.mt5_contracts)))
        self.mt5_auto_execute_var = tk.BooleanVar(value=False)
        self.mt5_live_status_var = tk.StringVar(value="ORDENS REAIS BLOQUEADAS")
        self.mt5_position_var = tk.StringVar(value="Nenhuma posição aberta")
        self.mt5_terminal_var = tk.StringVar(value=settings.mt5_terminal_path or "Detecção automática")
        self._mt5_gateway = MetaTrader5Gateway()
        self._mt5_adapter = MT5AnalysisAdapter(self.controller)
        self._mt5_poll_job = None
        self._mt5_polling = False
        self._mt5_symbols: list[str] = []
        self._mt5_positions: list[dict] = []
        self._auto_order_signature = None
        self._last_account_snapshot: MT5TerminalSnapshot | None = None
        self._active_drawer = ""

    def _build_ui(self) -> None:
        self._configure_prime_styles()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_prime_header()

        body = tk.Frame(self, bg=COLORS["bg"])
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(2, weight=1)
        self._prime_body = body

        self._build_prime_rail(body)
        self._build_analysis_drawer(body)
        self._build_signal_drawer(body)
        self._build_settings_drawer(body)
        self._build_prime_chart(body)
        self._build_trade_panel(body)

        self.analysis_drawer.grid_remove()
        self.signal_drawer.grid_remove()
        self.settings_drawer.grid_remove()
        self._build_prime_footer()

    def _configure_prime_styles(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "Rail.TButton", background=COLORS["bg"], foreground=COLORS["muted"],
            borderwidth=0, padding=(4, 10), font=("Segoe UI Semibold", 8),
        )
        style.map(
            "Rail.TButton", background=[("active", COLORS["card"])],
            foreground=[("active", COLORS["text"])],
        )
        style.configure(
            "ActiveRail.TButton", background=COLORS["green_dark"],
            foreground=COLORS["green"], borderwidth=0, padding=(4, 10),
            font=("Segoe UI Semibold", 8),
        )
        style.configure(
            "AssetTab.TButton", background=COLORS["card_alt"], foreground=COLORS["muted"],
            bordercolor=COLORS["border"], padding=(10, 7), font=("Segoe UI Semibold", 8),
        )
        style.configure(
            "ActiveAssetTab.TButton", background=COLORS["card"], foreground=COLORS["text"],
            bordercolor=COLORS["green"], padding=(10, 7), font=("Segoe UI Semibold", 8),
        )
        style.configure(
            "Buy.TButton", background=COLORS["green"], foreground="#FFFFFF",
            bordercolor=COLORS["green"], padding=(12, 12), font=("Segoe UI", 14, "bold"),
        )
        style.map("Buy.TButton", background=[("active", "#57D85A"), ("disabled", COLORS["green_dark"])])
        style.configure(
            "Sell.TButton", background=COLORS["red"], foreground="#FFFFFF",
            bordercolor=COLORS["red"], padding=(12, 12), font=("Segoe UI", 14, "bold"),
        )
        style.map("Sell.TButton", background=[("active", "#FF5366"), ("disabled", COLORS["card_alt"])])
        style.configure(
            "Live.TButton", background=COLORS["amber"], foreground="#101010",
            bordercolor=COLORS["amber"], padding=(8, 8), font=("Segoe UI", 9, "bold"),
        )

    # ------------------------------------------------------------------ header
    def _build_prime_header(self) -> None:
        header = tk.Frame(
            self, bg=COLORS["bg"], height=68,
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(2, weight=1)

        brand = tk.Frame(header, bg=COLORS["bg"], width=150)
        brand.grid(row=0, column=0, sticky="nsw", padx=(14, 7), pady=9)
        brand.grid_propagate(False)
        tk.Label(
            brand, text="P", bg=COLORS["green"], fg="#FFFFFF",
            font=("Segoe UI", 18, "bold"), width=2,
        ).pack(side="left")
        tk.Label(
            brand, text="PRIME\nTRADER", bg=COLORS["bg"], fg=COLORS["text"],
            font=("Segoe UI Semibold", 9), justify="left",
        ).pack(side="left", padx=(7, 0))

        ttk.Button(
            header, text="▦", style="AssetTab.TButton", width=3,
            command=lambda: self._show_drawer("analysis"),
        ).grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 7))

        self.asset_tab_holder = tk.Frame(header, bg=COLORS["bg"])
        self.asset_tab_holder.grid(row=0, column=2, sticky="w", pady=9)
        self._render_asset_tabs([])

        account = tk.Frame(header, bg=COLORS["bg"])
        account.grid(row=0, column=3, sticky="e", padx=(8, 13), pady=7)
        self.mt5_connection_label = tk.Label(
            account, textvariable=self.mt5_status_var, bg=COLORS["bg"], fg=COLORS["muted"],
            font=("Segoe UI", 8),
        )
        self.mt5_connection_label.grid(row=0, column=0, columnspan=2, sticky="e")
        self.mt5_mode_label = tk.Label(
            account, textvariable=self.mt5_mode_var, bg=COLORS["bg"], fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
        )
        self.mt5_mode_label.grid(row=1, column=0, sticky="e", padx=(0, 9))
        self.mt5_balance_label = tk.Label(
            account, textvariable=self.mt5_balance_var, bg=COLORS["bg"], fg=COLORS["amber"],
            font=("Segoe UI", 16, "bold"),
        )
        self.mt5_balance_label.grid(row=1, column=1, sticky="e")
        self.mt5_connect_button = ttk.Button(
            account, text="CONECTAR MT5", style="Secondary.TButton",
            command=self.connect_mt5,
        )
        self.mt5_connect_button.grid(row=0, column=2, rowspan=2, padx=(12, 0), sticky="ns")
        self.health_labels = {}

    def _render_asset_tabs(self, symbols: list[str]) -> None:
        for child in self.asset_tab_holder.winfo_children():
            child.destroy()
        preferred = [
            symbol for symbol in symbols
            if symbol.upper().startswith(("WIN", "WDO", "IND", "DOL"))
        ]
        choices = preferred[:4] or symbols[:4]
        current = self.mt5_symbol_var.get()
        if not choices:
            ttk.Button(
                self.asset_tab_holder, text="MT5 • conecte sua conta",
                style="AssetTab.TButton", state="disabled",
                command=self.connect_mt5,
            ).pack(side="left")
            return
        if current not in choices:
            current = choices[0]
            self.mt5_symbol_var.set(current)
        self.asset_tab_buttons = {}
        for symbol in choices:
            button = ttk.Button(
                self.asset_tab_holder,
                text=f"◆  {symbol}\nMetaTrader 5",
                style="ActiveAssetTab.TButton" if symbol == current else "AssetTab.TButton",
                command=lambda value=symbol: self._select_mt5_symbol(value),
            )
            button.pack(side="left", padx=(0, 6))
            self.asset_tab_buttons[symbol] = button
        ttk.Button(
            self.asset_tab_holder, text="+", style="AssetTab.TButton", width=3,
            command=self._refresh_mt5_symbols,
        ).pack(side="left")

    # ------------------------------------------------------------------- rail
    def _build_prime_rail(self, parent) -> None:
        rail = tk.Frame(
            parent, bg=COLORS["bg"], width=78,
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        rail.grid(row=0, column=0, sticky="nsw")
        rail.grid_propagate(False)
        self.rail_buttons = {}
        items = (
            ("graph", "⌁\nGráfico", lambda: self._show_drawer("")),
            ("signals", "◉\nSinais", lambda: self._show_drawer("signals")),
            ("history", "◷\nHistórico", self.open_mt5_history),
            ("analysis", "✦\nAnálise", lambda: self._show_drawer("analysis")),
            ("news", "◎\nNotícias", self.open_market_news),
            ("settings", "⚙\nAjustes", lambda: self._show_drawer("settings")),
        )
        for key, text, command in items:
            button = ttk.Button(
                rail, text=text,
                style="ActiveRail.TButton" if key == "graph" else "Rail.TButton",
                command=command,
            )
            button.pack(fill="x", pady=(5, 0), padx=3)
            self.rail_buttons[key] = button
        ttk.Button(
            rail, text="↻\nAtualizar", style="Rail.TButton",
            command=self.refresh_analysis,
        ).pack(side="bottom", fill="x", pady=5, padx=3)

    def _show_drawer(self, name: str) -> None:
        self.analysis_drawer.grid_remove()
        self.signal_drawer.grid_remove()
        self.settings_drawer.grid_remove()
        if name == "analysis":
            self.analysis_drawer.grid()
            active = "analysis"
        elif name == "signals":
            self.signal_drawer.grid()
            active = "signals"
        elif name == "settings":
            self.settings_drawer.grid()
            active = "settings"
        else:
            active = "graph"
        self._active_drawer = name
        for key, button in self.rail_buttons.items():
            button.configure(style="ActiveRail.TButton" if key == active else "Rail.TButton")

    # -------------------------------------------------------------- analysis UI
    def _build_analysis_drawer(self, parent) -> None:
        outer = tk.Frame(
            parent, bg=COLORS["panel"], width=300,
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        outer.grid(row=0, column=1, sticky="nsw")
        outer.grid_propagate(False)
        self.analysis_drawer = outer
        panel = tk.Frame(outer, bg=COLORS["panel"])
        panel.pack(fill="both", expand=True, padx=13, pady=12)

        tk.Label(
            panel, text="ANÁLISE", bg=COLORS["panel"], fg=COLORS["text"],
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")
        tk.Label(
            panel, text="Motor da v1.2.6 preservado", bg=COLORS["panel"], fg=COLORS["green"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(1, 12))

        self._drawer_label(panel, "Ativo MetaTrader 5")
        self.mt5_symbol_combo = ttk.Combobox(
            panel, textvariable=self.mt5_symbol_var, values=[], state="readonly",
        )
        self.mt5_symbol_combo.pack(fill="x", pady=(0, 7))
        self.mt5_symbol_combo.bind("<<ComboboxSelected>>", lambda _: self._select_mt5_symbol(self.mt5_symbol_var.get()))

        self._drawer_label(panel, "Sensibilidade")
        ttk.Combobox(
            panel, textvariable=self.sensitivity_var,
            values=["RÁPIDO", "EQUILIBRADO", "CONSERVADOR"], state="readonly",
        ).pack(fill="x", pady=(0, 7))

        self._drawer_label(panel, "Modo")
        ttk.Combobox(
            panel, textvariable=self.mode_var,
            values=["PRICE ACTION", "CONFIRMAÇÃO", "QUANTITATIVO"], state="readonly",
        ).pack(fill="x", pady=(0, 7))

        self._drawer_label(panel, "Horizonte da análise")
        ttk.Combobox(
            panel, textvariable=self.horizon_var,
            values=["1", "2", "3", "5", "10", "15"], state="readonly",
        ).pack(fill="x", pady=(0, 8))

        ttk.Button(
            panel, text="▶  INICIAR ANÁLISE", style="Accent.TButton",
            command=self.start_analysis,
        ).pack(fill="x", pady=(6, 4))
        ttk.Button(
            panel, text="Ⅱ  PAUSAR", style="Secondary.TButton",
            command=self.pause_analysis,
        ).pack(fill="x", pady=4)
        ttk.Button(
            panel, text="↻  ATUALIZAR ATIVOS MT5", style="Secondary.TButton",
            command=self._refresh_mt5_symbols,
        ).pack(fill="x", pady=4)
        ttk.Button(
            panel, text="APLICAR CONFIGURAÇÃO 1M / RÁPIDO / PRICE ACTION",
            style="Secondary.TButton", command=self._apply_recommended_profile,
        ).pack(fill="x", pady=(4, 8))

        self.profile_hint_label = tk.Label(
            panel, textvariable=self.profile_hint_var, bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8), wraplength=265, justify="left",
        )
        self.profile_hint_label.pack(anchor="w", pady=(4, 0))

    def _drawer_label(self, parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", pady=(3, 3))

    def _apply_recommended_profile(self) -> None:
        self.timeframe_var.set("1m")
        self.horizon_var.set("1")
        self.sensitivity_var.set("RÁPIDO")
        self.mode_var.set("PRICE ACTION")
        self._refresh_timeframe_buttons()
        self._save_form()
        self.status_var.set("Configuração aplicada: 1m • RÁPIDO • PRICE ACTION")
        if self._analysis_active and self._mt5_gateway.connected:
            self.start_analysis()

    # --------------------------------------------------------------- signal UI
    def _build_signal_drawer(self, parent) -> None:
        holder = tk.Frame(parent, bg=COLORS["panel"], width=350)
        holder.grid(row=0, column=1, sticky="nsw")
        holder.grid_propagate(False)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(2, weight=1)
        self.signal_drawer = holder
        super()._build_right(holder)

    # ------------------------------------------------------------- settings UI
    def _build_settings_drawer(self, parent) -> None:
        outer = tk.Frame(
            parent, bg=COLORS["panel"], width=300,
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        outer.grid(row=0, column=1, sticky="nsw")
        outer.grid_propagate(False)
        self.settings_drawer = outer
        panel = tk.Frame(outer, bg=COLORS["panel"])
        panel.pack(fill="both", expand=True, padx=13, pady=12)
        tk.Label(
            panel, text="AJUSTES", bg=COLORS["panel"], fg=COLORS["text"],
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", pady=(0, 10))

        self._drawer_label(panel, "Terminal MetaTrader 5")
        tk.Label(
            panel, textvariable=self.mt5_terminal_var, bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8), wraplength=265, justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 5))
        ttk.Button(
            panel, text="LOCALIZAR terminal64.exe", style="Secondary.TButton",
            command=self._choose_mt5_terminal,
        ).pack(fill="x", pady=(0, 8))

        ttk.Checkbutton(
            panel, text="Alertas de voz", variable=self.audio_var,
            command=self._save_form,
        ).pack(anchor="w", pady=(6, 2))
        self._drawer_label(panel, "Volume da voz")
        ttk.Scale(
            panel, from_=0, to=100, variable=self.audio_volume_var,
            command=lambda _: self._save_form(),
        ).pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(
            panel, text="Bloqueios estritos de risco", variable=self.strict_risk_blocks_var,
            command=self._save_form,
        ).pack(anchor="w", pady=(2, 10))
        ttk.Button(panel, text="ABRIR LOGS", style="Secondary.TButton", command=self._open_logs).pack(fill="x", pady=3)
        ttk.Button(panel, text="MONITOR DE SAÚDE", style="Secondary.TButton", command=self._open_health).pack(fill="x", pady=3)
        ttk.Button(panel, text="APIs AUXILIARES", style="Secondary.TButton", command=self._open_api_settings).pack(fill="x", pady=3)

        tk.Label(
            panel,
            text=(
                "O Prime Trader não pede nem armazena a senha da corretora. "
                "Faça login diretamente no MetaTrader 5 oficial."
            ),
            bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8),
            wraplength=265, justify="left",
        ).pack(side="bottom", anchor="w", pady=10)

    def _open_logs(self) -> None:
        super().open_logs()

    def _open_health(self) -> None:
        super().open_health()

    def _open_api_settings(self) -> None:
        super().open_api_settings()

    def _choose_mt5_terminal(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Selecione terminal64.exe do MetaTrader 5",
            filetypes=[("MetaTrader 5", "terminal64.exe"), ("Executáveis", "*.exe")],
        )
        if not path:
            return
        if os.path.basename(path).lower() != "terminal64.exe":
            messagebox.showerror("MetaTrader 5", "Selecione o arquivo terminal64.exe.", parent=self)
            return
        self.controller.settings.mt5_terminal_path = path
        self.mt5_terminal_var.set(path)
        self._save_form()
        self.status_var.set("Caminho do MetaTrader 5 salvo")

    # ------------------------------------------------------------------- chart
    def _build_prime_chart(self, parent) -> None:
        shell = tk.Frame(parent, bg=COLORS["bg"])
        shell.grid(row=0, column=2, sticky="nsew")
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)
        self.chart_shell = shell

        center = tk.Frame(
            shell, bg=COLORS["panel"],
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        center.grid(row=0, column=0, sticky="nsew")
        center.grid_rowconfigure(2, weight=1)
        center.grid_columnconfigure(0, weight=1)

        toolbar = tk.Frame(center, bg=COLORS["panel"])
        toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=(5, 0))
        self.timeframe_buttons = {}
        for timeframe in ("1m", "3m", "5m", "15m", "30m", "1h", "4h"):
            button = ttk.Button(
                toolbar, text=timeframe, style="Timeframe.TButton", width=3,
                command=lambda value=timeframe: self._set_timeframe(value),
            )
            button.pack(side="left", padx=(0, 1))
            self.timeframe_buttons[timeframe] = button
        self._refresh_timeframe_buttons()
        for text, name in (
            ("S/R", "sr"), ("FIB", "fibonacci"), ("EMA", "ema"),
            ("BB", "bollinger"), ("TOPOS", "swings"), ("TEND", "trend"),
            ("SINAIS", "signals"), ("S/A", "levels"),
        ):
            ttk.Button(
                toolbar, text=text, style="Tool.TButton",
                width=4 if len(text) <= 4 else 6,
                command=lambda n=name: self._toggle_overlay(n),
            ).pack(side="right", padx=1)
        ttk.Button(
            toolbar, text="FIT", style="Tool.TButton", width=3,
            command=lambda: self.chart.fit(),
        ).pack(side="right", padx=1)

        summary = tk.Frame(center, bg=COLORS["panel"])
        summary.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        tk.Label(
            summary, textvariable=self.context_var, bg=COLORS["panel"], fg=COLORS["text"],
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")
        tk.Label(
            summary, textvariable=self.ohlc_var, bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(10, 0))
        tk.Label(
            summary, textvariable=self.updated_var, bg=COLORS["panel"], fg=COLORS["green"],
            font=("Segoe UI", 8),
        ).pack(side="right")

        self.chart = CandleChart(center, on_ohlc=self.ohlc_var.set)
        self.chart.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 5))

    def _set_timeframe(self, timeframe: str) -> None:
        self.timeframe_var.set(timeframe)
        self._refresh_timeframe_buttons()
        self._save_form()
        if self._analysis_active and self._mt5_gateway.connected:
            self.start_analysis()

    # --------------------------------------------------------------- trade pane
    def _build_trade_panel(self, parent) -> None:
        panel = tk.Frame(
            parent, bg=COLORS["panel"], width=248,
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        panel.grid(row=0, column=3, sticky="nse")
        panel.grid_propagate(False)
        self.mt5_trade_panel = panel

        tk.Label(
            panel, text="ORDEM MT5", bg=COLORS["panel"], fg=COLORS["text"],
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", padx=13, pady=(13, 2))
        tk.Label(
            panel, textvariable=self.mt5_live_status_var, bg=COLORS["panel"], fg=COLORS["amber"],
            font=("Segoe UI Semibold", 8), wraplength=215, justify="left",
        ).pack(anchor="w", padx=13, pady=(0, 10))

        self._trade_value_control(panel, "Contratos / volume", self.mt5_contracts_var)
        ttk.Checkbutton(
            panel, text="Execução automática do sinal", variable=self.mt5_auto_execute_var,
            command=self._auto_execute_changed,
        ).pack(anchor="w", padx=12, pady=(8, 6))
        self.mt5_live_button = ttk.Button(
            panel, text="HABILITAR ORDENS REAIS", style="Live.TButton",
            command=self._toggle_live_trading,
        )
        self.mt5_live_button.pack(fill="x", padx=10, pady=(2, 10))

        tk.Frame(panel, bg=COLORS["border"], height=1).pack(fill="x", padx=10, pady=5)
        tk.Label(
            panel, text="RESULTADO ATUAL", bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=13, pady=(5, 0))
        self.mt5_profit_label = tk.Label(
            panel, textvariable=self.mt5_profit_var, bg=COLORS["panel"], fg=COLORS["green"],
            font=("Segoe UI", 17, "bold"),
        )
        self.mt5_profit_label.pack(anchor="w", padx=13, pady=(2, 0))
        tk.Label(
            panel, textvariable=self.mt5_equity_var, bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8), wraplength=215,
        ).pack(anchor="w", padx=13, pady=(0, 10))

        self.buy_button = ttk.Button(
            panel, text="↗  COMPRAR", style="Buy.TButton", state="disabled",
            command=lambda: self._manual_order("BUY"),
        )
        self.buy_button.pack(fill="x", padx=10, pady=(4, 6), ipady=4)
        self.sell_button = ttk.Button(
            panel, text="↘  VENDER", style="Sell.TButton", state="disabled",
            command=lambda: self._manual_order("SELL"),
        )
        self.sell_button.pack(fill="x", padx=10, pady=6, ipady=4)
        self.close_button = ttk.Button(
            panel, text="■  ENCERRAR POSIÇÃO", style="Secondary.TButton", state="disabled",
            command=self._close_positions,
        )
        self.close_button.pack(fill="x", padx=10, pady=6)

        tk.Frame(panel, bg=COLORS["border"], height=1).pack(fill="x", padx=10, pady=8)
        tk.Label(
            panel, text="POSIÇÃO ABERTA", bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=13)
        tk.Label(
            panel, textvariable=self.mt5_position_var, bg=COLORS["panel"], fg=COLORS["text"],
            font=("Segoe UI", 9), wraplength=215, justify="left",
        ).pack(anchor="w", padx=13, pady=(3, 8))

        tk.Label(
            panel,
            text=(
                "Manual: você clica COMPRAR/VENDER.\n"
                "Automático: somente um sinal CONFIRMADO pode disparar ordem.\n"
                "A execução real sempre começa bloqueada ao abrir o programa."
            ),
            bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8),
            wraplength=215, justify="left",
        ).pack(side="bottom", anchor="w", padx=13, pady=12)

    def _trade_value_control(self, parent, label: str, variable: tk.StringVar) -> None:
        block = tk.Frame(parent, bg=COLORS["panel"])
        block.pack(fill="x", padx=11, pady=3)
        tk.Label(
            block, text=label, bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w")
        row = tk.Frame(block, bg=COLORS["card"])
        row.pack(fill="x", pady=(3, 0))
        ttk.Button(row, text="−", style="Tool.TButton", width=3, command=lambda: self._step_contracts(-1)).pack(side="left")
        entry = ttk.Entry(row, textvariable=variable, justify="center", width=10)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<FocusOut>", lambda _: self._save_form())
        entry.bind("<Return>", lambda _: self._save_form())
        ttk.Button(row, text="+", style="Tool.TButton", width=3, command=lambda: self._step_contracts(1)).pack(side="right")

    def _step_contracts(self, change: int) -> None:
        try:
            value = int(float(self.mt5_contracts_var.get().replace(",", ".")))
        except ValueError:
            value = 1
        self.mt5_contracts_var.set(str(max(1, value + change)))
        self._save_form()

    # --------------------------------------------------------------- footer
    def _build_prime_footer(self) -> None:
        footer = tk.Frame(
            self, bg=COLORS["panel"], height=32,
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        tk.Label(footer, text="●", bg=COLORS["panel"], fg=COLORS["green"]).pack(side="left", padx=(10, 4), pady=6)
        tk.Label(
            footer, textvariable=self.status_var, bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(side="left")
        tk.Label(
            footer, text="PRIME TRADER • MOTOR v1.2.6 • MT5", bg=COLORS["panel"], fg=COLORS["text"],
            font=("Segoe UI", 8),
        ).pack(side="right", padx=11)
        self.task_progress = ttk.Progressbar(footer, mode="indeterminate", length=100)
        self.task_progress.pack(side="right", padx=8, pady=8)

    # ----------------------------------------------------------- settings save
    def _save_form(self) -> None:
        settings = self.controller.settings
        settings.timeframe = self.timeframe_var.get()
        try:
            settings.horizon_minutes = max(1, int(self.horizon_var.get()))
        except ValueError:
            settings.horizon_minutes = 1
            self.horizon_var.set("1")
        settings.sensitivity = self.sensitivity_var.get()
        settings.mode = self.mode_var.get()
        settings.audio_enabled = self.audio_var.get()
        settings.audio_volume = int(self.audio_volume_var.get())
        settings.voice_pre_signal = self.pre_voice_var.get()
        settings.voice_confirmed = self.confirmed_voice_var.get()
        settings.voice_alerts = self.alert_voice_var.get()
        settings.strict_risk_blocks = self.strict_risk_blocks_var.get()
        settings.platform_name = "MT5"
        settings.platform_sync_enabled = False
        settings.execution_mode = "SINAIS MANUAIS"
        settings.mt5_symbol = self.mt5_symbol_var.get()
        try:
            settings.mt5_contracts = max(1, int(float(self.mt5_contracts_var.get().replace(",", "."))))
        except ValueError:
            settings.mt5_contracts = 1
            self.mt5_contracts_var.set("1")
        settings.mt5_auto_execute = bool(self.mt5_auto_execute_var.get())
        self.profile_hint_var.set(
            "LEITURA RÁPIDA • direção imediata e mais oportunidades"
            if settings.sensitivity == "RÁPIDO" else
            "EQUILIBRADO • confirmação e frequência moderadas"
            if settings.sensitivity == "EQUILIBRADO" else
            "ALTA CONFIRMAÇÃO • menos sinais e maior exigência"
        )
        self.controller.settings_store.save(settings)

    # -------------------------------------------------------------- MT5 connect
    def connect_mt5(self) -> None:
        if self._mt5_gateway.connected:
            self._disconnect_mt5()
            return
        terminal_path = self.controller.settings.mt5_terminal_path
        self._run_task(
            "Conectando ao MetaTrader 5…",
            lambda: self._mt5_gateway.connect(terminal_path),
            self._mt5_connected,
        )

    def _mt5_connected(self, snapshot: MT5TerminalSnapshot) -> None:
        self._last_account_snapshot = snapshot
        self._apply_mt5_snapshot(snapshot)
        self.mt5_connect_button.configure(text="DESCONECTAR MT5")
        self.status_var.set("MetaTrader 5 conectado • carregando ativos")
        self._refresh_mt5_symbols()
        self._schedule_mt5_poll()

    def _apply_mt5_snapshot(self, snapshot: MT5TerminalSnapshot) -> None:
        self._last_account_snapshot = snapshot
        account = snapshot.account
        broker = account.company or account.server or "MetaTrader 5"
        build = snapshot.build or "—"
        day_trade = " • DAY TRADE" if "clear" in broker.lower() or "clear" in account.server.lower() else ""
        self.mt5_status_var.set(f"{broker} • MT5 {build}{day_trade}")
        self.mt5_mode_var.set(f"CONTA {account.mode}")
        currency = account.currency.upper() or "BRL"
        prefix = "R$" if currency == "BRL" else currency
        self.mt5_balance_var.set(f"{prefix} {account.balance:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."))
        self.mt5_equity_var.set(
            (f"Patrimônio {prefix} {account.equity:,.2f}").replace(",", "_").replace(".", ",").replace("_", ".")
        )
        self.mt5_profit_var.set(
            (f"P&L {prefix} {account.profit:+,.2f}").replace(",", "_").replace(".", ",").replace("_", ".")
        )
        self.mt5_connection_label.configure(fg=COLORS["green"] if snapshot.connected else COLORS["red"])
        self.mt5_mode_label.configure(fg=COLORS["red"] if account.mode == "REAL" else COLORS["green"])
        self.mt5_profit_label.configure(fg=COLORS["green"] if account.profit >= 0 else COLORS["red"])

    def _refresh_mt5_symbols(self) -> None:
        if not self._mt5_gateway.connected:
            self.status_var.set("Conecte o MetaTrader 5 para carregar os ativos")
            return
        if self._task_running:
            return
        self._run_task(
            "Carregando ativos do MetaTrader 5…",
            self._mt5_gateway.symbols,
            self._mt5_symbols_ready,
        )

    def _mt5_symbols_ready(self, symbols: list[str]) -> None:
        self._mt5_symbols = symbols
        self.mt5_symbol_combo.configure(values=symbols)
        if not symbols:
            self.status_var.set("MT5 conectado, mas nenhum ativo está visível em Observação do Mercado")
            self._render_asset_tabs([])
            return
        current = self.mt5_symbol_var.get()
        if current not in symbols:
            preferred = next((s for s in symbols if s.upper().startswith("WIN")), None)
            current = preferred or symbols[0]
            self.mt5_symbol_var.set(current)
        self._render_asset_tabs(symbols)
        self._save_form()
        self.status_var.set(f"{len(symbols)} ativos recebidos do MetaTrader 5")
        self.start_analysis()

    def _select_mt5_symbol(self, symbol: str) -> None:
        if not symbol:
            return
        self.mt5_symbol_var.set(symbol)
        self._save_form()
        if hasattr(self, "asset_tab_buttons"):
            for value, button in self.asset_tab_buttons.items():
                button.configure(style="ActiveAssetTab.TButton" if value == symbol else "AssetTab.TButton")
        if self._mt5_gateway.connected:
            self.start_analysis()

    def _disconnect_mt5(self) -> None:
        if self._mt5_poll_job is not None:
            self.after_cancel(self._mt5_poll_job)
            self._mt5_poll_job = None
        self.pause_analysis(silent=True)
        self.mt5_auto_execute_var.set(False)
        self._mt5_gateway.disconnect()
        self._last_account_snapshot = None
        self.mt5_status_var.set("MT5 DESCONECTADO")
        self.mt5_mode_var.set("SEM CONTA")
        self.mt5_balance_var.set("R$ —")
        self.mt5_equity_var.set("Patrimônio R$ —")
        self.mt5_profit_var.set("P&L R$ —")
        self.mt5_position_var.set("Nenhuma posição aberta")
        self.mt5_live_status_var.set("ORDENS REAIS BLOQUEADAS")
        self.mt5_connect_button.configure(text="CONECTAR MT5")
        self.mt5_live_button.configure(text="HABILITAR ORDENS REAIS")
        self.buy_button.configure(state="disabled")
        self.sell_button.configure(state="disabled")
        self.close_button.configure(state="disabled")
        self._render_asset_tabs([])
        self.status_var.set("MetaTrader 5 desconectado")

    # -------------------------------------------------------------- analysis
    def start_analysis(self) -> None:
        self._save_form()
        if not self._mt5_gateway.connected:
            self.status_var.set("Conecte o MetaTrader 5 para iniciar a análise")
            return
        symbol = self.mt5_symbol_var.get()
        if not symbol:
            self.status_var.set("Selecione um ativo do MetaTrader 5")
            return
        if self._task_running:
            self.status_var.set("Aguardando a tarefa atual terminar…")
            return
        self._analysis_active = True
        self._analysis_token += 1
        token = self._analysis_token
        timeframe = self.timeframe_var.get()

        def work():
            candles = self._mt5_gateway.candles(symbol, timeframe, limit=500)
            return self._mt5_adapter.analyze(candles, symbol, timeframe)

        self._run_task(
            f"Analisando {symbol} • {timeframe} • {self.sensitivity_var.get()} • {self.mode_var.get()}…",
            work,
            lambda snapshot: self._mt5_analysis_ready(snapshot, token),
        )

    def _mt5_analysis_ready(self, snapshot, token: int) -> None:
        if token != self._analysis_token or not self._analysis_active:
            return
        self.render_snapshot(snapshot)
        self.status_var.set(
            f"Análise ativa • {snapshot.symbol} • {snapshot.timeframe} • "
            f"{self.sensitivity_var.get()} • {self.mode_var.get()}"
        )
        self._schedule_mt5_poll()

    def refresh_analysis(self) -> None:
        if self._mt5_gateway.connected:
            self.start_analysis()
        else:
            self.status_var.set("Conecte o MetaTrader 5 para atualizar")

    def pause_analysis(self, silent: bool = False) -> None:
        self._analysis_active = False
        self._analysis_token += 1
        if not silent:
            self.status_var.set("Análise pausada • a conexão MT5 permanece ativa")

    def render_snapshot(self, snapshot) -> None:
        super().render_snapshot(snapshot)
        self.payout_label.configure(text="Execução: MetaTrader 5 • sem payout de opções binárias")
        if snapshot.signal.technical_levels_note:
            self.levels_note_label.configure(
                text=snapshot.signal.technical_levels_note.replace("Não executa ordens.", "Níveis podem acompanhar a ordem MT5.")
            )
        self._maybe_auto_execute(snapshot)

    # Estes cards existiam na interface quadrada anterior. No Prime Trader, o
    # gráfico fica limpo e os detalhes aparecem somente no drawer Sinais.
    def _render_indicators(self, snapshot) -> None:
        return

    def _render_insights(self, snapshot) -> None:
        return

    def _render_simulation_status(self) -> None:
        return

    def _refresh_recent_signals(self) -> None:
        return

    def _render_news(self, snapshot) -> None:
        if hasattr(self, "news_source_label"):
            self.news_source_label.configure(text="Notícias B3 ficam na aba Notícias e não alteram o sinal MT5.")
        for label in getattr(self, "news_labels", []):
            label.pack_forget()

    # ------------------------------------------------------------- live polling
    def _schedule_mt5_poll(self) -> None:
        if self._mt5_poll_job is not None:
            try:
                self.after_cancel(self._mt5_poll_job)
            except Exception:
                pass
        if self._mt5_gateway.connected:
            self._mt5_poll_job = self.after(self.MT5_POLL_MS, self._poll_mt5)

    def _poll_mt5(self) -> None:
        self._mt5_poll_job = None
        if not self._mt5_gateway.connected:
            return
        if self._mt5_polling:
            self._schedule_mt5_poll()
            return
        self._mt5_polling = True
        symbol = self.mt5_symbol_var.get()
        timeframe = self.timeframe_var.get()
        token = self._analysis_token
        analyze = self._analysis_active and bool(symbol)

        def worker() -> None:
            try:
                account = self._mt5_gateway.refresh_account()
                positions = self._mt5_gateway.positions(symbol or None)
                snapshot = None
                if analyze:
                    candles = self._mt5_gateway.candles(symbol, timeframe, limit=500)
                    snapshot = self._mt5_adapter.analyze(candles, symbol, timeframe)
                self._post_ui(self._mt5_poll_ready, account, positions, snapshot, token)
            except Exception as exc:
                self._post_ui(self._mt5_poll_failed, str(exc))

        threading.Thread(target=worker, daemon=True, name="prime-trader-mt5-poll").start()

    def _mt5_poll_ready(self, account, positions: list[dict], snapshot, token: int) -> None:
        self._mt5_polling = False
        self._apply_mt5_snapshot(account)
        self._mt5_positions = positions
        self._render_position(positions)
        if snapshot is not None and token == self._analysis_token and self._analysis_active:
            self.render_snapshot(snapshot)
        self._schedule_mt5_poll()

    def _mt5_poll_failed(self, error: str) -> None:
        self._mt5_polling = False
        self.status_var.set(f"MT5: {error[:110]}")
        self._schedule_mt5_poll()

    def _render_position(self, positions: list[dict]) -> None:
        if not positions:
            self.mt5_position_var.set("Nenhuma posição aberta")
            return
        pieces = []
        for item in positions[:3]:
            profit = float(item.get("profit") or 0.0)
            pieces.append(
                f"{item.get('symbol') or '—'} • {float(item.get('volume') or 0):g} • P&L R$ {profit:+.2f}"
            )
        if len(positions) > 3:
            pieces.append(f"+{len(positions) - 3} posição(ões)")
        self.mt5_position_var.set("\n".join(pieces))

    # ------------------------------------------------------------- real orders
    def _toggle_live_trading(self) -> None:
        if not self._mt5_gateway.connected:
            messagebox.showinfo("MetaTrader 5", "Conecte o MT5 primeiro.", parent=self)
            return
        if self._mt5_gateway.live_trading_enabled:
            self._mt5_gateway.set_live_trading_enabled(False)
            self.mt5_auto_execute_var.set(False)
            self.mt5_live_status_var.set("ORDENS REAIS BLOQUEADAS")
            self.mt5_live_button.configure(text="HABILITAR ORDENS REAIS")
            self.buy_button.configure(state="disabled")
            self.sell_button.configure(state="disabled")
            self.close_button.configure(state="disabled")
            self.status_var.set("Execução de ordens MT5 bloqueada")
            return

        account = self._last_account_snapshot
        mode = account.account.mode if account else "DESCONHECIDA"
        warning = (
            "Você está prestes a habilitar ordens em uma CONTA REAL.\n\n"
            "A partir desse momento, os botões COMPRAR, VENDER e ENCERRAR podem "
            "movimentar dinheiro pela conta atualmente aberta no MetaTrader 5.\n\n"
            "A execução automática continuará DESLIGADA até você ativá-la separadamente.\n\nContinuar?"
            if mode == "REAL" else
            "Habilitar envio de ordens pela conta atualmente aberta no MetaTrader 5?\n\n"
            "A execução automática continuará desligada até ser ativada separadamente."
        )
        if not messagebox.askyesno("Habilitar ordens MT5", warning, parent=self):
            return
        try:
            self._mt5_gateway.set_live_trading_enabled(True)
        except Exception as exc:
            messagebox.showerror("MetaTrader 5", str(exc), parent=self)
            return
        self.mt5_live_status_var.set(f"ORDENS HABILITADAS • CONTA {mode}")
        self.mt5_live_button.configure(text="BLOQUEAR ORDENS")
        self.buy_button.configure(state="normal")
        self.sell_button.configure(state="normal")
        self.close_button.configure(state="normal")
        self.status_var.set("Envio de ordens MT5 habilitado")

    def _auto_execute_changed(self) -> None:
        if self.mt5_auto_execute_var.get():
            if not self._mt5_gateway.live_trading_enabled:
                self.mt5_auto_execute_var.set(False)
                messagebox.showinfo(
                    "Execução automática",
                    "Primeiro habilite as ordens MT5. Depois ative a execução automática.",
                    parent=self,
                )
                return
            account = self._last_account_snapshot
            mode = account.account.mode if account else "DESCONHECIDA"
            if not messagebox.askyesno(
                "Execução automática",
                f"Ativar execução automática de sinais CONFIRMADOS na conta {mode}?\n\n"
                "O robô enviará no máximo uma ordem por sinal/vela. Stop e alvo técnicos "
                "serão enviados quando disponíveis.",
                parent=self,
            ):
                self.mt5_auto_execute_var.set(False)
                return
            self._auto_order_signature = None
            self.status_var.set("Execução automática MT5 ativada")
        else:
            self.status_var.set("Execução automática MT5 desativada")
        self._save_form()

    def _manual_order(self, side: str) -> None:
        if not self._mt5_gateway.live_trading_enabled:
            messagebox.showinfo("Ordem MT5", "Habilite as ordens reais antes de operar.", parent=self)
            return
        self._execute_order(side, automatic=False)

    def _maybe_auto_execute(self, snapshot) -> None:
        if not self.mt5_auto_execute_var.get() or not self._mt5_gateway.live_trading_enabled:
            return
        signal = snapshot.signal
        if signal.state != SignalState.CONFIRMED or signal.direction == Direction.WAIT:
            return
        if snapshot.symbol != self.mt5_symbol_var.get():
            return
        candle_time = snapshot.candles[-1].open_time if snapshot.candles else snapshot.generated_at
        signature = (snapshot.symbol, snapshot.timeframe, candle_time, signal.direction.value)
        if signature == self._auto_order_signature:
            return
        self._auto_order_signature = signature
        side = "BUY" if signal.direction == Direction.BUY else "SELL"
        self._execute_order(side, automatic=True, signal=signal)

    def _execute_order(self, side: str, *, automatic: bool, signal=None) -> None:
        symbol = self.mt5_symbol_var.get()
        try:
            volume = max(1, int(float(self.mt5_contracts_var.get().replace(",", "."))))
        except ValueError:
            volume = 1
            self.mt5_contracts_var.set("1")
        stop = target = None
        if signal is None and self.controller.snapshot is not None:
            candidate = self.controller.snapshot.signal
            expected = Direction.BUY if side == "BUY" else Direction.SELL
            if candidate.direction == expected:
                signal = candidate
        if signal is not None:
            stop = signal.technical_stop
            target = signal.technical_target
        label = "automática" if automatic else "manual"
        self.status_var.set(f"Enviando ordem {label} {side} • {symbol} • {volume}…")

        def worker() -> None:
            try:
                result = self._mt5_gateway.place_market_order(
                    symbol, side, volume,
                    stop_loss=stop, take_profit=target,
                    deviation=self.controller.settings.mt5_deviation,
                    comment="PrimeTrader-auto" if automatic else "PrimeTrader-manual",
                )
                self._post_ui(self._order_ready, result, automatic, side, symbol)
            except Exception as exc:
                self._post_ui(self._order_failed, str(exc), automatic)

        threading.Thread(target=worker, daemon=True, name="prime-trader-order").start()

    def _order_ready(self, result: MT5TradeResult, automatic: bool, side: str, symbol: str) -> None:
        origin = "AUTO" if automatic else "MANUAL"
        self.status_var.set(
            f"{origin} • {side} {symbol} executada • ordem {result.order or '—'} • "
            f"deal {result.deal or '—'} • preço {result.price:g}"
        )
        self._schedule_mt5_poll()

    def _order_failed(self, error: str, automatic: bool) -> None:
        origin = "automática" if automatic else "manual"
        self.status_var.set(f"Ordem {origin} rejeitada • {error[:100]}")
        if not automatic:
            messagebox.showerror("Ordem MT5 rejeitada", error, parent=self)

    def _close_positions(self) -> None:
        if not self._mt5_gateway.live_trading_enabled:
            messagebox.showinfo("Encerrar posição", "Habilite as ordens MT5 primeiro.", parent=self)
            return
        symbol = self.mt5_symbol_var.get()
        if not messagebox.askyesno(
            "Encerrar posição",
            f"Encerrar todas as posições abertas de {symbol}?",
            parent=self,
        ):
            return

        def worker() -> None:
            try:
                results = self._mt5_gateway.close_symbol_positions(symbol)
                self._post_ui(
                    lambda: self.status_var.set(f"{len(results)} posição(ões) de {symbol} encerrada(s)"),
                )
            except Exception as exc:
                self._post_ui(lambda: messagebox.showerror("Encerrar posição", str(exc), parent=self))

        threading.Thread(target=worker, daemon=True, name="prime-trader-close").start()

    # ----------------------------------------------------------- real history
    def open_mt5_history(self) -> None:
        self.rail_buttons["history"].configure(style="ActiveRail.TButton")
        if not self._mt5_gateway.connected:
            messagebox.showinfo("Histórico MT5", "Conecte o MetaTrader 5 primeiro.", parent=self)
            return
        now = datetime.now(timezone.utc)
        self._run_task(
            "Carregando histórico real do MetaTrader 5…",
            lambda: self._mt5_gateway.history(now - timedelta(days=30), now),
            self._show_mt5_history,
        )

    def _show_mt5_history(self, rows: list[dict]) -> None:
        window = tk.Toplevel(self)
        window.title("Prime Trader • Histórico MetaTrader 5")
        window.geometry("980x560")
        window.configure(bg=COLORS["bg"])
        columns = ("data", "ativo", "lado", "volume", "preco", "resultado", "ordem")
        tree = ttk.Treeview(window, columns=columns, show="headings")
        headings = {
            "data": "Data/Hora", "ativo": "Ativo", "lado": "Lado", "volume": "Volume",
            "preco": "Preço", "resultado": "Resultado", "ordem": "Ordem",
        }
        widths = {"data": 150, "ativo": 130, "lado": 85, "volume": 80, "preco": 110, "resultado": 110, "ordem": 120}
        for key in columns:
            tree.heading(key, text=headings[key])
            tree.column(key, width=widths[key], anchor="center")
        for row in sorted(rows, key=lambda item: int(item.get("time") or 0), reverse=True):
            raw_time = int(row.get("time") or 0)
            stamp = datetime.fromtimestamp(raw_time, tz=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M") if raw_time else "—"
            deal_type = int(row.get("type") or 0)
            side = "COMPRA" if deal_type == 0 else "VENDA" if deal_type == 1 else str(deal_type)
            result = float(row.get("profit") or 0) + float(row.get("commission") or 0) + float(row.get("swap") or 0)
            tree.insert("", "end", values=(
                stamp, row.get("symbol") or "—", side, row.get("volume") or 0,
                row.get("price") or 0, f"R$ {result:+.2f}", row.get("order") or "—",
            ))
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            window, text=f"Últimos 30 dias • {len(rows)} negócios retornados pelo terminal MT5",
            bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 8),
        ).pack(anchor="w", padx=12, pady=(0, 9))

    # --------------------------------------------------------------- news UI
    def open_market_news(self) -> None:
        self.rail_buttons["news"].configure(style="ActiveRail.TButton")
        symbol = self.mt5_symbol_var.get() or "Ibovespa"
        upper = symbol.upper()
        if upper.startswith("WDO") or upper.startswith("DOL"):
            query = '("dólar futuro" OR "dólar comercial" OR B3 OR Brasil)'
        elif upper.startswith("WIN") or upper.startswith("IND"):
            query = '(Ibovespa OR "índice futuro" OR B3 OR "bolsa brasileira")'
        else:
            query = f'("{symbol}" OR B3 OR Ibovespa OR "mercado brasileiro")'
        self._run_task(
            "Carregando notícias públicas do mercado brasileiro…",
            lambda: self.controller.news_provider.fetch(query, limit=20),
            lambda rows: self._show_market_news(symbol, rows),
        )

    def _show_market_news(self, symbol: str, rows) -> None:
        window = tk.Toplevel(self)
        window.title(f"Prime Trader • Notícias • {symbol}")
        window.geometry("900x600")
        window.configure(bg=COLORS["bg"])
        holder = tk.Frame(window, bg=COLORS["bg"])
        holder.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(
            holder, text=f"NOTÍCIAS • {symbol}", bg=COLORS["bg"], fg=COLORS["text"],
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w", pady=(0, 10))
        if not rows:
            tk.Label(
                holder, text="Nenhuma notícia retornada pelas fontes públicas neste momento.",
                bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 10),
            ).pack(anchor="w")
            return
        canvas = tk.Canvas(holder, bg=COLORS["bg"], highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=COLORS["bg"])
        item = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        for news in rows[:20]:
            card = tk.Frame(inner, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
            card.pack(fill="x", pady=4)
            when = news.published_at.astimezone().strftime("%d/%m %H:%M")
            tk.Label(
                card, text=f"{when} • {news.source or 'Fonte pública'} • {news.sentiment}",
                bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 8),
            ).pack(anchor="w", padx=10, pady=(8, 2))
            title = tk.Label(
                card, text=news.title, bg=COLORS["card"], fg=COLORS["accent2"],
                font=("Segoe UI Semibold", 10), wraplength=790, justify="left", cursor="hand2",
            )
            title.pack(anchor="w", padx=10, pady=(0, 8))
            if news.url:
                title.bind("<Button-1>", lambda _, url=news.url: webbrowser.open(url))

    # --------------------------------------------------------------- shutdown
    def _close(self) -> None:
        if self._mt5_poll_job is not None:
            try:
                self.after_cancel(self._mt5_poll_job)
            except Exception:
                pass
            self._mt5_poll_job = None
        try:
            self._mt5_gateway.disconnect()
        except Exception:
            pass
        self._save_form()
        super()._close()
