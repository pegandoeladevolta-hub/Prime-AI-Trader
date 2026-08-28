from __future__ import annotations

from tkinter import messagebox

from .live_terminal_layout import PrimeTraderLiveApp as LayoutPrimeTraderLiveApp
from .prime_terminal import EXEC_AUTO


class PrimeTraderLiveApp(LayoutPrimeTraderLiveApp):
    """Terminal MT5 com confirmação rápida no controller e auto sem estado oculto.

    O seletor EXECUÇÃO do topo é a fonte de verdade para habilitar o automático.
    A autorização ARMAR ORDENS REAIS continua separada e explícita: sem ela nenhuma
    ordem é enviada, mas desarmar não altera silenciosamente o seletor AUTOMÁTICO.
    """

    def _build_variables(self) -> None:
        super()._build_variables()
        automatic = self.execution_profile_var.get() == EXEC_AUTO
        self.mt5_auto.set(automatic)
        # Por segurança a autorização real continua sendo uma ação da sessão atual.
        # O usuário vê claramente o checkbox desarmado após abrir o programa.
        self.mt5_armed.set(False)

    def _save_form(self) -> None:
        # Não permite que uma BooleanVar antiga fique divergente do seletor visível.
        if hasattr(self, "execution_profile_var") and hasattr(self, "mt5_auto"):
            self.mt5_auto.set(self.execution_profile_var.get() == EXEC_AUTO)
        super()._save_form()
        if hasattr(self, "execution_profile_var"):
            automatic = self.execution_profile_var.get() == EXEC_AUTO
            changed = self.controller.settings.mt5_auto_execute_signals != automatic
            self.controller.settings.mt5_auto_execute_signals = automatic
            if changed:
                self.controller.save_settings()

    def _arm_changed(self) -> None:
        """Armar/desarmar não troca o modo escolhido no topo."""
        if self.mt5_armed.get():
            accepted = messagebox.askyesno(
                "Armar execução real",
                "As próximas ordens confirmadas pelo Prime Trader poderão ser "
                "enviadas ao MT5. Continuar?",
                parent=self,
            )
            if not accepted:
                self.mt5_armed.set(False)
        self.mt5_auto.set(self.execution_profile_var.get() == EXEC_AUTO)
        self._save_form()
        self._update_execution_controls()
        if self.execution_profile_var.get() == EXEC_AUTO:
            if self.mt5_armed.get():
                self.status_var.set(
                    "AUTOMÁTICO MT5 ATIVO • aguardando SINAL CONFIRMADO com SL/TP válido"
                )
            else:
                self.status_var.set(
                    "AUTOMÁTICO selecionado • marque ARMAR ORDENS REAIS para permitir execução"
                )


__all__ = ["PrimeTraderLiveApp"]
