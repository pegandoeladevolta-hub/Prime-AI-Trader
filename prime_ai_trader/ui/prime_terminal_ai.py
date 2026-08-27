from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..platform.mt5 import MT5ExecutionError, MT5UnavailableError
from .mt5_trade_chart import MT5TradeChart
from .prime_terminal_execution import PrimeTraderApp as ExecutionPrimeTraderApp


class PrimeTraderApp(ExecutionPrimeTraderApp):
    """Prime Trader com IA contextual e gerenciamento visual das posições MT5."""

    ANALYSIS_DEPTHS = (500, 1000, 1500, 2000, 3000)
    TRAINING_DEPTHS = (2000, 3000, 5000, 10000)

    def __init__(self, controller) -> None:
        self._position_job = None
        super().__init__(controller)
        self._position_job = self.after(1200, self._position_sync_tick)
        self.after(300, self._refresh_ai_status)

    def _build_variables(self) -> None:
        super()._build_variables()
        analysis_depth = int(getattr(self.controller.settings, "mt5_analysis_candles", 2000))
        if analysis_depth not in self.ANALYSIS_DEPTHS:
            analysis_depth = 2000
        training_depth = int(getattr(self.controller.settings, "mt5_training_candles", 5000))
        if training_depth not in self.TRAINING_DEPTHS:
            training_depth = 5000
        self.analysis_candles_var = tk.StringVar(master=self, value=str(analysis_depth))
        self.training_candles_var = tk.StringVar(master=self, value=str(training_depth))
        self.ai_status_var = tk.StringVar(master=self, value="IA • verificando configuração…")
        self.ai_context_var = tk.StringVar(
            master=self,
            value=f"Análise ao vivo: {analysis_depth} candles • histórico da IA: aguardando",
        )

    def _build_center(self, parent) -> None:
        super()._build_center(parent)
        old_chart = self.chart
        center = old_chart.master
        old_chart.destroy()
        self.chart = MT5TradeChart(
            center,
            on_ohlc=self.ohlc_var.set,
            on_modify_position=self._chart_modify_position,
        )
        self.chart.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 3))

    def _build_mt5_order_panel(self, parent) -> None:
        super()._build_mt5_order_panel(parent)
        panel = next(
            (child for child in parent.winfo_children()
             if isinstance(child, tk.Frame) and int(child.cget("width") or 0) >= 280),
            None,
        )
        if panel is None:
            return
        card = tk.Frame(
            panel, bg="#0f1619", highlightbackground="#243137",
            highlightthickness=1,
        )
        packed = panel.pack_slaves()
        pack_args = dict(fill="x", padx=16, pady=(7, 10))
        if packed:
            pack_args["before"] = packed[0]
        card.pack(**pack_args)

        tk.Label(
            card, text="IA E PROFUNDIDADE DE MERCADO", bg="#0f1619", fg="#e8eef1",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=10, pady=(9, 2))
        tk.Label(
            card, textvariable=self.ai_status_var, bg="#0f1619", fg="#14d8a7",
            font=("Segoe UI Semibold", 8), wraplength=245, justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 3))
        tk.Label(
            card, textvariable=self.ai_context_var, bg="#0f1619", fg="#76858c",
            font=("Segoe UI", 7), wraplength=245, justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 7))

        analysis_row = tk.Frame(card, bg="#0f1619")
        analysis_row.pack(fill="x", padx=10, pady=(0, 5))
        tk.Label(
            analysis_row, text="ANÁLISE AO VIVO", bg="#0f1619", fg="#66757c",
            font=("Segoe UI Semibold", 7),
        ).pack(side="left")
        self.analysis_depth_combo = ttk.Combobox(
            analysis_row, textvariable=self.analysis_candles_var,
            values=[str(value) for value in self.ANALYSIS_DEPTHS],
            state="readonly", width=8, font=("Segoe UI", 8),
        )
        self.analysis_depth_combo.pack(side="right")
        self.analysis_depth_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._analysis_depth_changed(),
        )

        training_row = tk.Frame(card, bg="#0f1619")
        training_row.pack(fill="x", padx=10, pady=(0, 8))
        tk.Label(
            training_row, text="TREINO DA IA", bg="#0f1619", fg="#66757c",
            font=("Segoe UI Semibold", 7),
        ).pack(side="left")
        self.training_depth_combo = ttk.Combobox(
            training_row, textvariable=self.training_candles_var,
            values=[str(value) for value in self.TRAINING_DEPTHS],
            state="readonly", width=8, font=("Segoe UI", 8),
        )
        self.training_depth_combo.pack(side="right")
        self.training_depth_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._training_depth_changed(),
        )
        tk.Button(
            card, text="◈  TREINAR IA", command=self.train_ai,
            bd=0, relief="flat", bg="#195e78", fg="white",
            activebackground="#21789a", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=9,
        ).pack(fill="x", padx=10, pady=(0, 10))

    def _analysis_depth_changed(self) -> None:
        try:
            depth = int(self.analysis_candles_var.get())
        except ValueError:
            depth = 2000
        if depth not in self.ANALYSIS_DEPTHS:
            depth = 2000
            self.analysis_candles_var.set(str(depth))
        self.controller.settings.mt5_analysis_candles = depth
        self.controller.save_settings()
        self._refresh_ai_status()
        self.status_var.set(f"Profundidade da análise ao vivo: {depth} candles")
        if getattr(self, "_analysis_active", False):
            self.refresh_analysis()

    def _training_depth_changed(self) -> None:
        try:
            depth = int(self.training_candles_var.get())
        except ValueError:
            depth = 5000
        if depth not in self.TRAINING_DEPTHS:
            depth = 5000
        self.controller.settings.mt5_training_candles = depth
        self.controller.save_settings()
        self._refresh_ai_status()

    def _save_form(self) -> None:
        if hasattr(self, "analysis_candles_var"):
            try:
                analysis_depth = int(self.analysis_candles_var.get())
            except ValueError:
                analysis_depth = 2000
            if analysis_depth not in self.ANALYSIS_DEPTHS:
                analysis_depth = 2000
                self.analysis_candles_var.set(str(analysis_depth))
            self.controller.settings.mt5_analysis_candles = analysis_depth
        if hasattr(self, "training_candles_var"):
            try:
                training_depth = int(self.training_candles_var.get())
            except ValueError:
                training_depth = 5000
            if training_depth not in self.TRAINING_DEPTHS:
                training_depth = 5000
                self.training_candles_var.set(str(training_depth))
            self.controller.settings.mt5_training_candles = training_depth
        super()._save_form()

    def _refresh_ai_status(self) -> None:
        if not hasattr(self, "ai_status_var"):
            return
        try:
            state = self.controller.ai_training_state()
        except Exception:
            self.ai_status_var.set("IA • estado indisponível")
            return
        analysis = int(state.get("analysis_candles") or 0)
        requested = int(state.get("requested_candles") or 0)
        loaded = int(state.get("loaded_candles") or 0)
        if state.get("compatible"):
            report = state.get("report")
            model = getattr(report, "selected_model", "Modelo")
            samples = int(getattr(report, "samples", 0) or 0)
            self.ai_status_var.set(f"IA TREINADA • {model} • {samples} amostras")
        else:
            self.ai_status_var.set("IA PRECISA TREINAR PARA ESTA CONFIGURAÇÃO")
        self.ai_context_var.set(
            f"Análise ao vivo: {analysis} candles • treino: {requested} • "
            f"histórico carregado: {loaded} • gráfico visível: 200"
        )

    def _configuration_changed(self) -> None:
        super()._configuration_changed()
        self._refresh_ai_status()

    def _execution_profile_changed(self) -> None:
        super()._execution_profile_changed()
        self._refresh_ai_status()

    def train_ai(self) -> None:
        if not self.mt5_connected.get():
            self._connect_mt5()
            if not self.mt5_connected.get():
                return
        self._analysis_depth_changed_silent()
        self._training_depth_changed()
        depth = int(self.training_candles_var.get())
        analysis = int(self.analysis_candles_var.get())
        self.ai_status_var.set(
            f"IA TREINANDO • análise {analysis} • carregando até {depth} candles do MT5…"
        )
        super().train_ai()

    def _analysis_depth_changed_silent(self) -> None:
        try:
            depth = int(self.analysis_candles_var.get())
        except ValueError:
            depth = 2000
        if depth not in self.ANALYSIS_DEPTHS:
            depth = 2000
            self.analysis_candles_var.set(str(depth))
        self.controller.settings.mt5_analysis_candles = depth
        self.controller.save_settings()

    def _training_ready(self, report) -> None:
        super()._training_ready(report)
        self._refresh_ai_status()

    def render_snapshot(self, snapshot) -> None:
        super().render_snapshot(snapshot)
        self._refresh_ai_status()
        self._refresh_chart_positions()

    def _refresh_positions(self) -> None:
        super()._refresh_positions()
        self._refresh_chart_positions()

    def _refresh_chart_positions(self) -> None:
        if not hasattr(self, "chart") or not isinstance(self.chart, MT5TradeChart):
            return
        if not self.mt5_connected.get():
            self.chart.set_positions([])
            return
        symbol = self.symbol_var.get().strip()
        try:
            rows = self.mt5.positions(symbol=symbol) if symbol else self.mt5.positions()
        except Exception:
            return
        self.chart.set_positions(rows)

    def _position_sync_tick(self) -> None:
        self._position_job = None
        if not self.winfo_exists():
            return
        if self.mt5_connected.get():
            self._refresh_chart_positions()
        self._position_job = self.after(1200, self._position_sync_tick)

    def _chart_modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        if not self._ensure_order_permission():
            return False
        try:
            result = self.mt5.modify_position_protection(
                ticket, sl=sl, tp=tp, armed=True,
            )
            self.status_var.set(
                f"MT5: proteção da posição {ticket} atualizada • "
                f"SL {sl:g} • TP {tp:g}"
            )
            self._refresh_positions()
            return bool(result.ok)
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            messagebox.showerror(
                "Prime Trader • Ajustar SL/TP", str(exc), parent=self,
            )
            self._refresh_chart_positions()
            return False

    def _close(self) -> None:
        if self._position_job is not None:
            try:
                self.after_cancel(self._position_job)
            except Exception:
                pass
            self._position_job = None
        super()._close()
