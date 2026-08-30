from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..app.mt5_daily_limits import evaluate_daily_limits
from ..app.mt5_profiles import ENVIRONMENTS, REAL, SIMULATOR, MT5ProfileStore, classify_account_environment
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
            master=self, value=f"PERFIL ATIVO: {env}"
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
            card, text="CLEAR • AMBIENTE MT5", bg="#0f1619", fg="#e8eef1",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=11, pady=(10, 3))
        tk.Label(
            card, textvariable=self.mt5_environment_status_var,
            bg="#0f1619", fg="#14d8a7", font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", padx=11, pady=(0, 7))

        combo = ttk.Combobox(
            card, textvariable=self.mt5_environment_var,
            values=list(ENVIRONMENTS), state="readonly", font=("Segoe UI", 9),
        )
        combo.pack(fill="x", padx=11, pady=(0, 7))
        combo.bind("<<ComboboxSelected>>", lambda _: self._environment_changed())
        self.mt5_environment_combo = combo

        account_buttons = tk.Frame(card, bg="#0f1619")
        account_buttons.pack(fill="x", padx=11, pady=(0, 7))
        self.mt5_real_account_button = tk.Button(
            account_buttons, text="CONTA REAL",
            command=lambda: self._select_environment(REAL),
            bd=0, relief="flat", fg="white", font=("Segoe UI Semibold", 8), pady=7,
        )
        self.mt5_real_account_button.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.mt5_demo_account_button = tk.Button(
            account_buttons, text="CONTA DEMO",
            command=lambda: self._select_environment(SIMULATOR),
            bd=0, relief="flat", fg="white", font=("Segoe UI Semibold", 8), pady=7,
        )
        self.mt5_demo_account_button.pack(side="left", fill="x", expand=True, padx=(3, 0))

        buttons = tk.Frame(card, bg="#0f1619")
        buttons.pack(fill="x", padx=11, pady=(0, 7))
        tk.Button(
            buttons, text="🔎 PESQUISAR ATIVO", command=self._open_asset_search,
            bd=0, relief="flat", bg="#161f23", fg="#e0e6e9",
            activebackground="#222e33", activeforeground="white",
            font=("Segoe UI Semibold", 8), pady=7,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(
            buttons, text="CONECTAR PERFIL", command=self._connect_mt5,
            bd=0, relief="flat", bg="#176f63", fg="white",
            activebackground="#218b7c", activeforeground="white",
            font=("Segoe UI Semibold", 8), pady=7,
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

        tk.Label(
            card,
            text="Escolha a conta antes de conectar. REAL e DEMO mantêm login, histórico e limites separados.",
            bg="#0f1619", fg="#66757c", font=("Segoe UI", 7),
            wraplength=252, justify="left",
        ).pack(anchor="w", padx=11, pady=(0, 10))

    def _refresh_environment_buttons(self) -> None:
        if not hasattr(self, "mt5_real_account_button"):
            return
        active = self.profile_store.environment
        for button, environment in (
            (self.mt5_real_account_button, REAL),
            (self.mt5_demo_account_button, SIMULATOR),
        ):
            selected = environment == active
            button.configure(
                bg="#176f63" if selected else "#24313a",
                activebackground="#218b7c" if selected else "#30424d",
            )

    def _select_environment(self, environment: str) -> None:
        if environment not in ENVIRONMENTS:
            return
        if environment == self.profile_store.environment:
            self._refresh_environment_buttons()
            return
        self.mt5_environment_var.set(environment)
        self._environment_changed()

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

    def _environment_changed(self) -> None:
        selected = self.mt5_environment_var.get()
        if selected not in ENVIRONMENTS:
            return
        old = self.profile_store.environment
        if selected == old:
            return

        if self.mt5_connected.get():
            try:
                rows = list(self.mt5.prime_positions())
            except Exception:
                rows = []
            if rows:
                self.mt5_environment_var.set(old)
                messagebox.showwarning(
                    "Trocar ambiente MT5",
                    "Existe uma operação do Prime Trader aberta no ambiente atual. Encerre-a no TP/SL ou manualmente antes de trocar entre REAL e SIMULADOR.",
                    parent=self,
                )
                return

        try:
            self._sync_journal()
        except Exception:
            pass
        try:
            self.mt5.disconnect()
        except Exception:
            pass
        self.mt5_connected.set(False)
        self.profile_store.set_environment(selected)
        self.mt5_journal = MT5TradeJournal(self.profile_store.journal_path(selected))
        path = self.profile_store.terminal_path(selected)
        configure = getattr(self.controller, "configure_mt5_profile", None)
        if callable(configure):
            configure(selected, path)
        self.mt5_account_text.set(f"{selected} • desconectado")
        self._load_profile_into_view()
        self._enforce_real_manual_confirmation()
        self.status_var.set(f"Perfil alterado para {selected} • conecte o MT5 correspondente")

    def _load_profile_into_view(self) -> None:
        env = self.profile_store.environment
        self.mt5_environment_var.set(env)
        self.mt5_environment_status_var.set(f"PERFIL ATIVO: {env}")
        target, stop = self.profile_store.daily_limits(env)
        self.daily_profit_target_var.set(f"{target:g}")
        self.daily_stop_loss_var.set(f"{stop:g}")
        self.consecutive_loss_limit_var.set(
            str(self.profile_store.consecutive_loss_limit(env))
        )
        path = self.profile_store.terminal_path(env)
        self.mt5_terminal_display_var.set(path or f"AUTO • procurando terminal do perfil {env}")
        self._refresh_environment_buttons()
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
        env = self.profile_store.environment
        destination = filedialog.askopenfilename(
            parent=self,
            title=f"Selecionar terminal MetaTrader 5 • {env}",
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
        self.profile_store.set_terminal_path(str(path), env)
        configure = getattr(self.controller, "configure_mt5_profile", None)
        if callable(configure):
            configure(env, str(path))
        self.mt5_terminal_display_var.set(str(path))
        self.mt5_connected.set(False)
        self.status_var.set(f"Terminal salvo para {env} • {path.parent.name}")

    def _connect_mt5(self) -> None:
        env = self.profile_store.environment
        path = self.profile_store.terminal_path(env)
        configure = getattr(self.controller, "configure_mt5_profile", None)
        if callable(configure):
            configure(env, path)
        super()._connect_mt5()
        if not self.mt5_connected.get():
            return
        try:
            account = self.mt5.account()
            detected = classify_account_environment(account.server, account.name)
            if detected != env:
                raise RuntimeError(f"Sessão {detected} conectada no perfil {env}")
            resolved = str(getattr(self.mt5, "terminal_path", "") or "")
            if resolved:
                self.profile_store.set_terminal_path(resolved, env)
                self.mt5_terminal_display_var.set(resolved)
            self.mt5_account_text.set(
                f"{env} • {account.server} • conta {account.login} • {account.currency}"
            )
            self.mt5_environment_status_var.set(
                f"CONECTADO: {env} • {account.server}"
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
