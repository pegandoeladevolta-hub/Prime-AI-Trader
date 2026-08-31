from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from ..app.mt5_credentials import (
    MT5CredentialPersistenceError,
    MT5CredentialStore,
    parse_mt5_credentials,
)
from ..app.mt5_profiles import ENVIRONMENTS, REAL, SIMULATOR
from ..platform.mt5_dual import MT5ProfileMismatchError
from .live_terminal_clear_profiles import PrimeTraderLiveApp as ClearProfilesPrimeTraderLiveApp


class PrimeTraderLiveApp(ClearProfilesPrimeTraderLiveApp):
    """Clear REAL/SIMULADOR com credenciais criptografadas e login automático."""

    def __init__(self, controller) -> None:
        # Precisa existir antes do super: uma auto-conexão da classe base já pode
        # passar pelo nosso _connect_mt5 durante a montagem da interface.
        self.mt5_credential_store = MT5CredentialStore()
        self._credentials_window = None
        self._connect_active_session_once = False
        super().__init__(controller)
        self._install_credentials_controls()
        self._apply_active_credentials()
        self._refresh_autologin_status()

        # Se o perfil ativo já estiver completamente cadastrado, tenta conectar
        # sem exigir que o usuário abra manualmente a janela de login do MT5.
        if self.mt5_credential_store.get(self.profile_store.environment).configured:
            self.after(350, self._auto_login_active_profile)

    def _install_credentials_controls(self) -> None:
        card = getattr(self, "_clear_profile_card", None)
        if card is None:
            return
        self.mt5_autologin_status_var = tk.StringVar(master=self, value="LOGIN AUTOMÁTICO: —")
        tk.Label(
            card,
            textvariable=self.mt5_autologin_status_var,
            bg="#0f1619", fg="#8fa0a6", font=("Segoe UI Semibold", 7),
        ).pack(anchor="w", padx=11, pady=(0, 5))
        tk.Button(
            card,
            text="🔐 CONTAS / LOGIN AUTOMÁTICO",
            command=self._open_credentials_dialog,
            bd=0, relief="flat", bg="#24313a", fg="#eef3f5",
            activebackground="#30424d", activeforeground="white",
            font=("Segoe UI Semibold", 8), pady=8,
        ).pack(fill="x", padx=11, pady=(0, 10))

    def _refresh_autologin_status(self) -> None:
        if not hasattr(self, "mt5_autologin_status_var"):
            return
        env = self.profile_store.environment
        credentials = self.mt5_credential_store.get(env)
        if credentials.configured:
            self.mt5_autologin_status_var.set(
                f"LOGIN AUTOMÁTICO: CONFIGURADO • conta {credentials.login}"
            )
        else:
            self.mt5_autologin_status_var.set("LOGIN AUTOMÁTICO: NÃO CONFIGURADO")

    def _apply_active_credentials(self) -> None:
        env = self.profile_store.environment
        path = self.profile_store.terminal_path(env)
        credentials = self.mt5_credential_store.get(env)
        configure = getattr(self.controller, "configure_mt5_profile", None)
        if credentials.configured and callable(configure):
            configure(
                env,
                path,
                login=credentials.login,
                password=credentials.password,
                server=credentials.server,
            )
        else:
            # Impede que credenciais do ambiente anterior sobrevivam em memória
            # quando o novo perfil ainda não foi cadastrado.
            if callable(configure):
                configure(env, path)
            setter = getattr(self.mt5, "set_credentials", None)
            if callable(setter):
                setter(login=None, password="", server="")

    def _connect_mt5(self) -> None:
        self._apply_active_credentials()
        return super()._connect_mt5()

    def _handle_mt5_connection_error(self, error: Exception) -> bool:
        if not isinstance(error, MT5ProfileMismatchError):
            return False
        detected = error.detected_environment
        expected = error.expected_environment
        if detected not in ENVIRONMENTS or detected == expected:
            messagebox.showerror(
                "Prime Trader • Conta MT5",
                f"{error}\n\nAbra CONTAS / LOGIN AUTOMÁTICO e revise o cadastro de {expected}.",
                parent=self,
            )
            self.after(80, self._open_credentials_dialog)
            return True

        account = f" • conta {error.detected_login}" if error.detected_login else ""
        choice = messagebox.askyesnocancel(
            "Prime Trader • Escolher conta",
            f"O MT5 está conectado em {detected}{account}, mas o Prime Trader está em {expected}.\n\n"
            f"SIM: usar {detected} agora.\n"
            f"NÃO: manter {expected} e abrir o cadastro de login.\n"
            "CANCELAR: não conectar.",
            parent=self,
        )
        if choice is True:
            self._connect_active_session_once = True
            self.mt5_environment_var.set(detected)
            self._environment_changed()
        elif choice is False:
            self.after(80, self._open_credentials_dialog)
        else:
            self.status_var.set("CONEXÃO CANCELADA • escolha CONTA REAL ou CONTA DEMO")
        return True

    def _auto_login_active_profile(self) -> None:
        if not self.winfo_exists() or self.mt5_connected.get():
            return
        credentials = self.mt5_credential_store.get(self.profile_store.environment)
        if not credentials.configured:
            return
        self.status_var.set(
            f"LOGIN AUTOMÁTICO • conectando {self.profile_store.environment} • conta {credentials.login}"
        )
        self._connect_mt5()

    def _environment_changed(self) -> None:
        before = self.profile_store.environment
        selected = self.mt5_environment_var.get()
        super()._environment_changed()
        after = self.profile_store.environment

        # Se a classe-base recusou a troca por existir posição aberta, não tenta
        # desconectar nem autenticar outra conta.
        if after == before or after != selected:
            self._connect_active_session_once = False
            self._refresh_autologin_status()
            return

        self._apply_active_credentials()
        self._refresh_autologin_status()
        credentials = self.mt5_credential_store.get(after)
        if credentials.configured:
            self._connect_active_session_once = False
            self.status_var.set(f"Perfil {after} selecionado • login automático em andamento")
            self.after(120, self._auto_login_active_profile)
        elif self._connect_active_session_once:
            self._connect_active_session_once = False
            self.status_var.set(f"Perfil {after} selecionado • usando a sessão já aberta no MT5")
            self.after(120, self._connect_mt5)
        else:
            self.status_var.set(
                f"Perfil {after} selecionado • cadastre LOGIN/SENHA em CONTAS / LOGIN AUTOMÁTICO"
            )
            self.after(80, self._open_credentials_dialog)

    @staticmethod
    def _credential_section(parent, title: str, login_value: str,
                            server_value: str, password_value: str):
        frame = tk.Frame(
            parent, bg="#0f1619", highlightbackground="#27343a", highlightthickness=1,
        )
        frame.pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(
            frame, text=title, bg="#0f1619", fg="#e9eff1",
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", padx=12, pady=(10, 8))

        login_var = tk.StringVar(master=parent, value=login_value)
        server_var = tk.StringVar(master=parent, value=server_value)
        password_var = tk.StringVar(master=parent, value=password_value)

        def field(label: str, variable: tk.StringVar, *, secret: bool = False):
            tk.Label(
                frame, text=label, bg="#0f1619", fg="#819096",
                font=("Segoe UI Semibold", 8),
            ).pack(anchor="w", padx=12, pady=(2, 3))
            entry = tk.Entry(
                frame, textvariable=variable, show="●" if secret else "",
                bg="#11171a", fg="#f1f4f5", insertbackground="white",
                relief="flat", bd=0, highlightthickness=1,
                highlightbackground="#253137", font=("Segoe UI", 10),
            )
            entry.pack(fill="x", padx=12, ipady=6, pady=(0, 7))
            return entry

        field("LOGIN MT5", login_var)
        field("SERVIDOR", server_var)
        password_entry = field("SENHA MT5", password_var, secret=True)

        show_var = tk.BooleanVar(master=parent, value=False)
        tk.Checkbutton(
            frame, text="Mostrar senha", variable=show_var,
            command=lambda: password_entry.configure(show="" if show_var.get() else "●"),
            bg="#0f1619", fg="#849399", selectcolor="#11171a",
            activebackground="#0f1619", activeforeground="white",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=10, pady=(0, 9))
        return login_var, server_var, password_var

    def _open_credentials_dialog(self) -> None:
        if self._credentials_window is not None:
            try:
                if self._credentials_window.winfo_exists():
                    self._credentials_window.lift()
                    self._credentials_window.focus_force()
                    return
            except Exception:
                pass

        window = tk.Toplevel(self)
        self._credentials_window = window
        window.title("Prime Trader • Contas MT5 da Clear")
        window.geometry("560x760")
        window.minsize(540, 710)
        window.configure(bg="#0b0f12")
        window.transient(self)

        tk.Label(
            window,
            text="CONTAS MT5 • LOGIN AUTOMÁTICO",
            bg="#0b0f12", fg="#f0f4f5", font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", padx=14, pady=(14, 3))
        tk.Label(
            window,
            text=(
                "Cadastre uma vez. Ao escolher CLEAR REAL ou CLEAR SIMULADOR, o Prime Trader "
                "entra automaticamente na conta correspondente. As senhas ficam protegidas pelo Windows."
            ),
            bg="#0b0f12", fg="#7f8e94", font=("Segoe UI", 8),
            wraplength=480, justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 12))

        real = self.mt5_credential_store.get(REAL)
        simulator = self.mt5_credential_store.get(SIMULATOR)
        real_vars = self._credential_section(
            window, "CLEAR REAL",
            str(real.login or ""), real.server, real.password,
        )
        simulator_vars = self._credential_section(
            window, "CLEAR SIMULADOR / DEMO",
            str(simulator.login or ""), simulator.server, simulator.password,
        )

        tk.Label(
            window,
            text="Importante: use a senha específica do MetaTrader 5. Não use a senha do site/app da Clear se forem diferentes.",
            bg="#0b0f12", fg="#9aa7ac", font=("Segoe UI", 8),
            wraplength=480, justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 10))

        def parse_section(environment: str, values):
            login_var, server_var, password_var = values
            return parse_mt5_credentials(
                environment,
                login_text=login_var.get(),
                password=password_var.get(),
                server=server_var.get(),
            )

        def save_all(target_environment: str | None = None) -> None:
            try:
                profiles = {
                    REAL: parse_section(REAL, real_vars),
                    SIMULATOR: parse_section(SIMULATOR, simulator_vars),
                }
                if target_environment is not None and profiles[target_environment] is None:
                    raise ValueError(
                        f"Preencha LOGIN e SENHA de {target_environment} antes de conectar."
                    )
                self.mt5_credential_store.save_profiles(profiles)
            except (ValueError, OSError, MT5CredentialPersistenceError) as exc:
                messagebox.showerror(
                    "Contas MT5 • Não foi possível salvar",
                    f"{exc}\n\nNenhuma senha foi exibida. Revise os campos e tente novamente.",
                    parent=window,
                )
                return

            saved_accounts = [
                f"{environment} • conta {credentials.login}"
                for environment, credentials in profiles.items()
                if credentials is not None
            ]
            window.destroy()
            self._credentials_window = None
            self.status_var.set(
                "CONTAS MT5 SALVAS E VERIFICADAS • " + (" • ".join(saved_accounts) or "nenhuma conta cadastrada")
            )

            if target_environment is None:
                self._apply_active_credentials()
                self._refresh_autologin_status()
                messagebox.showinfo(
                    "Contas MT5",
                    "Cadastro salvo e relido com sucesso. Use CONTA DEMO ou CONTA REAL para conectar.",
                    parent=self,
                )
                return

            if target_environment != self.profile_store.environment:
                self.mt5_environment_var.set(target_environment)
                self._environment_changed()
                return

            self._apply_active_credentials()
            self._refresh_autologin_status()
            try:
                self.mt5.disconnect()
            except Exception:
                pass
            self.mt5_connected.set(False)
            self.after(120, self._auto_login_active_profile)

        buttons = tk.Frame(window, bg="#0b0f12")
        buttons.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(
            buttons, text="SALVAR E USAR DEMO", command=lambda: save_all(SIMULATOR),
            bd=0, relief="flat", bg="#176f63", fg="white",
            activebackground="#218b7c", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=10,
        ).pack(fill="x", pady=(0, 7))
        tk.Button(
            buttons, text="SALVAR E USAR REAL", command=lambda: save_all(REAL),
            bd=0, relief="flat", bg="#9a6b18", fg="white",
            activebackground="#b27c1d", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=10,
        ).pack(fill="x", pady=(0, 7))

        lower_buttons = tk.Frame(buttons, bg="#0b0f12")
        lower_buttons.pack(fill="x")
        tk.Button(
            lower_buttons, text="SÓ SALVAR", command=save_all,
            bd=0, relief="flat", bg="#24313a", fg="#e8eef1",
            activebackground="#30424d", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=9,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(
            lower_buttons, text="CANCELAR", command=lambda: on_close(),
            bd=0, relief="flat", bg="#1b2428", fg="#d8e0e3",
            activebackground="#28343a", activeforeground="white",
            font=("Segoe UI", 9), pady=10,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        def on_close() -> None:
            self._credentials_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)


__all__ = ["PrimeTraderLiveApp"]
