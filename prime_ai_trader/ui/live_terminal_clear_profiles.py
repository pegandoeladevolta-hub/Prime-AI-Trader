from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from ..app.mt5_daily_limits import evaluate_daily_limits
from ..app.mt5_profiles import REAL, SIMULATOR, MT5ProfileStore, classify_account_environment
from ..core.models import Direction
from ..database.mt5_journal import MT5TradeJournal
from .live_terminal_mt5_journal import PrimeTraderLiveApp as JournalPrimeTraderLiveApp
from .prime_terminal import EXEC_AUTO, EXEC_COMMAND


class PrimeTraderLiveApp(JournalPrimeTraderLiveApp):
    """Runtime Clear: REAL/SIMULADOR separados + busca + valores do trade em dinheiro."""

    def __init__(self, controller) -> None:
        self.profile_store = MT5ProfileStore()
        self.profile_store.migrate_legacy_limits_once(controller.settings)
        environment = self.profile_store.environment
        path = self.profile_store.terminal_path(environment)
        configure = getattr(controller, "configure_mt5_profile", None)
        if callable(configure):
            configure(environment, path)
        super().__init__(controller)

        # A classe-base cria um diário genérico por compatibilidade; daqui em diante
        # REAL e SIMULADOR ficam fisicamente separados.
        self.mt5_journal = MT5TradeJournal(self.profile_store.journal_path(environment))
        self._build_clear_profile_card()
        self._build_trade_value_card()
        self._load_profile_into_view()
        self._enforce_real_manual_confirmation()
        self._refresh_daily_limit_view()
        try:
            self.mt5_volume.trace_add("write", lambda *_: self._refresh_trade_value())
        except Exception:
            pass

    def _build_variables(self) -> None:
        super()._build_variables()
        env = self.profile_store.environment
        self.mt5_environment_var = tk.StringVar(master=self, value=env)
        self.mt5_environment_status_var = tk.StringVar(
            master=self, value="AGUARDANDO CONEXÃO COM O MT5"
        )
        self.trade_value_summary_var = tk.StringVar(
            master=self, value="Aguardando sinal com Entrada + SL + TP para calcular valores."
        )

    def _build_clear_profile_card(self) -> None:
        parent = getattr(self, "_mt5_sidebar_body", None)
        if parent is None:
            return
        card = tk.Frame(parent, bg="#0f1619", highlightbackground="#243137", highlightthickness=1)
        card.pack(fill="x", padx=14, pady=(0, 14))
        self._clear_profile_card = card

        tk.Label(
            card, text="CLEAR • CONTA DETECTADA PELO MT5", bg="#0f1619", fg="#e8eef1",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=11, pady=(10, 3))
        tk.Label(
            card, textvariable=self.mt5_environment_status_var,
            bg="#0f1619", fg="#14d8a7", font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", padx=11, pady=(0, 7))

        buttons = tk.Frame(card, bg="#0f1619")
        buttons.pack(fill="x", padx=11, pady=(0, 7))
        tk.Button(
            buttons, text="CONECTAR AO MT5 ABERTO", command=self._connect_mt5,
            bd=0, relief="flat", bg="#176f63", fg="white",
            activebackground="#218b7c", activeforeground="white",
            font=("Segoe UI Semibold", 8), pady=8,
        ).pack(fill="x")

        tk.Button(
            card, text="🔎 PESQUISAR ATIVO", command=self._open_asset_search,
            bd=0, relief="flat", bg="#161f23", fg="#e0e6e9",
            activebackground="#222e33", activeforeground="white",
            font=("Segoe UI Semibold", 8), pady=7,
        ).pack(fill="x", padx=11, pady=(0, 7))

        tk.Label(
            card,
            text=(
                "Faça o login somente no MetaTrader 5. O Prime Trader lê a sessão aberta "
                "e identifica automaticamente se a conta é DEMO ou REAL."
            ),
            bg="#0f1619", fg="#66757c", font=("Segoe UI", 7),
            wraplength=252, justify="left",
        ).pack(anchor="w", padx=11, pady=(0, 10))

    def _build_trade_value_card(self) -> None:
        parent = getattr(self, "_mt5_sidebar_body", None)
        if parent is None:
            return
        card = tk.Frame(parent, bg="#0f1619", highlightbackground="#243137", highlightthickness=1)
        card.pack(fill="x", padx=14, pady=(0, 14))
        tk.Label(
            card, text="VALOR DA OPERAÇÃO • ESTIMATIVA MT5",
            bg="#0f1619", fg="#e8eef1", font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=11, pady=(10, 4))
        tk.Label(
            card, textvariable=self.trade_value_summary_var,
            bg="#0f1619", fg="#cbd4d8", font=("Segoe UI", 8),
            wraplength=252, justify="left",
        ).pack(anchor="w", padx=11, pady=(0, 6))
        tk.Label(
            card,
            text="O lote não equivale a um valor fixo em reais. O cálculo usa o ativo, preço, lote, SL/TP e a fórmula do terminal conectado.",
            bg="#0f1619", fg="#66757c", font=("Segoe UI", 7),
            wraplength=252, justify="left",
        ).pack(anchor="w", padx=11, pady=(0, 10))

    def _load_profile_into_view(self) -> None:
        env = self.profile_store.environment
        self.mt5_environment_var.set(env)
        if not self.mt5_connected.get():
            self.mt5_environment_status_var.set(f"ÚLTIMA CONTA: {env}")
        target, stop = self.profile_store.daily_limits(env)
        self.daily_profit_target_var.set(f"{target:g}")
        self.daily_stop_loss_var.set(f"{stop:g}")
        self.consecutive_loss_limit_var.set(
            str(self.profile_store.consecutive_loss_limit(env))
        )
        path = self.profile_store.terminal_path(env)
        self.mt5_terminal_display_var.set(path or "AUTO • procurando o MT5 da Clear")
        self._refresh_trade_value()

    def _daily_status(self):
        target, stop = self.profile_store.daily_limits()
        return evaluate_daily_limits(
            self.mt5_journal, profit_target=target, stop_loss=stop,
            max_consecutive_losses=self.profile_store.consecutive_loss_limit(),
        )

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
        self.profile_store.set_daily_limits(target, stop)
        self.profile_store.set_consecutive_loss_limit(streak_limit)
        # Mantém os campos antigos sincronizados apenas para compatibilidade visual.
        self.controller.settings.mt5_daily_profit_target = target
        self.controller.settings.mt5_daily_stop_loss = stop
        self.controller.settings.mt5_max_consecutive_losses = streak_limit
        self.controller.save_settings()
        self._refresh_daily_limit_view()
        self.status_var.set(
            f"LIMITES salvos para {self.profile_store.environment} • o outro ambiente não foi alterado"
        )

    def _enforce_real_manual_confirmation(self) -> None:
        if self.profile_store.environment != REAL:
            return
        if self.execution_profile_var.get() == EXEC_AUTO:
            self.execution_profile_var.set(EXEC_COMMAND)
            self.mt5_auto.set(False)
            self.mt5_armed.set(False)
            self._save_form()
            self._update_execution_controls()
            self.status_var.set(
                "CONTA REAL • confirmação manual obrigatória antes de cada ordem"
            )

    def _execution_profile_changed(self) -> None:
        if (
            self.profile_store.environment == REAL
            and self.execution_profile_var.get() == EXEC_AUTO
        ):
            self.execution_profile_var.set(EXEC_COMMAND)
            self.mt5_auto.set(False)
            self.mt5_armed.set(False)
            self._save_form()
            self._update_execution_controls()
            messagebox.showinfo(
                "Prime Trader • Conta Real",
                "Na conta REAL, cada ordem exige sua confirmação. O modo automático fica disponível somente na conta DEMO.",
                parent=self,
            )
            return
        return super()._execution_profile_changed()

    def _select_mt5_terminal(self) -> None:
        destination = filedialog.askopenfilename(
            parent=self,
            title="Selecionar o MetaTrader 5 da Clear",
            filetypes=[("MetaTrader 5", "terminal64.exe terminal.exe"), ("Executável", "*.exe")],
        )
        if not destination:
            return
        path = Path(destination)
        if path.name.lower() not in {"terminal64.exe", "terminal.exe"}:
            if not messagebox.askyesno(
                "Selecionar MT5", "O arquivo não se chama terminal64.exe/terminal.exe. Usar mesmo assim?", parent=self,
            ):
                return
        self.profile_store.set_terminal_path(str(path))
        configure = getattr(self.controller, "configure_mt5_profile", None)
        if callable(configure):
            configure(self.profile_store.environment, str(path))
        self.mt5_terminal_display_var.set(str(path))
        self.mt5_connected.set(False)
        self.status_var.set(f"MetaTrader 5 selecionado • {path.parent.name}")

    def _on_mt5_account_connected(self, account) -> None:
        """Adota a conta que o próprio MT5 informa antes de ler posições."""
        detected = classify_account_environment(account.server, account.name)
        previous = self.profile_store.environment
        if detected != previous:
            self.profile_store.set_environment(detected)
            self.mt5_journal = MT5TradeJournal(self.profile_store.journal_path(detected))
            self._load_profile_into_view()
        self.mt5_environment_var.set(detected)
        self.mt5.environment = detected
        self._enforce_real_manual_confirmation()

        resolved = str(getattr(self.mt5, "terminal_path", "") or "")
        if resolved:
            self.profile_store.set_terminal_path(resolved)
            self.mt5_terminal_display_var.set(resolved)

        account_kind = "DEMO" if detected == SIMULATOR else "REAL"
        self.mt5_environment_status_var.set(
            f"CONECTADO: CLEAR {account_kind} • conta {account.login}"
        )
        if detected != previous:
            self.status_var.set(
                f"Conta {account_kind} detectada automaticamente pelo servidor {account.server}"
            )

    def _format_mt5_account_text(self, account, crypto_note: str = "") -> str:
        detected = classify_account_environment(account.server, account.name)
        account_kind = "DEMO" if detected == SIMULATOR else "REAL"
        return f"CLEAR {account_kind} • conta {account.login}"

    def _connect_mt5(self) -> None:
        env = self.profile_store.environment
        path = self.profile_store.terminal_path()
        configure = getattr(self.controller, "configure_mt5_profile", None)
        if callable(configure):
            configure(env, path)
        super()._connect_mt5()
        if not self.mt5_connected.get():
            return
        try:
            account = self.mt5.account()
            detected = classify_account_environment(account.server, account.name)
            resolved = str(getattr(self.mt5, "terminal_path", "") or "")
            if resolved:
                self.profile_store.set_terminal_path(resolved)
                self.mt5_terminal_display_var.set(resolved)
            self.mt5_account_text.set(self._format_mt5_account_text(account))
            account_kind = "DEMO" if detected == SIMULATOR else "REAL"
            self.mt5_environment_status_var.set(
                f"CONECTADO: CLEAR {account_kind} • conta {account.login}"
            )
            self._refresh_trade_value()
        except Exception as exc:
            self.mt5_connected.set(False)
            messagebox.showerror("Prime Trader • Perfil MT5", str(exc), parent=self)

    def _open_asset_search(self) -> None:
        if not self.mt5_connected.get():
            self._connect_mt5()
            if not self.mt5_connected.get():
                return
        try:
            symbols = list(self.mt5.list_symbols())
        except Exception as exc:
            messagebox.showerror("Pesquisar ativo", str(exc), parent=self)
            return

        window = tk.Toplevel(self)
        window.title(f"Pesquisar ativo • {self.profile_store.environment}")
        window.geometry("470x520")
        window.configure(bg="#0b0f12")
        window.transient(self)
        query = tk.StringVar(master=window)
        tk.Label(
            window, text="Digite o código ou parte do nome do ativo",
            bg="#0b0f12", fg="#e8eef1", font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", padx=14, pady=(14, 5))
        entry = tk.Entry(
            window, textvariable=query, bg="#11171a", fg="white",
            insertbackground="white", relief="flat", font=("Segoe UI", 11),
        )
        entry.pack(fill="x", padx=14, ipady=7)
        listbox = tk.Listbox(
            window, bg="#0d1316", fg="#dbe2e5", selectbackground="#176f63",
            selectforeground="white", relief="flat", font=("Consolas", 10),
        )
        listbox.pack(fill="both", expand=True, padx=14, pady=10)

        def refresh(*_args) -> None:
            needle = query.get().strip().upper()
            filtered = [s for s in symbols if needle in s.upper()] if needle else symbols
            listbox.delete(0, tk.END)
            for symbol in filtered[:1500]:
                listbox.insert(tk.END, symbol)

        def choose(_event=None) -> None:
            selected = listbox.curselection()
            if not selected:
                return
            symbol = str(listbox.get(selected[0]))
            self.symbol_var.set(symbol)
            if hasattr(self.controller, "select_mt5_symbol"):
                self.controller.select_mt5_symbol(symbol)
            self._configuration_changed()
            window.destroy()

        query.trace_add("write", refresh)
        listbox.bind("<Double-Button-1>", choose)
        listbox.bind("<Return>", choose)
        tk.Button(
            window, text="USAR ATIVO SELECIONADO", command=choose,
            bd=0, relief="flat", bg="#176f63", fg="white",
            font=("Segoe UI Semibold", 9), pady=9,
        ).pack(fill="x", padx=14, pady=(0, 14))
        refresh()
        entry.focus_set()

    def _refresh_trade_value(self) -> None:
        if not hasattr(self, "trade_value_summary_var"):
            return
        snapshot = getattr(self.controller, "snapshot", None)
        if not self.mt5_connected.get() or snapshot is None:
            self.trade_value_summary_var.set("Aguardando MT5 conectado e um plano de trade válido.")
            return
        signal = snapshot.signal
        if signal.direction == Direction.WAIT or not signal.entry or not signal.technical_stop or not signal.technical_target:
            self.trade_value_summary_var.set("Sem Entrada + SL + TP válidos neste momento.")
            return
        try:
            volume = float(self.mt5_volume.get().replace(",", "."))
            side = "BUY" if signal.direction == Direction.BUY else "SELL"
            entry = float(signal.entry)
            stop = float(signal.technical_stop)
            target = float(signal.technical_target)
            at_stop = self.mt5.estimate_trade_profit(snapshot.symbol, side, volume, entry, stop)
            at_target = self.mt5.estimate_trade_profit(snapshot.symbol, side, volume, entry, target)
            currency = self._currency()
            risk = abs(float(at_stop or 0.0))
            gain = max(0.0, float(at_target or 0.0))
            rr = gain / risk if risk > 0 else float(signal.technical_room_ratio or 0.0)
            self.trade_value_summary_var.set(
                f"LOTE: {volume:g}\nRISCO NO SL: ≈ {currency} {risk:,.2f}\n"
                f"GANHO NO TP: ≈ {currency} {gain:,.2f}\nR:R FINANCEIRO: 1 : {rr:.2f}"
            )
        except Exception as exc:
            self.trade_value_summary_var.set(f"Estimativa financeira indisponível: {exc}")

    def _journal_tick(self) -> None:
        super()._journal_tick()
        self._refresh_trade_value()
        depth = getattr(self.controller, "analysis_depth_status", None)
        if callable(depth):
            status = depth()
            if status.get("reduced") and not self._last_daily_limit_state[0] if self._last_daily_limit_state else status.get("reduced"):
                message = str(status.get("message") or "")
                if message:
                    self.status_var.set(message)


__all__ = ["PrimeTraderLiveApp"]
