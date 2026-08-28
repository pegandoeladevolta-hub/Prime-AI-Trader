from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(frozen=True, slots=True)
class AutoPositionGuardStatus:
    blocked: bool
    reason: str
    open_positions: int = 0
    released: bool = False


class PrimeAutoPositionGuard:
    """Impede que o automático empilhe posições simultâneas no MT5.

    A regra é global para as ordens abertas pelo Prime Trader: depois que uma ordem
    automática é aceita, nenhuma outra pode ser enviada enquanto existir uma
    posição Prime Trader aberta. A proteção continua funcionando após reiniciar o
    aplicativo porque o estado real é reconciliado com ``positions_get`` do MT5.

    Existe uma pequena janela de sincronização após ``order_send`` para cobrir o
    intervalo em que o servidor aceitou a ordem, mas ``positions_get`` ainda não a
    publicou. Depois que uma posição já foi observada, são exigidas duas leituras
    consecutivas sem posição antes de liberar uma nova entrada, evitando flicker.
    """

    def __init__(self, *, sync_grace_seconds: float = 5.0,
                 flat_confirmations: int = 2) -> None:
        self.sync_grace_seconds = max(0.0, float(sync_grace_seconds))
        self.flat_confirmations = max(1, int(flat_confirmations))
        self.locked = False
        self.position_seen = False
        self.lock_started = 0.0
        self.empty_checks = 0

    def mark_order_accepted(self, *, now: float | None = None) -> None:
        self.locked = True
        self.position_seen = False
        self.lock_started = time.monotonic() if now is None else float(now)
        self.empty_checks = 0

    def reset(self) -> None:
        self.locked = False
        self.position_seen = False
        self.lock_started = 0.0
        self.empty_checks = 0

    def evaluate(self, open_positions: list[dict] | tuple[dict, ...], *,
                 connected: bool = True,
                 now: float | None = None) -> AutoPositionGuardStatus:
        current = time.monotonic() if now is None else float(now)
        count = len(open_positions or ())

        if count:
            self.locked = True
            self.position_seen = True
            if self.lock_started <= 0:
                self.lock_started = current
            self.empty_checks = 0
            return AutoPositionGuardStatus(
                True,
                "operação Prime Trader ainda aberta no MT5; aguardando TP/SL ou fechamento manual",
                count,
            )

        # Se perdemos a conexão, nunca interpretamos a ausência de dados como
        # encerramento da operação. É mais seguro manter o bloqueio local.
        if not connected:
            if self.locked:
                return AutoPositionGuardStatus(
                    True,
                    "não foi possível confirmar o encerramento da operação porque o MT5 está desconectado",
                    0,
                )
            return AutoPositionGuardStatus(False, "nenhuma operação automática ativa", 0)

        if not self.locked:
            return AutoPositionGuardStatus(False, "nenhuma operação automática ativa", 0)

        elapsed = max(0.0, current - self.lock_started)
        if not self.position_seen and elapsed < self.sync_grace_seconds:
            return AutoPositionGuardStatus(
                True,
                "ordem aceita; aguardando sincronização da posição no MT5",
                0,
            )

        if self.position_seen:
            self.empty_checks += 1
            if self.empty_checks < self.flat_confirmations:
                return AutoPositionGuardStatus(
                    True,
                    "posição deixou de aparecer; confirmando encerramento no MT5",
                    0,
                )

        # A posição desapareceu de forma consistente. Isso cobre TP, SL e também
        # fechamento manual. O próximo sinal precisa ser uma nova confirmação.
        self.reset()
        return AutoPositionGuardStatus(
            False,
            "operação anterior encerrada; automático liberado para a próxima oportunidade",
            0,
            released=True,
        )


__all__ = ["AutoPositionGuardStatus", "PrimeAutoPositionGuard"]
