from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .live_terminal import PrimeTraderLiveApp as BasePrimeTraderLiveApp


class PrimeTraderLiveApp(BasePrimeTraderLiveApp):
    """Painel MT5 responsivo sem comprimir os controles.

    A área de IA + operação mantém o espaçamento original e ganha rolagem vertical
    quando a janela é baixa. O bloco de posições fica separado e sempre visível na
    base da lateral. Nenhuma regra de análise, IA, SL/TP ou execução é alterada.
    """

    SIDEBAR_WIDTH = 304
    POSITIONS_DOCK_HEIGHT = 146

    def _build_mt5_order_panel(self, parent) -> None:
        panel = tk.Frame(
            parent,
            bg="#0b0f12",
            width=self.SIDEBAR_WIDTH,
            highlightbackground="#1b2328",
            highlightthickness=1,
        )
        panel.grid(row=0, column=2, sticky="nse")
        panel.grid_propagate(False)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=0)
        panel.grid_columnconfigure(0, weight=1)

        # Conteúdo principal: nunca é espremido. Quando faltar altura, aparece
        # rolagem somente nesta área da lateral.
        scroll_host = tk.Frame(panel, bg="#0b0f12")
        scroll_host.grid(row=0, column=0, sticky="nsew")
        scroll_host.grid_rowconfigure(0, weight=1)
        scroll_host.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            scroll_host,
            bg="#0b0f12",
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
        )
        scrollbar = ttk.Scrollbar(
            scroll_host,
            orient="vertical",
            command=canvas.yview,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        body = tk.Frame(canvas, bg="#0b0f12")
        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_body_width(event) -> None:
            canvas.itemconfigure(body_window, width=max(1, event.width))

        body.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", sync_body_width)

        self._mt5_sidebar_canvas = canvas
        self._mt5_sidebar_body = body

        self._build_ai_management_card(body)
        self._build_operation_controls(body)
        self._build_positions_dock(panel)
        self._bind_sidebar_mousewheel(panel, canvas)

    def _build_ai_management_card(self, parent: tk.Frame) -> None:
        card = tk.Frame(
            parent,
            bg="#0f1619",
            highlightbackground="#243137",
            highlightthickness=1,
        )
        card.pack(fill="x", padx=14, pady=(10, 12))

        tk.Label(
            card,
            text="IA • GESTÃO DE TRADE • PROFUNDIDADE",
            bg="#0f1619",
            fg="#e8eef1",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=11, pady=(10, 2))
        tk.Label(
            card,
            textvariable=self.ai_status_var,
            bg="#0f1619",
            fg="#14d8a7",
            font=("Segoe UI Semibold", 8),
            wraplength=252,
            justify="left",
        ).pack(anchor="w", padx=11, pady=(0, 4))
        tk.Label(
            card,
            textvariable=self.ai_context_var,
            bg="#0f1619",
            fg="#76858c",
            font=("Segoe UI", 7),
            wraplength=252,
            justify="left",
        ).pack(anchor="w", padx=11, pady=(0, 9))

        management_row = tk.Frame(card, bg="#0f1619")
        management_row.pack(fill="x", padx=11, pady=(0, 7))
        tk.Label(
            management_row,
            text="GESTÃO",
            bg="#0f1619",
            fg="#66757c",
            font=("Segoe UI Semibold", 7),
        ).pack(side="left")
        self.management_combo = ttk.Combobox(
            management_row,
            textvariable=self.management_mode_var,
            values=list(self.MANAGEMENT_MODES),
            state="readonly",
            width=10,
            font=("Segoe UI", 8),
        )
        self.management_combo.pack(side="right")
        self.management_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._management_changed(),
        )

        rr_row = tk.Frame(card, bg="#0f1619")
        rr_row.pack(fill="x", padx=11, pady=(0, 7))
        tk.Label(
            rr_row,
            text="R:R MÍNIMO",
            bg="#0f1619",
            fg="#66757c",
            font=("Segoe UI Semibold", 7),
        ).pack(side="left")
        self.rr_combo = ttk.Combobox(
            rr_row,
            textvariable=self.minimum_rr_var,
            values=[f"{value:g}" for value in self.RR_VALUES],
            state="readonly",
            width=8,
            font=("Segoe UI", 8),
        )
        self.rr_combo.pack(side="right")
        self.rr_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._management_changed(),
        )

        analysis_row = tk.Frame(card, bg="#0f1619")
        analysis_row.pack(fill="x", padx=11, pady=(0, 7))
        tk.Label(
            analysis_row,
            text="ANÁLISE AO VIVO",
            bg="#0f1619",
            fg="#66757c",
            font=("Segoe UI Semibold", 7),
        ).pack(side="left")
        self.analysis_depth_combo = ttk.Combobox(
            analysis_row,
            textvariable=self.analysis_candles_var,
            values=[str(value) for value in self.ANALYSIS_DEPTHS],
            state="readonly",
            width=8,
            font=("Segoe UI", 8),
        )
        self.analysis_depth_combo.pack(side="right")
        self.analysis_depth_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._analysis_depth_changed(),
        )

        training_row = tk.Frame(card, bg="#0f1619")
        training_row.pack(fill="x", padx=11, pady=(0, 10))
        tk.Label(
            training_row,
            text="TREINO DA IA",
            bg="#0f1619",
            fg="#66757c",
            font=("Segoe UI Semibold", 7),
        ).pack(side="left")
        self.training_depth_combo = ttk.Combobox(
            training_row,
            textvariable=self.training_candles_var,
            values=[str(value) for value in self.TRAINING_DEPTHS],
            state="readonly",
            width=8,
            font=("Segoe UI", 8),
        )
        self.training_depth_combo.pack(side="right")
        self.training_depth_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._training_depth_changed(),
        )

        tk.Button(
            card,
            text="◈  TREINAR IA PARA SL/TP",
            command=self.train_ai,
            bd=0,
            relief="flat",
            bg="#195e78",
            fg="white",
            activebackground="#21789a",
            activeforeground="white",
            font=("Segoe UI Semibold", 9),
            pady=10,
        ).pack(fill="x", padx=11, pady=(0, 11))

    def _build_operation_controls(self, parent: tk.Frame) -> None:
        section = tk.Frame(parent, bg="#0b0f12")
        section.pack(fill="x", pady=(0, 14))

        tk.Label(
            section,
            text="OPERAÇÃO MT5",
            bg="#0b0f12",
            fg="#e8eef1",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", padx=16, pady=(4, 3))
        tk.Label(
            section,
            textvariable=self.current_signal_text,
            bg="#0b0f12",
            fg="#14d8a7",
            font=("Segoe UI Semibold", 8),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        self._order_field(section, "VOLUME", self.mt5_volume)
        self._order_field(section, "SL EM PONTOS (0 = sem)", self.mt5_sl)
        self._order_field(section, "TP EM PONTOS (0 = sem)", self.mt5_tp)

        tk.Checkbutton(
            section,
            text="ARMAR ORDENS REAIS",
            variable=self.mt5_armed,
            command=self._arm_changed,
            bg="#0b0f12",
            fg="#cbd4d8",
            selectcolor="#11171a",
            activebackground="#0b0f12",
            activeforeground="white",
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", padx=16, pady=(12, 7))

        self.execute_signal_button = tk.Button(
            section,
            text="✦  EXECUTAR SINAL ATUAL",
            command=self._execute_signal_now,
            bd=0,
            relief="flat",
            bg="#176f63",
            fg="white",
            activebackground="#218b7c",
            activeforeground="white",
            font=("Segoe UI Semibold", 10),
            pady=12,
        )
        self.execute_signal_button.pack(fill="x", padx=16, pady=(5, 10))

        manual = tk.Frame(section, bg="#0b0f12")
        manual.pack(fill="x", padx=16, pady=(0, 10))
        self.buy_button = tk.Button(
            manual,
            text="▲ COMPRAR",
            command=lambda: self._send_manual_order("BUY"),
            bd=0,
            relief="flat",
            bg="#08a66f",
            fg="white",
            activebackground="#0bc082",
            activeforeground="white",
            font=("Segoe UI Semibold", 10),
            pady=12,
        )
        self.buy_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.sell_button = tk.Button(
            manual,
            text="▼ VENDER",
            command=lambda: self._send_manual_order("SELL"),
            bd=0,
            relief="flat",
            bg="#e14b3f",
            fg="white",
            activebackground="#f05a4d",
            activeforeground="white",
            font=("Segoe UI Semibold", 10),
            pady=12,
        )
        self.sell_button.pack(side="left", fill="x", expand=True, padx=(4, 0))

        tk.Label(
            section,
            text="Preço, candles, ativo e ordens usam o mesmo terminal MT5 conectado.",
            bg="#0b0f12",
            fg="#66747a",
            font=("Segoe UI", 8),
            wraplength=258,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(5, 10))

    def _build_positions_dock(self, panel: tk.Frame) -> None:
        dock = tk.Frame(
            panel,
            bg="#0c1114",
            height=self.POSITIONS_DOCK_HEIGHT,
            highlightbackground="#243137",
            highlightthickness=1,
        )
        dock.grid(row=1, column=0, sticky="ew")
        dock.grid_propagate(False)
        self._mt5_positions_dock = dock

        tk.Label(
            dock,
            text="POSIÇÕES ABERTAS",
            bg="#0c1114",
            fg="#8b989e",
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", padx=16, pady=(10, 5))

        self.position_combo = ttk.Combobox(
            dock,
            textvariable=self.mt5_position,
            state="readonly",
        )
        self.position_combo.pack(fill="x", padx=16, pady=(0, 7))

        tk.Button(
            dock,
            text="ENCERRAR POSIÇÃO",
            command=self._close_position,
            bd=0,
            relief="flat",
            bg="#20282d",
            fg="#f0f3f4",
            activebackground="#2b363c",
            activeforeground="white",
            font=("Segoe UI Semibold", 9),
            pady=7,
        ).pack(fill="x", padx=16, pady=(0, 5))

        tk.Button(
            dock,
            text="ATUALIZAR POSIÇÕES",
            command=self._refresh_positions,
            bd=0,
            relief="flat",
            bg="#11171a",
            fg="#9aa6ab",
            activebackground="#1a2327",
            activeforeground="white",
            font=("Segoe UI", 8),
            pady=6,
        ).pack(fill="x", padx=16, pady=(0, 9))

    def _bind_sidebar_mousewheel(self, panel: tk.Frame, canvas: tk.Canvas) -> None:
        def on_wheel(event) -> str:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta:
                canvas.yview_scroll(-1 if delta > 0 else 1, "units")
            return "break"

        def bind_tree(widget) -> None:
            try:
                widget.bind("<MouseWheel>", on_wheel, add="+")
            except tk.TclError:
                return
            for child in widget.winfo_children():
                bind_tree(child)

        bind_tree(panel)


__all__ = ["PrimeTraderLiveApp"]
