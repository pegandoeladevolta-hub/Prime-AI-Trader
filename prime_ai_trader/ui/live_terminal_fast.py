from __future__ import annotations

from ..core.models import Direction, SignalState
from .live_terminal_layout import PrimeTraderLiveApp as LayoutPrimeTraderLiveApp
from .prime_terminal_ai import PrimeTraderApp as TerminalPrimeTraderApp


class PrimeTraderLiveApp(LayoutPrimeTraderLiveApp):
    """Terminal responsivo com confirmação intravela controlada no modo rápido.

    A estabilidade continua sendo medida pela mesma sequência de pré-leituras do
    terminal ao vivo. Somente depois dessa estabilidade o controller pode promover
    RÁPIDO + PRICE ACTION para CONFIRMADO sem esperar o fechamento obrigatório.
    """

    def render_snapshot(self, snapshot) -> None:
        # Esta chamada aplica uma única vez o filtro de estabilidade existente:
        # três leituras consecutivas na mesma direção + tempo mínimo estável.
        display_snapshot = self._stable_display_snapshot(snapshot)
        effective_snapshot = snapshot

        stable_forming = (
            snapshot.signal.state == SignalState.FORMING
            and snapshot.signal.direction != Direction.WAIT
            and display_snapshot.signal.state == SignalState.FORMING
            and display_snapshot.signal.direction == snapshot.signal.direction
        )
        if stable_forming:
            promoter = getattr(self.controller, "promote_intrabar_confirmation", None)
            if callable(promoter):
                promoted = promoter(snapshot)
                if promoted is not None:
                    effective_snapshot = promoted
                    display_snapshot = promoted
                    self.status_var.set(
                        f"SINAL RÁPIDO MT5 CONFIRMADO • {promoted.symbol} • "
                        f"{promoted.signal.direction.value} • score {promoted.signal.score}/100 • "
                        f"R:R {float(promoted.signal.technical_room_ratio or 0.0):.2f}"
                    )
                    self._refresh_recent_signals()

        # Chama diretamente o renderizador completo do terminal (IA, gráfico,
        # SL/TP e posições) e depois entrega o snapshot efetivo ao automático.
        # Assim o auto não continua enxergando o objeto FORMING original.
        TerminalPrimeTraderApp.render_snapshot(self, display_snapshot)
        self._maybe_execute_auto(effective_snapshot)


__all__ = ["PrimeTraderLiveApp"]
