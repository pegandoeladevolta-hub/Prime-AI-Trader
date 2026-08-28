from __future__ import annotations

import tkinter as tk

from .live_terminal import PrimeTraderLiveApp as BasePrimeTraderLiveApp


class PrimeTraderLiveApp(BasePrimeTraderLiveApp):
    """Ajuste visual do painel MT5 para resoluções verticais menores.

    A lógica de análise, IA e execução permanece na classe base. Esta camada só
    fixa os controles de posições na parte inferior do painel direito, impedindo
    que ENCERRAR POSIÇÃO e ATUALIZAR POSIÇÕES fiquem escondidos atrás do rodapé.
    """

    def _build_mt5_order_panel(self, parent) -> None:
        super()._build_mt5_order_panel(parent)
        panel = next(
            (
                child for child in parent.winfo_children()
                if isinstance(child, tk.Frame)
                and int(child.cget("width") or 0) >= 280
            ),
            None,
        )
        if panel is None:
            return
        self._pin_position_controls(panel)

    def _pin_position_controls(self, panel: tk.Frame) -> None:
        position_label = None
        close_button = None
        refresh_button = None
        information_label = None

        for child in panel.winfo_children():
            try:
                text = str(child.cget("text") or "")
            except tk.TclError:
                text = ""
            if text == "POSIÇÕES ABERTAS":
                position_label = child
            elif text == "ENCERRAR POSIÇÃO":
                close_button = child
            elif text == "ATUALIZAR POSIÇÕES":
                refresh_button = child
            elif text.startswith("Preço, candles, ativo e ordens usam"):
                information_label = child

        combo = getattr(self, "position_combo", None)
        required = (position_label, combo, close_button, refresh_button)
        if any(widget is None for widget in required):
            return

        # O texto informativo inferior ocupava altura útil e empurrava os botões
        # para baixo do rodapé em janelas como 1264x950.
        if information_label is not None:
            information_label.pack_forget()

        # Remove somente o gerenciamento geométrico antigo. Os widgets e seus
        # comandos continuam exatamente os mesmos.
        for widget in required:
            widget.pack_forget()

        fixed_height = 86
        backdrop = tk.Frame(
            panel,
            bg="#0b0f12",
            highlightbackground="#243137",
            highlightthickness=1,
        )
        backdrop.place(
            relx=0.0, rely=1.0, x=0, y=0,
            anchor="sw", relwidth=1.0, height=fixed_height,
        )
        backdrop.lift()
        self._mt5_positions_backdrop = backdrop

        position_label.place(x=16, rely=1.0, y=-69, anchor="sw")
        combo.place(x=16, rely=1.0, y=-43, anchor="sw", width=260, height=24)

        # Os dois botões ficam lado a lado para consumir menos altura vertical e
        # permanecerem sempre acima do footer do Prime Trader.
        close_button.configure(pady=2, font=("Segoe UI Semibold", 8))
        refresh_button.configure(pady=2, font=("Segoe UI", 8))
        close_button.place(
            x=16, rely=1.0, y=-8, anchor="sw", width=127, height=28,
        )
        refresh_button.place(
            x=149, rely=1.0, y=-8, anchor="sw", width=127, height=28,
        )

        for widget in required:
            widget.lift()


__all__ = ["PrimeTraderLiveApp"]
