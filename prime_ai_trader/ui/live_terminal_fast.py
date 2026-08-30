from __future__ import annotations

from datetime import datetime, timezone
import time
from tkinter import messagebox

from ..app.mt5_profiles import REAL
from ..app.mt5_position_guard import AutoPositionGuardStatus, PrimeAutoPositionGuard
from ..core.models import SignalState
from .live_terminal_layout import PrimeTraderLiveApp as LayoutPrimeTraderLiveApp
from .prime_terminal import EXEC_AUTO


class PrimeTraderLiveApp(LayoutPrimeTraderLiveApp):
    """Terminal MT5 com contexto contínuo e uma única operação automática ativa.

    O seletor EXECUÇÃO do topo é a fonte de verdade para habilitar o automático.
    A autorização ARMAR ENVIO DE ORDENS continua separada. Além disso, o automático
    nunca empilha posições: depois de uma ordem aceita, aguarda a posição Prime
    Trader desaparecer do MT5 antes de permitir uma nova oportunidade.
    """

    def __init__(self, controller) -> None:
        self._auto_position_guard = PrimeAutoPositionGuard(
            sync_grace_seconds=5.0,
            flat_confirmations=2,
        )
        self._auto_order_inflight = False
        self._auto_requires_signal_after: datetime | None = None
        super().__init__(controller)

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
                "Armar envio de ordens",
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
                    "AUTOMÁTICO MT5 ATIVO • uma operação por vez • aguardando oportunidade confirmada"
                )
            else:
                self.status_var.set(
                    "AUTOMÁTICO selecionado • marque ARMAR ENVIO DE ORDENS para permitir execução"
                )

    def _auto_enabled_and_armed(self) -> bool:
        profile_store = getattr(self, "profile_store", None)
        if profile_store is not None and profile_store.environment == REAL:
            return False
        return bool(
            self.execution_profile_var.get() == EXEC_AUTO
            and self.mt5_auto.get()
            and self.mt5_armed.get()
        )

    def _prime_position_status(self) -> tuple[AutoPositionGuardStatus, list[dict]]:
        """Reconcilia a trava local com as posições reais do MetaTrader 5."""
        if not self.mt5_connected.get():
            return (
                AutoPositionGuardStatus(
                    True,
                    "MT5 desconectado; não é seguro abrir outra operação sem verificar posições",
                ),
                [],
            )
        try:
            getter = getattr(self.mt5, "prime_positions", None)
            if getter is None:
                rows = self.mt5.positions()
                magic = int(getattr(self.mt5, "MAGIC", 260826))
                rows = [
                    row for row in rows
                    if int(row.get("magic", 0) or 0) == magic
                    or str(row.get("comment") or "").lower().startswith("prime trader")
                ]
            else:
                rows = list(getter())
            return self._auto_position_guard.evaluate(rows, connected=True), rows
        except Exception as exc:
            self.controller.logger.warning(
                "Não foi possível verificar posições Prime Trader antes da autoexecução: %s",
                exc,
            )
            return (
                AutoPositionGuardStatus(
                    True,
                    "não foi possível verificar as posições abertas no MT5; nova ordem bloqueada por segurança",
                ),
                [],
            )

    @staticmethod
    def _position_wait_text(rows: list[dict], reason: str) -> str:
        if not rows:
            return f"AUTO MT5 BLOQUEADO • {reason}"
        if len(rows) > 1:
            return (
                f"AUTO MT5 BLOQUEADO • {len(rows)} posições Prime Trader ainda abertas • "
                "nenhuma nova ordem até todas serem encerradas"
            )
        row = rows[0]
        symbol = str(row.get("symbol") or "ativo")
        ticket = row.get("ticket") or "—"
        sl = float(row.get("sl") or 0.0)
        tp = float(row.get("tp") or 0.0)
        protection = ""
        if sl or tp:
            protection = f" • SL {sl:g} • TP {tp:g}"
        return (
            f"OPERAÇÃO ATIVA • {symbol} #{ticket}{protection} • "
            "automático aguardando encerramento no TP/SL"
        )

    def _release_for_fresh_opportunity(self) -> None:
        """Depois do fechamento, descarta qualquer sinal antigo da operação anterior."""
        self._auto_requires_signal_after = datetime.now(timezone.utc)
        releaser = getattr(self.controller, "release_active_opportunity_for_reentry", None)
        if callable(releaser):
            releaser()
        self.status_var.set(
            "OPERAÇÃO ENCERRADA • aguardando uma NOVA confirmação de contexto antes da próxima ordem"
        )

    def _signal_is_fresh_after_flat(self, snapshot) -> bool:
        cutoff = self._auto_requires_signal_after
        if cutoff is None:
            return True
        # Um FORMING novo não deve liberar a proteção sozinho. Só uma confirmação
        # realmente nova, criada depois de ficarmos flat, pode abrir a próxima ordem.
        if snapshot.signal.state != SignalState.CONFIRMED:
            return False
        created = getattr(snapshot.signal, "created_at", None)
        if created is None:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        else:
            created = created.astimezone(timezone.utc)
        if created <= cutoff:
            return False
        self._auto_requires_signal_after = None
        return True

    def _maybe_execute_auto(self, snapshot) -> None:
        """Uma ordem automática só pode existir quando a conta está flat para o bot."""
        if snapshot is None or not self._auto_enabled_and_armed():
            return super()._maybe_execute_auto(snapshot)
        if self._auto_order_inflight:
            self.status_var.set(
                "AUTO MT5 • ordem anterior ainda está sendo enviada; nova ordem bloqueada"
            )
            return

        if not self.mt5_connected.get():
            self._connect_mt5()
            if not self.mt5_connected.get():
                self.status_var.set(
                    "AUTO MT5 BLOQUEADO • conecte o MT5 para verificar a operação ativa"
                )
                return

        guard_status, rows = self._prime_position_status()
        if guard_status.blocked:
            self.status_var.set(self._position_wait_text(rows, guard_status.reason))
            return
        if guard_status.released:
            self._release_for_fresh_opportunity()

        if not self._signal_is_fresh_after_flat(snapshot):
            self.status_var.set(
                "AUTO MT5 • operação anterior encerrada • aguardando uma NOVA confirmação antes de reentrar"
            )
            return

        return super()._maybe_execute_auto(snapshot)

    def _execute_confirmed_signal(self, snapshot) -> bool:
        """Marca a trava imediatamente quando o servidor aceita a ordem."""
        if self._auto_order_inflight:
            return False
        self._auto_order_inflight = True
        try:
            success = super()._execute_confirmed_signal(snapshot)
            if success:
                self._auto_position_guard.mark_order_accepted(now=time.monotonic())
                signal = snapshot.signal
                self.status_var.set(
                    f"AUTO MT5: {signal.direction.value} executada • OPERAÇÃO ATIVA • "
                    f"SL {float(signal.technical_stop or 0):g} • "
                    f"TP {float(signal.technical_target or 0):g} • "
                    "nenhuma nova ordem até esta posição encerrar"
                )
            return success
        finally:
            self._auto_order_inflight = False


__all__ = ["PrimeTraderLiveApp"]
