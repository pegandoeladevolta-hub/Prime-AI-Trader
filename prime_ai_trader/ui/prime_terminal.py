from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..core.models import Direction, Market, SignalState
from ..platform.mt5 import MT5Bridge, MT5ExecutionError, MT5UnavailableError
from ..signals.engine import sensitivity_profile
from .dashboard import PrimeAITraderApp


EXEC_SIGNALS = "SÓ SINAIS"
EXEC_COMMAND = "EXECUTAR SOB COMANDO"
EXEC_AUTO = "AUTOMÁTICO"
_TIMEFRAME_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15,
    "30m": 30, "1h": 60, "4h": 240,
}


class PrimeTraderApp(PrimeAITraderApp):
    """Terminal Prime Trader: leitura e execução vinculadas ao mesmo MT5."""

    def __init__(self, controller) -> None:
        self.mt5 = getattr(controller, "mt5", None) or MT5Bridge(
            controller.settings.mt5_terminal_path or None,
        )
        super().__init__(controller)
        self.title("PRIME TRADER")

    def _build_variables(self) -> None:
        super()._build_variables()
        settings = self.controller.settings
        settings.market_data_source = "MT5"
        settings.platform_name = "MT5"
        settings.platform_sync_enabled = False
        settings.external_context_enabled = False
        self.platform_var.set("MT5")
        self.simulation_auto_var.set(False)
        if settings.mt5_symbol:
            self.symbol_var.set(settings.mt5_symbol)

        self.mt5_connected = tk.BooleanVar(master=self, value=False)
        self.mt5_armed = tk.BooleanVar(master=self, value=False)
        self.mt5_auto = tk.BooleanVar(master=self, value=False)
        self.mt5_volume = tk.StringVar(master=self, value=f"{settings.mt5_default_volume:g}")
        self.mt5_sl = tk.StringVar(master=self, value=f"{settings.mt5_default_sl:g}")
        self.mt5_tp = tk.StringVar(master=self, value=f"{settings.mt5_default_tp:g}")
        self.mt5_account_text = tk.StringVar(master=self, value="MT5 desconectado")
        self.mt5_position = tk.StringVar(master=self, value="")
        profile = settings.mt5_execution_profile
        if profile not in {EXEC_SIGNALS, EXEC_COMMAND, EXEC_AUTO}:
            profile = EXEC_SIGNALS
        self.execution_profile_var = tk.StringVar(master=self, value=profile)
        self.current_signal_text = tk.StringVar(master=self, value="Aguardando leitura do gráfico")

    def _build_ui(self) -> None:
        self.configure(bg="#080b0d")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_prime_header()

        content = tk.Frame(self, bg="#080b0d")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        # Widgets legados são construídos fora da tela porque o motor ainda os
        # atualiza. VEX/BullEx não aparecem nem participam do fluxo MT5.
        compatibility = tk.Frame(self, bg="#080b0d")
        PrimeAITraderApp._build_left(self, compatibility)
        PrimeAITraderApp._build_right(self, compatibility)
        self.platform_var.set("MT5")

        self._build_prime_nav(content)
        self._build_center(content)
        self._build_mt5_order_panel(content)
        self._build_prime_footer()
        self._update_execution_controls()

    def _build_prime_header(self) -> None:
        header = tk.Frame(
            self, bg="#0b0f12", height=112,
            highlightbackground="#1b2328", highlightthickness=1,
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        top = tk.Frame(header, bg="#0b0f12")
        top.pack(fill="x", padx=14, pady=(7, 3))
        tk.Label(
            top, text="◆", bg="#0b0f12", fg="#14d8a7",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left")
        tk.Label(
            top, text=" PRIME TRADER", bg="#0b0f12", fg="#f2f5f7",
            font=("Segoe UI Semibold", 15),
        ).pack(side="left")
        tk.Button(
            top, text="CONECTAR AO MT5", command=self._connect_mt5,
            bd=0, relief="flat", bg="#151c20", fg="#dce3e6",
            activebackground="#1d282d", activeforeground="white",
            font=("Segoe UI Semibold", 8), padx=14, pady=6,
        ).pack(side="right")
        tk.Label(
            top, textvariable=self.mt5_account_text, bg="#0b0f12",
            fg="#738087", font=("Segoe UI", 8),
        ).pack(side="right", padx=(8, 14))

        controls = tk.Frame(header, bg="#0b0f12")
        controls.pack(fill="x", padx=14, pady=(4, 8))
        self.mt5_asset_combo = self._header_combo(
            controls, "ATIVO DO MT5", self.symbol_var,
            [self.symbol_var.get()] if self.symbol_var.get() else [], 190,
        )
        self.mt5_asset_combo.bind("<<ComboboxSelected>>", lambda _: self._configuration_changed())
        tk.Button(
            controls, text="↻", command=self._refresh_assets_button,
            bd=0, relief="flat", bg="#151c20", fg="#b9c3c7",
            activebackground="#1d282d", activeforeground="white",
            font=("Segoe UI", 9), width=3,
        ).pack(side="left", padx=(3, 10), pady=(16, 0))

        self.header_timeframe_combo = self._header_combo(
            controls, "TIME FRAME", self.timeframe_var,
            list(_TIMEFRAME_MINUTES), 72,
        )
        self.header_profile_combo = self._header_combo(
            controls, "PERFIL", self.sensitivity_var,
            ["RÁPIDO", "EQUILIBRADO", "CONSERVADOR"], 112,
        )
        self.header_mode_combo = self._header_combo(
            controls, "MODO", self.mode_var,
            ["PRICE ACTION", "CONFIRMAÇÃO", "QUANTITATIVO"], 132,
        )
        self.header_execution_combo = self._header_combo(
            controls, "EXECUÇÃO", self.execution_profile_var,
            [EXEC_SIGNALS, EXEC_COMMAND, EXEC_AUTO], 174,
        )
        for combo in (
            self.header_timeframe_combo, self.header_profile_combo,
            self.header_mode_combo,
        ):
            combo.bind("<<ComboboxSelected>>", lambda _: self._configuration_changed())
        self.header_execution_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._execution_profile_changed(),
        )

        self.health_labels = {}
        hidden_health = tk.Frame(self, bg="#080b0d")
        for name in ("ÁUDIO", "DATABASE", "NEWS", "IA", "WEBSOCKET", "FOREX", "BINANCE"):
            self.health_labels[name] = ttk.Label(hidden_health, text=name)

    @staticmethod
    def _header_combo(parent, label: str, variable, values, width_px: int):
        holder = tk.Frame(parent, bg="#0b0f12")
        holder.pack(side="left", padx=(0, 9))
        tk.Label(
            holder, text=label, bg="#0b0f12", fg="#647178",
            font=("Segoe UI Semibold", 7),
        ).pack(anchor="w")
        combo = ttk.Combobox(
            holder, textvariable=variable, values=values, state="readonly",
            font=("Segoe UI", 9), width=max(8, width_px // 9),
        )
        combo.pack(anchor="w", pady=(2, 0))
        return combo

    def _build_prime_nav(self, parent) -> None:
        rail = tk.Frame(
            parent, bg="#0a0e10", width=78,
            highlightbackground="#1b2328", highlightthickness=1,
        )
        rail.grid(row=0, column=0, sticky="nsw")
        rail.grid_propagate(False)
        items = (
            ("▥", "GRÁFICO", self.refresh_analysis),
            ("✦", "SINAIS", self.open_performance),
            ("≡", "HISTÓRICO", self.open_decision_history),
            ("⏸", "PAUSAR", self.pause_analysis),
        )
        for icon, label, command in items:
            holder = tk.Frame(rail, bg="#0a0e10")
            holder.pack(fill="x", pady=(9, 1))
            tk.Button(
                holder, text=icon, command=command, bd=0, relief="flat",
                bg="#0a0e10", fg="#aab4b9", activebackground="#12191d",
                activeforeground="#14d8a7", font=("Segoe UI Symbol", 16), pady=2,
            ).pack(fill="x")
            tk.Label(
                holder, text=label, bg="#0a0e10", fg="#6f7c82",
                font=("Segoe UI", 7),
            ).pack()
        tk.Button(
            rail, text="▶", command=self.start_analysis, bd=0, relief="flat",
            bg="#0c6f58", fg="white", activebackground="#0e8a6d",
            font=("Segoe UI", 15, "bold"), pady=8,
        ).pack(side="bottom", fill="x", padx=8, pady=(4, 12))

    def _build_mt5_order_panel(self, parent) -> None:
        panel = tk.Frame(
            parent, bg="#0b0f12", width=292,
            highlightbackground="#1b2328", highlightthickness=1,
        )
        panel.grid(row=0, column=2, sticky="nse")
        panel.grid_propagate(False)

        tk.Label(
            panel, text="OPERAÇÃO MT5", bg="#0b0f12", fg="#e8eef1",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(
            panel, textvariable=self.current_signal_text, bg="#0b0f12",
            fg="#14d8a7", font=("Segoe UI Semibold", 8),
            wraplength=255, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 9))

        self._order_field(panel, "VOLUME", self.mt5_volume)
        self._order_field(panel, "SL MANUAL (0 = sem)", self.mt5_sl)
        self._order_field(panel, "TP MANUAL (0 = sem)", self.mt5_tp)

        tk.Checkbutton(
            panel, text="ARMAR ENVIO DE ORDENS", variable=self.mt5_armed,
            command=self._arm_changed, bg="#0b0f12", fg="#cbd4d8",
            selectcolor="#11171a", activebackground="#0b0f12",
            activeforeground="white", font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", padx=16, pady=(10, 5))

        self.execute_signal_button = tk.Button(
            panel, text="✦  EXECUTAR SINAL ATUAL", command=self._execute_signal_now,
            bd=0, relief="flat", bg="#176f63", fg="white",
            activebackground="#218b7c", font=("Segoe UI Semibold", 10), pady=11,
        )
        self.execute_signal_button.pack(fill="x", padx=16, pady=(6, 8))

        manual = tk.Frame(panel, bg="#0b0f12")
        manual.pack(fill="x", padx=16)
        self.buy_button = tk.Button(
            manual, text="▲ COMPRAR", command=lambda: self._send_manual_order("BUY"),
            bd=0, relief="flat", bg="#08a66f", fg="white",
            activebackground="#0bc082", font=("Segoe UI Semibold", 10), pady=11,
        )
        self.buy_button.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.sell_button = tk.Button(
            manual, text="▼ VENDER", command=lambda: self._send_manual_order("SELL"),
            bd=0, relief="flat", bg="#e14b3f", fg="white",
            activebackground="#f05a4d", font=("Segoe UI Semibold", 10), pady=11,
        )
        self.sell_button.pack(side="left", fill="x", expand=True, padx=(3, 0))

        tk.Label(
            panel, text="POSIÇÕES ABERTAS", bg="#0b0f12", fg="#738087",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(16, 4))
        self.position_combo = ttk.Combobox(
            panel, textvariable=self.mt5_position, state="readonly",
        )
        self.position_combo.pack(fill="x", padx=16)
        tk.Button(
            panel, text="ENCERRAR POSIÇÃO", command=self._close_position,
            bd=0, relief="flat", bg="#20282d", fg="#f0f3f4",
            activebackground="#2b363c", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=9,
        ).pack(fill="x", padx=16, pady=(7, 4))
        tk.Button(
            panel, text="ATUALIZAR POSIÇÕES", command=self._refresh_positions,
            bd=0, relief="flat", bg="#11171a", fg="#8d9aa0",
            activebackground="#1a2327", activeforeground="white",
            font=("Segoe UI", 8), pady=7,
        ).pack(fill="x", padx=16)

        tk.Label(
            panel,
            text="Preço, candles, ativo e ordens usam o mesmo terminal MT5 conectado.",
            bg="#0b0f12", fg="#66747a", font=("Segoe UI", 8),
            wraplength=255, justify="left",
        ).pack(side="bottom", anchor="w", padx=16, pady=16)

    def _build_prime_footer(self) -> None:
        footer = tk.Frame(
            self, bg="#090d0f", height=28,
            highlightbackground="#1b2328", highlightthickness=1,
        )
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        tk.Label(
            footer, text="●", bg="#090d0f", fg="#14d8a7",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(12, 4))
        tk.Label(
            footer, textvariable=self.status_var, bg="#090d0f",
            fg="#78858b", font=("Segoe UI", 8),
        ).pack(side="left")
        tk.Label(
            footer, text="FONTE: METATRADER 5 • MOTOR 1.3.5", bg="#090d0f",
            fg="#566269", font=("Segoe UI", 8),
        ).pack(side="right", padx=12)
        self.task_progress = ttk.Progressbar(footer, mode="indeterminate", length=100)
        self.task_progress.pack(side="right", padx=8, pady=5)

    @staticmethod
    def _order_field(parent, label: str, variable: tk.StringVar) -> None:
        tk.Label(
            parent, text=label, bg="#0b0f12", fg="#6f7c82",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(6, 3))
        tk.Entry(
            parent, textvariable=variable, bg="#11171a", fg="#eef2f4",
            insertbackground="white", relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#202a2f", font=("Segoe UI", 10),
        ).pack(fill="x", padx=16, ipady=6)

    @staticmethod
    def _looks_crypto(symbol: str) -> bool:
        upper = symbol.upper()
        return any(token in upper for token in (
            "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH",
            "AVAX", "LINK", "XLM", "USDT", "USDC",
        ))

    def _connect_mt5(self) -> None:
        try:
            if hasattr(self.controller, "connect_mt5"):
                account = self.controller.connect_mt5()
            else:
                account = self.mt5.connect()
            account_hook = getattr(self, "_on_mt5_account_connected", None)
            if callable(account_hook):
                account_hook(account)
            self.mt5_connected.set(True)
            symbols = self.mt5.list_symbols()
            self.mt5_asset_combo.configure(values=symbols)
            selected = self.controller.symbol()
            if selected in symbols:
                self.symbol_var.set(selected)
            elif symbols:
                self.symbol_var.set(symbols[0])
                if hasattr(self.controller, "select_mt5_symbol"):
                    self.controller.select_mt5_symbol(symbols[0])
            self.market_var.set(self.controller.settings.market)
            crypto_count = sum(1 for symbol in symbols if self._looks_crypto(symbol))
            crypto_note = f" • {crypto_count} cripto" if crypto_count else " • sem cripto neste servidor"
            account_formatter = getattr(self, "_format_mt5_account_text", None)
            if callable(account_formatter):
                account_text = str(account_formatter(account, crypto_note))
            else:
                account_text = f"{account.server} • conta {account.login}{crypto_note}"
            self.mt5_account_text.set(account_text)
            self.status_var.set(
                f"MT5 conectado • {len(symbols)} ativos negociáveis carregados"
            )
            self._refresh_positions()
            self._save_form()
        except (MT5UnavailableError, MT5ExecutionError) as exc:
            self.mt5_connected.set(False)
            self.mt5_account_text.set("MT5 desconectado")
            handler = getattr(self, "_handle_mt5_connection_error", None)
            if callable(handler) and handler(exc):
                return
            messagebox.showerror("Prime Trader • MT5", str(exc), parent=self)

    def _refresh_assets_button(self) -> None:
        if not self.mt5_connected.get():
            self._connect_mt5()
            return
        try:
            symbols = self.mt5.list_symbols()
            self.mt5_asset_combo.configure(values=symbols)
            self.status_var.set(f"Lista atualizada • {len(symbols)} ativos do MT5")
        except MT5UnavailableError as exc:
            messagebox.showerror("Prime Trader • Ativos", str(exc), parent=self)

    def _configuration_changed(self) -> None:
        symbol = self.symbol_var.get().strip()
        if symbol and hasattr(self.controller, "select_mt5_symbol"):
            self.controller.select_mt5_symbol(symbol, save=False)
            self.market_var.set(self.controller.settings.market)
        timeframe = self.timeframe_var.get()
        self.horizon_var.set(str(_TIMEFRAME_MINUTES.get(timeframe, 1)))
        self._save_form()
        if hasattr(self, "timeframe_buttons"):
            self._refresh_timeframe_buttons()
        if self._analysis_active:
            self._schedule_analysis_restart()

    def _save_form(self) -> None:
        settings = self.controller.settings
        symbol = self.symbol_var.get().strip()
        if symbol and hasattr(self.controller, "select_mt5_symbol"):
            self.controller.select_mt5_symbol(symbol, save=False)
        settings.market_data_source = "MT5"
        settings.platform_name = "MT5"
        settings.platform_sync_enabled = False
        settings.external_context_enabled = False
        settings.timeframe = self.timeframe_var.get()
        settings.horizon_minutes = _TIMEFRAME_MINUTES.get(settings.timeframe, 1)
        self.horizon_var.set(str(settings.horizon_minutes))
        settings.sensitivity = self.sensitivity_var.get()
        settings.mode = self.mode_var.get()
        self.profile_hint_var.set(sensitivity_profile(settings.sensitivity).description)
        settings.execution_mode = "SINAIS MANUAIS"
        settings.mt5_execution_profile = self.execution_profile_var.get()
        settings.mt5_auto_execute_signals = bool(self.mt5_auto.get())
        settings.mt5_execution_armed = bool(self.mt5_armed.get())
        try:
            settings.mt5_default_volume = max(0.000001, float(self.mt5_volume.get().replace(",", ".")))
        except ValueError:
            self.mt5_volume.set(f"{settings.mt5_default_volume:g}")
        try:
            settings.mt5_default_sl = max(0.0, float(self.mt5_sl.get().replace(",", ".") or 0))
            settings.mt5_default_tp = max(0.0, float(self.mt5_tp.get().replace(",", ".") or 0))
        except ValueError:
            self.mt5_sl.set("0")
            self.mt5_tp.set("0")
        settings.audio_enabled = self.audio_var.get()
        settings.audio_volume = self.audio_volume_var.get()
        settings.voice_pre_signal = self.pre_voice_var.get()
        settings.voice_confirmed = self.confirmed_voice_var.get()
        settings.voice_alerts = self.alert_voice_var.get()
        self.platform_var.set("MT5")
        self.controller.save_settings()

    def _execution_profile_changed(self) -> None:
        selected = self.execution_profile_var.get()
        if selected == EXEC_AUTO:
            accepted = messagebox.askyesno(
                "Operação automática",
                "Neste modo, cada sinal confirmado poderá gerar uma ordem real no MT5. Ativar o modo automático?",
                parent=self,
            )
            if not accepted:
                self.execution_profile_var.set(EXEC_SIGNALS)
                selected = EXEC_SIGNALS
            else:
                self.mt5_armed.set(True)
                self.mt5_auto.set(True)
        elif selected == EXEC_COMMAND:
            self.mt5_auto.set(False)
        else:
            self.mt5_auto.set(False)
            self.mt5_armed.set(False)
        self._save_form()
        self._update_execution_controls()
        self.status_var.set(f"Execução: {selected.lower()}")

    def _update_execution_controls(self) -> None:
        if not hasattr(self, "buy_button"):
            return
        profile = self.execution_profile_var.get()
        state = "normal" if profile != EXEC_SIGNALS else "disabled"
        self.buy_button.configure(state=state)
        self.sell_button.configure(state=state)
        self.execute_signal_button.configure(
            state="normal" if profile == EXEC_COMMAND else "disabled",
        )

    def _arm_changed(self) -> None:
        if self.mt5_armed.get():
            accepted = messagebox.askyesno(
                "Armar envio de ordens",
                "As próximas ordens solicitadas pelo Prime Trader poderão ser enviadas ao MT5. Continuar?",
                parent=self,
            )
            if not accepted:
                self.mt5_armed.set(False)
        if not self.mt5_armed.get() and self.execution_profile_var.get() == EXEC_AUTO:
            self.execution_profile_var.set(EXEC_SIGNALS)
            self.mt5_auto.set(False)
        self._save_form()
        self._update_execution_controls()

    def _ensure_order_permission(self) -> bool:
        if self.execution_profile_var.get() == EXEC_SIGNALS:
            messagebox.showinfo(
                "Prime Trader", "O modo atual é SÓ SINAIS. Troque a execução no topo para enviar ordens.",
                parent=self,
            )
            return False
        if not self.mt5_armed.get():
            accepted = messagebox.askyesno(
                "Confirmar ordem real",
                "Esta ação pode enviar uma ordem real para a conta conectada no MT5. Deseja armar a execução?",
                parent=self,
            )
            if not accepted:
                return False
            self.mt5_armed.set(True)
            self._save_form()
        return True

    def _execute_signal_now(self) -> None:
        snapshot = self.controller.snapshot
        if not snapshot or snapshot.signal.state != SignalState.CONFIRMED:
            messagebox.showinfo(
                "Prime Trader", "Não existe um sinal confirmado neste momento.", parent=self,
            )
            return
        if snapshot.signal.direction == Direction.WAIT:
            messagebox.showinfo("Prime Trader", "A leitura atual é AGUARDAR.", parent=self)
            return
        if not self._ensure_order_permission():
            return
        try:
            volume = float(self.mt5_volume.get().replace(",", "."))
            signal = snapshot.signal
            kwargs = dict(
                symbol=snapshot.symbol,
                volume=volume,
                sl=float(signal.technical_stop or 0.0),
                tp=float(signal.technical_target or 0.0),
                deviation=self.controller.settings.mt5_deviation_points,
                armed=True,
            )
            result = (
                self.mt5.buy(**kwargs)
                if signal.direction == Direction.BUY else self.mt5.sell(**kwargs)
            )
            self.status_var.set(
                f"Sinal executado no MT5 • {signal.direction.value} • {result.deal or result.order}"
            )
            self._refresh_positions()
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            messagebox.showerror("Prime Trader • Executar sinal", str(exc), parent=self)

    def _send_manual_order(self, side: str) -> None:
        if not self._ensure_order_permission():
            return
        if not self.mt5_connected.get():
            self._connect_mt5()
            if not self.mt5_connected.get():
                return
        try:
            symbol = self.symbol_var.get().strip()
            if not symbol:
                raise MT5ExecutionError("Selecione um ativo do MT5.")
            volume = float(self.mt5_volume.get().replace(",", "."))
            sl = float(self.mt5_sl.get().replace(",", ".") or 0)
            tp = float(self.mt5_tp.get().replace(",", ".") or 0)
            kwargs = dict(
                symbol=symbol, volume=volume, sl=sl, tp=tp,
                deviation=self.controller.settings.mt5_deviation_points,
                armed=True,
            )
            result = self.mt5.buy(**kwargs) if side == "BUY" else self.mt5.sell(**kwargs)
            self.status_var.set(
                f"MT5: ordem {side} executada • {result.deal or result.order} • {result.price}"
            )
            self._refresh_positions()
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            messagebox.showerror("Prime Trader • Ordem", str(exc), parent=self)

    def _refresh_positions(self) -> None:
        if not self.mt5_connected.get():
            self.position_combo["values"] = []
            return
        try:
            rows = self.mt5.positions()
            values = [
                f"{row['ticket']} | {row['symbol']} | {row['volume']}"
                for row in rows
            ]
            self.position_combo["values"] = values
            self.mt5_position.set(values[0] if values else "")
        except (MT5ExecutionError, MT5UnavailableError):
            self.position_combo["values"] = []

    def _close_position(self) -> None:
        raw = self.mt5_position.get().strip()
        if not raw:
            messagebox.showinfo("Prime Trader", "Nenhuma posição aberta selecionada.", parent=self)
            return
        if not self._ensure_order_permission():
            return
        try:
            ticket = int(raw.split("|", 1)[0].strip())
            result = self.mt5.close_position(
                ticket,
                deviation=self.controller.settings.mt5_deviation_points,
                armed=True,
            )
            self.status_var.set(
                f"MT5: posição {ticket} encerrada • negócio {result.deal}"
            )
            self._refresh_positions()
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            messagebox.showerror("Prime Trader • Encerrar", str(exc), parent=self)

    def render_snapshot(self, snapshot) -> None:
        super().render_snapshot(snapshot)
        signal = snapshot.signal
        self.current_signal_text.set(
            f"{snapshot.symbol} • {snapshot.timeframe} • {self.sensitivity_var.get()} • "
            f"{self.mode_var.get()}\n{signal.state.value} • {signal.direction.value} • score {signal.score}/100"
        )

    def _set_timeframe(self, timeframe: str) -> None:
        self.timeframe_var.set(timeframe)
        self._configuration_changed()

    def _selection_changed(self) -> None:
        self._configuration_changed()

    def _market_changed(self) -> None:
        # O mercado é inferido do símbolo selecionado no próprio MT5.
        self._configuration_changed()

    def refresh_symbols(self) -> None:
        self._refresh_assets_button()

    def _prime_select_symbol(self, symbol: str) -> None:
        self.symbol_var.set(symbol)
        self._configuration_changed()

    def _mt5_symbol(self, symbol: str) -> str:
        return symbol

    def _auto_changed(self) -> None:
        self._execution_profile_changed()

    # Wrappers diretos para os comandos criados nesta classe.
    def start_analysis(self):
        if not self.mt5_connected.get():
            self._connect_mt5()
            if not self.mt5_connected.get():
                return None
        self._save_form()
        return super().start_analysis()

    def refresh_analysis(self):
        return super().refresh_analysis()

    def open_performance(self):
        return super().open_performance()

    def open_decision_history(self):
        return super().open_decision_history()

    def pause_analysis(self, silent: bool = False):
        return super().pause_analysis(silent=silent)

    def _close(self) -> None:
        try:
            self.mt5.disconnect()
        finally:
            super()._close()
