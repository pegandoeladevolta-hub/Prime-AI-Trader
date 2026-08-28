from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone

from ..core.models import Direction, SignalState, TIMEFRAME_MINUTES
from ..signals.engine import sensitivity_profile
from .mt5_controller import MT5TradingController


FAST_SCORE_MARGIN = 6
FAST_MIN_ELAPSED_SECONDS = 4.0
FAST_MAX_ELAPSED_SECONDS = 45.0
FAST_ELAPSED_FRACTION = 0.08


def fast_intrabar_gate(
    signal,
    *,
    sensitivity: str,
    mode: str,
    timeframe: str,
    minimum_rr: float,
    candle_open_time: datetime,
    candle_closed: bool,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Decide se um pré-sinal MT5 pode ser confirmado antes do fechamento.

    A confirmação rápida existe somente para RÁPIDO + PRICE ACTION. O sinal já
    precisa ter passado todos os filtros do motor-base (estado FORMING sem
    blockers/waiting), possuir Stop/Alvo e ter margem extra de score. Também
    exigimos que a vela esteja aberta há tempo suficiente para evitar entrada no
    primeiro tick do candle.
    """
    if str(sensitivity or "").upper() != "RÁPIDO":
        return False, "perfil não é RÁPIDO"
    if str(mode or "").upper() != "PRICE ACTION":
        return False, "modo exige fechamento normal"
    if candle_closed:
        return False, "vela já fechada; confirmação normal tem prioridade"
    if signal.state != SignalState.FORMING or signal.direction == Direction.WAIT:
        return False, "não existe pré-sinal direcional em formação"
    if signal.blockers or signal.waiting_reasons:
        return False, "o motor técnico ainda possui bloqueios"

    required_score = sensitivity_profile("RÁPIDO").score + FAST_SCORE_MARGIN
    if int(signal.score or 0) < required_score:
        return False, f"score {signal.score}/{required_score} para confirmação rápida"

    entry = float(signal.entry or 0.0)
    stop = float(signal.technical_stop or 0.0)
    target = float(signal.technical_target or 0.0)
    rr = float(signal.technical_room_ratio or 0.0)
    if entry <= 0 or stop <= 0 or target <= 0:
        return False, "plano de Entrada/SL/TP ainda incompleto"
    if rr + 1e-9 < float(minimum_rr):
        return False, f"R:R {rr:.2f} abaixo do mínimo {minimum_rr:.2f}"

    current = now or datetime.now(timezone.utc)
    opened = candle_open_time
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    else:
        opened = opened.astimezone(timezone.utc)
    elapsed = max(0.0, (current.astimezone(timezone.utc) - opened).total_seconds())
    timeframe_seconds = max(60, TIMEFRAME_MINUTES.get(timeframe, 1) * 60)
    minimum_elapsed = max(
        FAST_MIN_ELAPSED_SECONDS,
        min(FAST_MAX_ELAPSED_SECONDS, timeframe_seconds * FAST_ELAPSED_FRACTION),
    )
    if elapsed < minimum_elapsed:
        return False, f"vela aberta há {elapsed:.1f}s; mínimo rápido {minimum_elapsed:.1f}s"

    return True, "pré-sinal estável elegível para confirmação rápida MT5"


class MT5FastTradingController(MT5TradingController):
    """Controller MT5 com promoção controlada de pré-sinal no perfil RÁPIDO.

    A análise técnica e a construção do plano SL/TP continuam no motor existente.
    Esta camada apenas elimina a dependência absoluta do fechamento quando o
    usuário escolhe explicitamente RÁPIDO + PRICE ACTION.
    """

    def __init__(self) -> None:
        self._fast_promoted_candles: set[tuple] = set()
        super().__init__()

    def _fast_candle_key(self, snapshot) -> tuple | None:
        history = snapshot.history_candles or snapshot.candles
        if not history:
            return None
        candle = history[-1]
        return (snapshot.symbol, snapshot.timeframe, candle.open_time)

    def fast_intrabar_status(self, snapshot=None) -> tuple[bool, str]:
        snapshot = snapshot or self.snapshot
        if snapshot is None:
            return False, "sem snapshot"
        history = snapshot.history_candles or snapshot.candles
        if not history:
            return False, "sem candles"
        candle = history[-1]
        key = self._fast_candle_key(snapshot)
        if key in self._fast_promoted_candles:
            return False, "já houve confirmação rápida nesta vela"
        return fast_intrabar_gate(
            snapshot.signal,
            sensitivity=self.settings.sensitivity,
            mode=self.settings.mode,
            timeframe=snapshot.timeframe,
            minimum_rr=self.minimum_rr(),
            candle_open_time=candle.open_time,
            candle_closed=bool(candle.closed),
        )

    def promote_intrabar_confirmation(self, snapshot=None):
        snapshot = snapshot or self.snapshot
        eligible, reason = self.fast_intrabar_status(snapshot)
        if not eligible or snapshot is None:
            return None

        key = self._fast_candle_key(snapshot)
        if key is None:
            return None
        signal = snapshot.signal
        now = datetime.now(timezone.utc)
        note = (
            "Confirmação rápida MT5: direção permaneceu estável em leituras "
            "consecutivas, score acima do piso rápido e plano de Stop/Alvo válido. "
            "Não houve espera por expiração nem por fechamento obrigatório."
        )
        promoted_signal = replace(
            signal,
            state=SignalState.CONFIRMED,
            confirmed_candle=False,
            created_at=now,
            validation_note=f"{note} {signal.validation_note}".strip(),
        )
        promoted_snapshot = replace(
            snapshot,
            signal=promoted_signal,
            generated_at=now,
        )
        self.snapshot = promoted_snapshot
        cache_key = (snapshot.market, snapshot.symbol, snapshot.timeframe)
        self._snapshot_cache[cache_key] = (time.monotonic(), promoted_snapshot)

        signal_id = self._record_signal(
            promoted_signal,
            snapshot.market,
            snapshot.symbol,
            snapshot.timeframe,
            snapshot.candles,
            snapshot.indicators,
            self.settings.mode,
        )
        self._record_decision(promoted_snapshot, signal_id=signal_id)
        self._fast_promoted_candles.add(key)
        if len(self._fast_promoted_candles) > 256:
            self._fast_promoted_candles = set(list(self._fast_promoted_candles)[-128:])
        self.logger.info(
            "Confirmação rápida MT5 | %s %s score=%s R:R=%.2f",
            snapshot.symbol,
            promoted_signal.direction.value,
            promoted_signal.score,
            float(promoted_signal.technical_room_ratio or 0.0),
        )
        return promoted_snapshot


__all__ = ["MT5FastTradingController", "fast_intrabar_gate"]
