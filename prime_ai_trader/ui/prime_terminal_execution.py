from __future__ import annotations

from tkinter import messagebox

from ..platform.mt5 import MT5ExecutionError, MT5UnavailableError
from .prime_terminal import PrimeTraderApp as BasePrimeTraderApp


class PrimeTraderApp(BasePrimeTraderApp):
    """Ajustes da boleta manual sem alterar o motor visual/analítico."""

    def _build_mt5_order_panel(self, parent) -> None:
        super()._build_mt5_order_panel(parent)
        self._rename_manual_protection_labels(parent)

    def _rename_manual_protection_labels(self, widget) -> None:
        for child in widget.winfo_children():
            try:
                text = str(child.cget("text"))
                if text == "SL MANUAL (0 = sem)":
                    child.configure(text="SL EM PONTOS (0 = sem)")
                elif text == "TP MANUAL (0 = sem)":
                    child.configure(text="TP EM PONTOS (0 = sem)")
            except Exception:
                pass
            self._rename_manual_protection_labels(child)

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
            sl_points = float(self.mt5_sl.get().replace(",", ".") or 0)
            tp_points = float(self.mt5_tp.get().replace(",", ".") or 0)
            if not hasattr(self.mt5, "manual_protection_from_points"):
                raise MT5ExecutionError(
                    "A ponte MT5 instalada não suporta SL/TP em pontos. Reinstale esta versão do Prime Trader."
                )
            sl, tp = self.mt5.manual_protection_from_points(
                symbol, side, sl_points, tp_points,
            )
            kwargs = dict(
                symbol=symbol,
                volume=volume,
                sl=sl,
                tp=tp,
                deviation=self.controller.settings.mt5_deviation_points,
                armed=True,
            )
            result = self.mt5.buy(**kwargs) if side == "BUY" else self.mt5.sell(**kwargs)
            protection = []
            if sl_points > 0:
                protection.append(f"SL {sl_points:g} pts")
            if tp_points > 0:
                protection.append(f"TP {tp_points:g} pts")
            extra = " • " + " / ".join(protection) if protection else ""
            self.status_var.set(
                f"MT5: ordem {side} executada • {result.deal or result.order} • "
                f"{result.price}{extra}"
            )
            self._refresh_positions()
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            messagebox.showerror("Prime Trader • Ordem", str(exc), parent=self)
