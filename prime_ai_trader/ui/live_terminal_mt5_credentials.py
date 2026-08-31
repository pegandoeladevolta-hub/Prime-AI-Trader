from __future__ import annotations

from tkinter import messagebox

from ..app.mt5_credentials import MT5CredentialPurgeError, purge_saved_mt5_credentials
from .live_terminal_clear_profiles import PrimeTraderLiveApp as ClearProfilesPrimeTraderLiveApp


class PrimeTraderLiveApp(ClearProfilesPrimeTraderLiveApp):
    """MT5 da Clear por sessão ativa, sem formulário ou armazenamento de senha."""

    def __init__(self, controller) -> None:
        removed = False
        purge_error = ""
        try:
            removed = purge_saved_mt5_credentials()
        except (OSError, ValueError, MT5CredentialPurgeError) as exc:
            purge_error = str(exc)

        super().__init__(controller)

        if removed:
            self.status_var.set(
                "Credenciais MT5 antigas removidas • o login agora é feito somente no MetaTrader 5"
            )
        if purge_error:
            self.after(
                150,
                lambda: messagebox.showwarning(
                    "Prime Trader • Limpeza de credenciais",
                    f"{purge_error}\n\n"
                    "O Prime Trader não usará essas credenciais para conectar. "
                    "Faça o login somente dentro do MetaTrader 5.",
                    parent=self,
                ),
            )


__all__ = ["PrimeTraderLiveApp"]
