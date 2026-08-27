from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..core.models import CRYPTO_DEFAULTS, Market
from ..platform.mt5 import MT5Bridge, MT5ExecutionError, MT5UnavailableError
from .dashboard import PrimeAITraderApp


class PrimeTraderApp(PrimeAITraderApp):
    """Terminal visual do Prime Trader sobre o motor analítico da v1.2.6."""

    def __init__(self, controller) -> None:
        self.mt5 = MT5Bridge(controller.settings.mt5_terminal_path or None)
        super().__init__(controller)
        self.title("PRIME TRADER")

    def _build_variables(self) -> None:
        # Mantemos os defaults internos da 1.2.6 para compatibilidade, mas o
        # produto Prime Trader abre no perfil que apresentou melhor comportamento
        # nos testes do usuário: M1 + RÁPIDO + PRICE ACTION.
        super()._build_variables()
        settings = self.controller.settings
        settings.timeframe = "1m"
        settings.horizon_minutes = 1
        settings.sensitivity = "RÁPIDO"
        settings.mode = "PRICE ACTION"
        settings.platform_sync_enabled = False
        self.timeframe_var.set("1m")
        self.horizon_var.set("1")
        self.sensitivity_var.set("RÁPIDO")
        self.mode_var.set("PRICE ACTION")

        self.mt5_connected = tk.BooleanVar(master=self, value=False)
        # Sempre inicia desarmado por segurança, mesmo que a sessão anterior tenha
        # sido fechada com execução habilitada.
        self.mt5_armed = tk.BooleanVar(master=self, value=False)
        self.mt5_auto = tk.BooleanVar(master=self, value=False)
        self.mt5_volume = tk.StringVar(master=self, value=f"{settings.mt5_default_volume:g}")
        self.mt5_sl = tk.StringVar(master=self, value=f"{settings.mt5_default_sl:g}")
        self.mt5_tp = tk.StringVar(master=self, value=f"{settings.mt5_default_tp:g}")
        self.mt5_account_text = tk.StringVar(master=self, value="MT5 desconectado")
        self.mt5_position = tk.StringVar(master=self, value="")

    def _build_ui(self) -> None:
        self.configure(bg="#080b0d")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_prime_header()

        content = tk.Frame(self, bg="#080b0d")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        # Compatibilidade interna com o renderizador da 1.2.6. Esses widgets não
        # entram no layout e, portanto, VEX/BullEx não aparecem nem podem conectar.
        compatibility = tk.Frame(self, bg="#080b0d")
        PrimeAITraderApp._build_left(self, compatibility)
        PrimeAITraderApp._build_right(self, compatibility)

        self._build_prime_nav(content)
        self._build_center(content)
        self._build_mt5_order_panel(content)
        self._build_prime_footer()

    def _build_prime_header(self) -> None:
        header = tk.Frame(
            self, bg="#0b0f12", height=54,
            highlightbackground="#1b2328", highlightthickness=1,
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        brand = tk.Frame(header, bg="#0b0f12")
        brand.pack(side="left", padx=(16, 18), fill="y")
        tk.Label(
            brand, text="◆", bg="#0b0f12", fg="#14d8a7",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left", pady=10)
        tk.Label(
            brand, text=" PRIME TRADER", bg="#0b0f12", fg="#f2f5f7",
            font=("Segoe UI Semibold", 15),
        ).pack(side="left", pady=10)

        tabs = tk.Frame(header, bg="#0b0f12")
        tabs.pack(side="left", fill="y")
        for symbol in ("EUR/USD", "GBP/USD", "USD/JPY", "BTC/USDT"):
            tk.Button(
                tabs, text=symbol, bd=0, relief="flat", bg="#0b0f12",
                fg="#a9b3b8", activebackground="#131a1e",
                activeforeground="#ffffff", font=("Segoe UI", 9), padx=12,
                command=lambda s=symbol: self._prime_select_symbol(s),
            ).pack(side="left", fill="y")

        tk.Label(
            header, text="M1  •  RÁPIDO  •  PRICE ACTION", bg="#0b0f12",
            fg="#14d8a7", font=("Segoe UI Semibold", 9),
        ).pack(side="right", padx=16)

        # Contrato esperado pelo monitor de saúde da interface original.
        self.health_labels = {}
        hidden_health = tk.Frame(self, bg="#080b0d")
        for name in ("ÁUDIO", "DATABASE", "NEWS", "IA", "WEBSOCKET", "FOREX", "BINANCE"):
            self.health_labels[name] = ttk.Label(hidden_health, text=name)

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
            ("◎", "NOTÍCIAS", self.refresh_news_panel),
            ("◈", "RADAR", self.run_radar),
            ("⚙", "AJUSTES", self.open_api_settings),
        )
        for icon, label, command in items:
            holder = tk.Frame(rail, bg="#0a0e10")
            holder.pack(fill="x", pady=(8, 1))
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
            parent, bg="#0b0f12", width=265,
            highlightbackground="#1b2328", highlightthickness=1,
        )
        panel.grid(row=0, column=2, sticky="nse")
        panel.grid_propagate(False)

        tk.Label(
            panel, text="ORDEM", bg="#0b0f12", fg="#e8eef1",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(
            panel, textvariable=self.mt5_account_text, bg="#0b0f12",
            fg="#7f8c92", font=("Segoe UI", 8), wraplength=225, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        self.mt5_connect_button = tk.Button(
            panel, text="CONECTAR MT5", command=self._connect_mt5,
            bd=0, relief="flat", bg="#151c20", fg="#dce3e6",
            activebackground="#1d282d", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=8,
        )
        self.mt5_connect_button.pack(fill="x", padx=16, pady=(0, 12))

        self._order_field(panel, "VOLUME", self.mt5_volume)
        self._order_field(panel, "STOP LOSS (preço, 0 = sem)", self.mt5_sl)
        self._order_field(panel, "TAKE PROFIT (preço, 0 = sem)", self.mt5_tp)

        mode = tk.Frame(panel, bg="#0b0f12")
        mode.pack(fill="x", padx=16, pady=(8, 4))
        tk.Checkbutton(
            mode, text="ARMAR ORDENS REAIS", variable=self.mt5_armed,
            command=self._arm_changed, bg="#0b0f12", fg="#cbd4d8",
            selectcolor="#11171a", activebackground="#0b0f12",
            activeforeground="white", font=("Segoe UI Semibold", 8),
        ).pack(anchor="w")
        tk.Checkbutton(
            mode, text="AUTOEXECUTAR SINAL CONFIRMADO", variable=self.mt5_auto,
            command=self._auto_changed, bg="#0b0f12", fg="#cbd4d8",
            selectcolor="#11171a", activebackground="#0b0f12",
            activeforeground="white", font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(5, 0))

        tk.Button(
            panel, text="▲  COMPRAR", command=lambda: self._send_manual_order("BUY"),
            bd=0, relief="flat", bg="#08a66f", fg="white",
            activebackground="#0bc082", font=("Segoe UI Semibold", 12), pady=13,
        ).pack(fill="x", padx=16, pady=(14, 6))
        tk.Button(
            panel, text="▼  VENDER", command=lambda: self._send_manual_order("SELL"),
            bd=0, relief="flat", bg="#e14b3f", fg="white",
            activebackground="#f05a4d", font=("Segoe UI Semibold", 12), pady=13,
        ).pack(fill="x", padx=16, pady=6)

        tk.Label(
            panel, text="POSIÇÃO ABERTA", bg="#0b0f12", fg="#738087",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(18, 4))
        self.position_combo = ttk.Combobox(
            panel, textvariable=self.mt5_position, state="readonly",
        )
        self.position_combo.pack(fill="x", padx=16)
        tk.Button(
            panel, text="ENCERRAR POSIÇÃO", command=self._close_position,
            bd=0, relief="flat", bg="#20282d", fg="#f0f3f4",
            activebackground="#2b363c", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=10,
        ).pack(fill="x", padx=16, pady=(7, 6))
        tk.Button(
            panel, text="ATUALIZAR POSIÇÕES", command=self._refresh_positions,
            bd=0, relief="flat", bg="#11171a", fg="#8d9aa0",
            activebackground="#1a2327", activeforeground="white",
            font=("Segoe UI", 8), pady=7,
        ).pack(fill="x", padx=16)

        tk.Label(
            panel,
            text="A autenticação ocorre no próprio MetaTrader 5. O Prime Trader não pede nem salva a senha da corretora.",
            bg="#0b0f12", fg="#66747a", font=("Segoe UI", 8),
            wraplength=225, justify="left",
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
            footer, text="PRIME TRADER • BASE ANALÍTICA 1.2.6", bg="#090d0f",
            fg="#566269", font=("Segoe UI", 8),
        ).pack(side="right", padx=12)
        self.task_progress = ttk.Progressbar(footer, mode="indeterminate", length=100)
        self.task_progress.pack(side="right", padx=8, pady=5)

    @staticmethod
    def _order_field(parent, label: str, variable: tk.StringVar) -> None:
        tk.Label(
            parent, text=label, bg="#0b0f12", fg="#6f7c82",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(7, 3))
        tk.Entry(
            parent, textvariable=variable, bg="#11171a", fg="#eef2f4",
            insertbackground="white", relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#202a2f", font=("Segoe UI", 10),
        ).pack(fill="x", padx=16, ipady=7)

    def _prime_select_symbol(self, symbol: str) -> None:
        if symbol in CRYPTO_DEFAULTS:
            self.market_var.set(Market.CRYPTO.value)
        else:
            self.market_var.set(Market.FOREX.value)
        self._market_changed()
        self.symbol_var.set(symbol)
        self.timeframe_var.set("1m")
        self.horizon_var.set("1")
        self.sensitivity_var.set("RÁPIDO")
        self.mode_var.set("PRICE ACTION")
        self._save_form()
        self.refresh_analysis()

    def _connect_mt5(self) -> None:
        try:
            self.mt5.terminal_path = self.controller.settings.mt5_terminal_path or None
            account = self.mt5.connect()
            self.mt5_connected.set(True)
            self.mt5_account_text.set(
                f"Conectado • {account.server}\nConta {account.login} • "
                f"{account.currency} • patrimônio {account.equity:.2f}"
            )
            self.mt5_connect_button.configure(text="MT5 CONECTADO", bg="#0c6f58")
            self._refresh_positions()
        except (MT5UnavailableError, MT5ExecutionError) as exc:
            self.mt5_connected.set(False)
            self.mt5_account_text.set(str(exc))
            messagebox.showerror("Prime Trader • MT5", str(exc), parent=self)

    def _arm_changed(self) -> None:
        if self.mt5_armed.get():
            accepted = messagebox.askyesno(
                "Armar execução real",
                "Os botões COMPRAR/VENDER poderão enviar ordens reais para a conta conectada no MT5. Deseja armar?",
                parent=self,
            )
            if not accepted:
                self.mt5_armed.set(False)
                return
        self.controller.settings.mt5_execution_armed = bool(self.mt5_armed.get())
        self.controller.save_settings()

    def _auto_changed(self) -> None:
        if self.mt5_auto.get() and not self.mt5_armed.get():
            self.mt5_auto.set(False)
            messagebox.showwarning(
                "Prime Trader", "Arme a execução real antes de ativar a autoexecução.",
                parent=self,
            )
            return
        self.controller.settings.mt5_auto_execute_signals = bool(self.mt5_auto.get())
        self.controller.save_settings()

    def _send_manual_order(self, side: str) -> None:
        if not self.mt5_connected.get():
            self._connect_mt5()
            if not self.mt5_connected.get():
                return
        try:
            symbol = self._mt5_symbol(self.symbol_var.get())
            volume = float(self.mt5_volume.get().replace(",", "."))
            sl = float(self.mt5_sl.get().replace(",", ".") or 0)
            tp = float(self.mt5_tp.get().replace(",", ".") or 0)
            kwargs = dict(
                symbol=symbol, volume=volume, sl=sl, tp=tp,
                deviation=self.controller.settings.mt5_deviation_points,
                armed=bool(self.mt5_armed.get()),
            )
            result = self.mt5.buy(**kwargs) if side == "BUY" else self.mt5.sell(**kwargs)
            self.status_var.set(
                f"MT5: ordem executada • {result.deal or result.order} • {result.price}"
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
            messagebox.showinfo(
                "Prime Trader", "Nenhuma posição aberta selecionada.", parent=self,
            )
            return
        try:
            ticket = int(raw.split("|", 1)[0].strip())
            result = self.mt5.close_position(
                ticket, deviation=self.controller.settings.mt5_deviation_points,
                armed=bool(self.mt5_armed.get()),
            )
            self.status_var.set(
                f"MT5: posição {ticket} encerrada • negócio {result.deal}"
            )
            self._refresh_positions()
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            messagebox.showerror("Prime Trader • Encerrar", str(exc), parent=self)

    @staticmethod
    def _mt5_symbol(symbol: str) -> str:
        return symbol.replace("/", "")

    # Wrappers diretos mantêm o contrato de botões auditável: cada handler
    # referenciado por esta classe existe explicitamente nela.
    def start_analysis(self):
        return super().start_analysis()

    def refresh_analysis(self):
        return super().refresh_analysis()

    def open_performance(self):
        return super().open_performance()

    def open_decision_history(self):
        return super().open_decision_history()

    def refresh_news_panel(self):
        return super().refresh_news_panel()

    def run_radar(self):
        return super().run_radar()

    def open_api_settings(self):
        return super().open_api_settings()

    def _close(self) -> None:
        try:
            self.mt5.disconnect()
        finally:
            super()._close()
