from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from ..app.mt5_credentials import MT5CredentialStore
from ..app.mt5_profiles import REAL, SIMULATOR
from .live_terminal_clear_profiles import PrimeTraderLiveApp as ClearProfilesPrimeTraderLiveApp


class PrimeTraderLiveApp(ClearProfilesPrimeTraderLiveApp):
    """Clear REAL/SIMULADOR com credenciais criptografadas e login automático."""

    def __init__(self, controller) -> None:
        # Precisa existir antes do super: uma auto-conexão da classe base já pode
        # passar pelo nosso _connect_mt5 durante a montagem da interface.
        self.mt5_credential_store = MT5CredentialStore()
        self._credentials_window = None
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
            self._refresh_autologin_status()
            return

        self._apply_active_credentials()
        self._refresh_autologin_status()
        credentials = self.mt5_credential_store.get(after)
        if credentials.configured:
            self.status_var.set(f"Perfil {after} selecionado • login automático em andamento")
            self.after(120, self._auto_login_active_profile)
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
        window.geometry("520x690")
        window.minsize(500, 640)
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

        def parse_and_save(environment: str, values) -> None:
            login_var, server_var, password_var = values
            login_text = login_var.get().strip()
            server = server_var.get().strip()
            password = password_var.get()
            if not login_text and not password and not server:
                self.mt5_credential_store.clear(environment)
                return
            try:
                login = int(login_text)
            except ValueError as exc:
                raise ValueError(f"{environment}: o LOGIN deve conter somente números.") from exc
            self.mt5_credential_store.save(
                environment, login=login, password=password, server=server,
            )

        def save_all() -> None:
            try:
                parse_and_save(REAL, real_vars)
                parse_and_save(SIMULATOR, simulator_vars)
            except ValueError as exc:
                messagebox.showerror("Contas MT5", str(exc), parent=window)
                return
            self._apply_active_credentials()
            self._refresh_autologin_status()
            self.status_var.set("CONTAS MT5 SALVAS • credenciais protegidas • login automático ativo")
            window.destroy()
            self._credentials_window = None
            credentials = self.mt5_credential_store.get(self.profile_store.environment)
            if credentials.configured:
                try:
                    self.mt5.disconnect()
                except Exception:
                    pass
                self.mt5_connected.set(False)
                self.after(120, self._auto_login_active_profile)

        buttons = tk.Frame(window, bg="#0b0f12")
        buttons.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(
            buttons, text="SALVAR AS DUAS CONTAS", command=save_all,
            bd=0, relief="flat", bg="#176f63", fg="white",
            activebackground="#218b7c", activeforeground="white",
            font=("Segoe UI Semibold", 9), pady=10,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(
            buttons, text="CANCELAR", command=window.destroy,
            bd=0, relief="flat", bg="#1b2428", fg="#d8e0e3",
            activebackground="#28343a", activeforeground="white",
            font=("Segoe UI", 9), pady=10,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        def on_close() -> None:
            self._credentials_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)


__all__ = ["PrimeTraderLiveApp"]
