from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from ..app.mt5_daily_limits import evaluate_daily_limits
from ..database.mt5_journal import MT5TradeJournal
from ..strategies.context import strategy_key
from .live_terminal_fast import PrimeTraderLiveApp as GuardedPrimeTraderLiveApp
from .mt5_journal_dialogs import MT5PerformanceDialog, MT5TradeHistoryDialog


class PrimeTraderLiveApp(GuardedPrimeTraderLiveApp):
    """Runtime final: uma posição por vez + diário MT5 + limite financeiro diário."""

    JOURNAL_SYNC_MS = 900

    def __init__(self, controller) -> None:
        self.mt5_journal = MT5TradeJournal()
        self._journal_job = None
        self._last_daily_limit_state: tuple[bool, str] | None = None
        self._account_currency_cache = "USD"
        super().__init__(controller)
        self._build_daily_limits_card()
        self._refresh_daily_limit_view()
        self._journal_job = self.after(self.JOURNAL_SYNC_MS, self._journal_tick)

    def _build_variables(self) -> None:
        super()._build_variables()
        settings = self.controller.settings
        self.daily_profit_target_var = tk.StringVar(
            master=self, value=f"{float(settings.mt5_daily_profit_target or 0):g}"
        )
        self.daily_stop_loss_var = tk.StringVar(
            master=self, value=f"{float(settings.mt5_daily_stop_loss or 0):g}"
        )
        self.consecutive_loss_limit_var = tk.StringVar(
            master=self, value=str(int(settings.mt5_max_consecutive_losses or 0))
        )
        self.daily_result_var = tk.StringVar(master=self, value="Resultado de hoje: —")
        path = str(settings.mt5_terminal_path or "").strip()
        self.mt5_terminal_display_var = tk.StringVar(
            master=self, value=path or "AUTO • procurando terminal da corretora"
        )

    def _build_daily_limits_card(self) -> None:
        parent = getattr(self, "_mt5_sidebar_body", None)
        if parent is None:
            return
        card = tk.Frame(
            parent,
            bg="#0f1619",
            highlightbackground="#243137",
            highlightthickness=1,
        )
        card.pack(fill="x", padx=14, pady=(0, 14))
        self._daily_limits_card = card

        tk.Label(
            card,
            text="LIMITES DO DIA • MT5",
            bg="#0f1619",
            fg="#e8eef1",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=11, pady=(10, 3))
        self.daily_result_label = tk.Label(
            card,
            textvariable=self.daily_result_var,
            bg="#0f1619",
            fg="#14d8a7",
            font=("Segoe UI Semibold", 8),
            wraplength=252,
            justify="left",
        )
        self.daily_result_label.pack(anchor="w", padx=11, pady=(0, 8))

        row = tk.Frame(card, bg="#0f1619")
        row.pack(fill="x", padx=11)
        left = tk.Frame(row, bg="#0f1619")
        left.pack(side="left", fill="x", expand=True, padx=(0, 4))
        right = tk.Frame(row, bg="#0f1619")
        right.pack(side="left", fill="x", expand=True, padx=(4, 0))
        tk.Label(
            left, text="META DIÁRIA", bg="#0f1619", fg="#7b898f",
            font=("Segoe UI Semibold", 7),
        ).pack(anchor="w")
        tk.Entry(
            left, textvariable=self.daily_profit_target_var,
            bg="#11171a", fg="#eef2f4", insertbackground="white",
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#202a2f", font=("Segoe UI", 9),
        ).pack(fill="x", ipady=5, pady=(2, 0))
        tk.Label(
            right, text="STOP DIÁRIO", bg="#0f1619", fg="#7b898f",
            font=("Segoe UI Semibold", 7),
        ).pack(anchor="w")
        tk.Entry(
            right, textvariable=self.daily_stop_loss_var,
            bg="#11171a", fg="#eef2f4", insertbackground="white",
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#202a2f", font=("Segoe UI", 9),
        ).pack(fill="x", ipady=5, pady=(2, 0))

        tk.Label(
            card, text="PARAR APÓS LOSSES SEGUIDOS", bg="#0f1619", fg="#7b898f",
            font=("Segoe UI Semibold", 7),
        ).pack(anchor="w", padx=11, pady=(7, 0))
        tk.Entry(
            card, textvariable=self.consecutive_loss_limit_var,
            bg="#11171a", fg="#eef2f4", insertbackground="white",
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#202a2f", font=("Segoe UI", 9),
        ).pack(fill="x", padx=11, ipady=5, pady=(2, 0))

        tk.Label(
            card,
            text="0 = desativado • o padrão é parar após 2 losses seguidos • usa apenas resultados realizados do dia",
            bg="#0f1619", fg="#66757c", font=("Segoe UI", 7),
            wraplength=252, justify="left",
        ).pack(anchor="w", padx=11, pady=(5, 7))
        tk.Button(
            card,
            text="SALVAR LIMITES DO DIA",
            command=self._daily_limits_changed,
            bd=0, relief="flat", bg="#195e78", fg="white",
            activebackground="#21789a", activeforeground="white",
            font=("Segoe UI Semibold", 8), pady=8,
        ).pack(fill="x", padx=11, pady=(0, 10))

        separator = tk.Frame(card, bg="#243137", height=1)
        separator.pack(fill="x", padx=11, pady=(0, 8))
        tk.Label(
            card,
            text="TERMINAL MT5",
            bg="#0f1619", fg="#7b898f", font=("Segoe UI Semibold", 7),
        ).pack(anchor="w", padx=11)
        tk.Label(
            card,
            textvariable=self.mt5_terminal_display_var,
            bg="#0f1619", fg="#9ca9ae", font=("Segoe UI", 7),
            wraplength=252, justify="left",
        ).pack(anchor="w", padx=11, pady=(3, 6))
        tk.Button(
            card,
            text="SELECIONAR TERMINAL MT5",
            command=self._select_mt5_terminal,
            bd=0, relief="flat", bg="#161f23", fg="#dce3e6",
            activebackground="#222e33", activeforeground="white",
            font=("Segoe UI Semibold", 8), pady=7,
        ).pack(fill="x", padx=11, pady=(0, 10))

    def _journal_context(self) -> dict[str, str]:
        settings = self.controller.settings
        return {
            "timeframe": str(settings.timeframe),
            "strategy": str(strategy_key(settings.market)),
            "sensitivity": str(settings.sensitivity),
            "mode": str(settings.mode),
            "management": str(self.controller.management_mode()),
        }

    def _sync_journal(self) -> None:
        if not self.mt5_connected.get():
            return
        try:
            self.mt5_journal.sync_with_mt5(self.mt5, **self._journal_context())
        except Exception as exc:
            self.controller.logger.debug("Diário MT5 aguardando sincronização: %s", exc)

    def _journal_tick(self) -> None:
        self._journal_job = None
        try:
            self._sync_journal()
            self._refresh_daily_limit_view()
        finally:
            if self.winfo_exists():
                self._journal_job = self.after(self.JOURNAL_SYNC_MS, self._journal_tick)

    def _daily_status(self):
        settings = self.controller.settings
        return evaluate_daily_limits(
            self.mt5_journal,
            profit_target=float(settings.mt5_daily_profit_target or 0.0),
            stop_loss=float(settings.mt5_daily_stop_loss or 0.0),
            max_consecutive_losses=int(settings.mt5_max_consecutive_losses or 0),
        )

    def _refresh_daily_limit_view(self):
        status = self._daily_status()
        currency = self._currency()
        target = (
            f"{currency} {status.profit_target:,.2f}"
            if status.profit_target > 0 else "DESATIVADA"
        )
        stop = (
            f"{currency} {status.stop_loss:,.2f}"
            if status.stop_loss > 0 else "DESATIVADO"
        )
        streak_limit = (
            str(status.consecutive_loss_limit)
            if status.consecutive_loss_limit > 0 else "DESATIVADO"
        )
        self.daily_result_var.set(
            f"HOJE: {currency} {status.net_profit:+,.2f} • {status.operations} encerrada(s)\n"
            f"META: {target} • STOP: {stop}\n"
            f"LOSSES SEGUIDOS: {status.consecutive_losses}/{streak_limit}"
        )
        if hasattr(self, "daily_result_label"):
            self.daily_result_label.configure(fg="#e14b3f" if status.blocked else "#14d8a7")

        state = (status.blocked, status.reason)
        previous = self._last_daily_limit_state
        self._last_daily_limit_state = state
        if status.blocked and state != previous:
            self.status_var.set(
                f"NOVAS ORDENS BLOQUEADAS • {status.reason} • ajuste os limites para liberar"
            )
        elif previous and previous[0] and not status.blocked:
            self.status_var.set(
                "LIMITES DO DIA ALTERADOS • trava financeira liberada • aguardando nova oportunidade"
            )
        return status

    def _daily_entry_allowed(self, *, force_sync: bool = False,
                             show_dialog: bool = False) -> bool:
        if force_sync:
            self._sync_journal()
        status = self._refresh_daily_limit_view()
        if not status.blocked:
            return True
        message = (
            f"{status.reason}\n\nNenhuma nova ordem será enviada pelo Prime Trader hoje. "
            "Para continuar, altere manualmente os limites do dia."
        )
        self.status_var.set(f"SESSÃO PARADA • {status.reason}")
        if show_dialog:
            messagebox.showwarning("Prime Trader • Limite diário", message, parent=self)
        return False

    def _daily_limits_changed(self) -> None:
        try:
            target = float(self.daily_profit_target_var.get().replace(",", ".") or 0)
            stop = float(self.daily_stop_loss_var.get().replace(",", ".") or 0)
            streak_limit = int(self.consecutive_loss_limit_var.get().strip() or 0)
            if target < 0 or stop < 0 or not 0 <= streak_limit <= 20:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Limites do dia",
                "Informe valores maiores ou iguais a zero. Losses seguidos deve ficar entre 0 e 20. Use 0 para desativar.",
                parent=self,
            )
            return
        settings = self.controller.settings
        settings.mt5_daily_profit_target = target
        settings.mt5_daily_stop_loss = stop
        settings.mt5_max_consecutive_losses = streak_limit
        self.controller.save_settings()
        self.daily_profit_target_var.set(f"{target:g}")
        self.daily_stop_loss_var.set(f"{stop:g}")
        self.consecutive_loss_limit_var.set(str(streak_limit))
        status = self._refresh_daily_limit_view()
        if status.blocked:
            self.status_var.set(
                f"LIMITES SALVOS • {status.reason} • novas ordens continuam bloqueadas"
            )
        else:
            self.status_var.set(
                "LIMITES DO DIA SALVOS • automático liberado dentro das novas travas"
            )

    def _select_mt5_terminal(self) -> None:
        destination = filedialog.askopenfilename(
            parent=self,
            title="Selecionar terminal MetaTrader 5 da corretora",
            filetypes=[("MetaTrader 5", "terminal64.exe terminal.exe"), ("Executável", "*.exe")],
        )
        if not destination:
            return
        path = Path(destination)
        if path.name.lower() not in {"terminal64.exe", "terminal.exe"}:
            accepted = messagebox.askyesno(
                "Selecionar MT5",
                "O arquivo escolhido não se chama terminal64.exe/terminal.exe. Usar mesmo assim?",
                parent=self,
            )
            if not accepted:
                return
        self.controller.settings.mt5_terminal_path = str(path)
        self.mt5.terminal_path = str(path)
        self.controller.save_settings()
        self.mt5_terminal_display_var.set(str(path))
        try:
            self.mt5.disconnect()
        except Exception:
            pass
        self.mt5_connected.set(False)
        self.status_var.set(f"Terminal MT5 selecionado • {path.parent.name}")
        self._connect_mt5()

    def _connect_mt5(self) -> None:
        super()._connect_mt5()
        if not self.mt5_connected.get():
            return
        try:
            account = self.mt5.account()
            self._account_currency_cache = str(account.currency or "USD")
        except Exception:
            pass
        resolved = str(getattr(self.mt5, "terminal_path", "") or "").strip()
        if resolved:
            self.mt5_terminal_display_var.set(resolved)
        self._sync_journal()
        self._refresh_daily_limit_view()

    def _release_for_fresh_opportunity(self) -> None:
        # No exato momento em que a posição desaparece, importa o deal de saída
        # antes de permitir que o automático considere uma nova oportunidade.
        self._sync_journal()
        self._refresh_daily_limit_view()
        return super()._release_for_fresh_opportunity()

    def _maybe_execute_auto(self, snapshot) -> None:
        if snapshot is not None and self._auto_enabled_and_armed():
            if not self._daily_entry_allowed():
                return
        return super()._maybe_execute_auto(snapshot)

    def _execute_confirmed_signal(self, snapshot) -> bool:
        # Segunda camada: mesmo se algum callback chamar a execução diretamente,
        # a ordem não passa depois que meta/stop diário foi atingido.
        if not self._daily_entry_allowed(force_sync=True):
            return False
        success = super()._execute_confirmed_signal(snapshot)
        if success:
            try:
                volume = float(self.mt5_volume.get().replace(",", "."))
                context = self._journal_context()
                self.mt5_journal.record_open(
                    snapshot,
                    volume=volume,
                    strategy=context["strategy"],
                    sensitivity=context["sensitivity"],
                    mode=context["mode"],
                    management=context["management"],
                )
                self._sync_journal()
            except Exception as exc:
                self.controller.logger.exception(
                    "Não foi possível registrar a operação no diário MT5: %s", exc
                )
        return success

    def _execute_signal_now(self) -> None:
        if not self._daily_entry_allowed(force_sync=True, show_dialog=True):
            return
        return super()._execute_signal_now()

    def _send_manual_order(self, side: str) -> None:
        if not self._daily_entry_allowed(force_sync=True, show_dialog=True):
            return
        return super()._send_manual_order(side)

    def _currency(self) -> str:
        if self.mt5_connected.get():
            try:
                self._account_currency_cache = str(self.mt5.account().currency or self._account_currency_cache)
            except Exception:
                pass
        return self._account_currency_cache or "USD"

    def open_performance(self):
        self._sync_journal()
        return MT5PerformanceDialog(
            self,
            self.mt5_journal.statistics(),
            currency=self._currency(),
        )

    def open_decision_history(self):
        self._sync_journal()
        return MT5TradeHistoryDialog(
            self,
            self.mt5_journal,
            self.mt5_journal.recent(2000),
            currency=self._currency(),
        )

    def _close(self) -> None:
        if self._journal_job is not None:
            try:
                self.after_cancel(self._journal_job)
            except Exception:
                pass
            self._journal_job = None
        self._sync_journal()
        super()._close()


__all__ = ["PrimeTraderLiveApp"]
