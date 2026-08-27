from __future__ import annotations

import tkinter as tk

from ..core.models import Direction, SignalState
from ..platform.mt5 import MT5ExecutionError, MT5UnavailableError
from .prime_terminal import PrimeTraderApp


class PrimeTraderLiveApp(PrimeTraderApp):
    """Acrescenta autoexecução opcional sem alterar o motor de sinais 1.2.6."""

    def __init__(self, controller) -> None:
        self._last_auto_signature = None
        self._auto_job = None
        super().__init__(controller)
        self._auto_job = self.after(350, self._auto_execution_tick)

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
            ("◎", "NOTÍCIAS", self._show_news),
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

    def _show_news(self) -> None:
        snapshot = self.controller.snapshot
        window = tk.Toplevel(self)
        window.title("Prime Trader • Notícias")
        window.geometry("720x520")
        window.configure(bg="#0b0f12")
        tk.Label(
            window, text="NOTÍCIAS RECENTES DO ATIVO", bg="#0b0f12",
            fg="#eef2f4", font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", padx=18, pady=(16, 8))
        text = tk.Text(
            window, bg="#0e1417", fg="#c8d2d6", insertbackground="white",
            relief="flat", wrap="word", font=("Segoe UI", 10), padx=12, pady=12,
        )
        text.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        if snapshot is None:
            text.insert("end", "Inicie uma análise para carregar as notícias relacionadas ao ativo atual.")
        elif not snapshot.news:
            text.insert("end", "Nenhuma notícia relevante foi retornada pelas fontes públicas nesta análise.")
        else:
            for item in snapshot.news[:15]:
                when = item.published_at.astimezone().strftime("%d/%m %H:%M")
                source = getattr(item, "source", "") or "Fonte pública"
                text.insert("end", f"{when}  •  {source}\n{item.title}\n\n")
        text.configure(state="disabled")

    def _auto_execution_tick(self) -> None:
        try:
            snapshot = self.controller.snapshot
            enabled = bool(self.mt5_auto.get()) and bool(self.mt5_armed.get())
            if enabled and snapshot is not None:
                signal = snapshot.signal
                if signal.state == SignalState.CONFIRMED and signal.direction != Direction.WAIT:
                    candle_key = snapshot.candles[-1].open_time if snapshot.candles else snapshot.generated_at
                    signature = (
                        snapshot.market, snapshot.symbol, snapshot.timeframe,
                        candle_key, signal.direction.value,
                    )
                    if signature != self._last_auto_signature:
                        self._last_auto_signature = signature
                        self._execute_confirmed_signal(snapshot)
        finally:
            if self.winfo_exists():
                self._auto_job = self.after(350, self._auto_execution_tick)

    def _execute_confirmed_signal(self, snapshot) -> None:
        try:
            if not self.mt5_connected.get():
                self._connect_mt5()
            if not self.mt5_connected.get():
                raise MT5UnavailableError("MT5 não conectado; sinal não foi executado.")
            signal = snapshot.signal
            symbol = self._mt5_symbol(snapshot.symbol)
            volume = float(self.mt5_volume.get().replace(",", "."))
            sl = float(signal.technical_stop or 0.0)
            tp = float(signal.technical_target or 0.0)
            kwargs = dict(
                symbol=symbol, volume=volume, sl=sl, tp=tp,
                deviation=self.controller.settings.mt5_deviation_points,
                armed=True,
            )
            if signal.direction == Direction.BUY:
                result = self.mt5.buy(**kwargs)
            elif signal.direction == Direction.SELL:
                result = self.mt5.sell(**kwargs)
            else:
                return
            self.status_var.set(
                f"AUTO MT5: {signal.direction.value} executada • "
                f"{result.deal or result.order} • {result.price}"
            )
            self._refresh_positions()
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            self.status_var.set(f"AUTO MT5 NÃO EXECUTOU: {exc}")

    def _close(self) -> None:
        if self._auto_job is not None:
            try:
                self.after_cancel(self._auto_job)
            except Exception:
                pass
            self._auto_job = None
        super()._close()
