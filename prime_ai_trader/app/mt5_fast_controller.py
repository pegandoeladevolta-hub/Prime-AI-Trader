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
FAST_STREAK_REQUIRED = 3
FAST_STABLE_SECONDS = 2.0


class FastSignalStability:
    """Estado puro da estabilidade intravela, independente da interface Tkinter."""

    def __init__(self) -> None:
        self.candidate = None
        self.streak = 0
        self.first_seen = 0.0

    def reset(self) -> None:
        self.candidate = None
        self.streak = 0
        self.first_seen = 0.0

    def observe(self, key: tuple, *, now: float | None = None) -> tuple[int, float, bool]:
        current = time.monotonic() if now is None else float(now)
        if key != self.candidate:
            self.candidate = key
            self.streak = 1
            self.first_seen = current
            return self.streak, 0.0, False
        self.streak += 1
        stable_for = max(0.0, current - self.first_seen)
        stable = self.streak >= FAST_STREAK_REQUIRED and stable_for >= FAST_STABLE_SECONDS
        return self.streak, stable_for, stable


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
    """Valida se um pré-sinal MT5 já possui qualidade para confirmação intravela."""
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

    return True, "pré-sinal elegível para confirmação rápida MT5"


class MT5FastTradingController(MT5TradingController):
    """Controller MT5 que confirma o perfil rápido no próprio fluxo de dados.

    A versão anterior dependia do renderizador da interface para contar leituras
    consecutivas. O histórico real mostrou sequências de 8-10 pré-sinais com score
    alto que nunca viravam CONFIRMADO. A estabilidade agora pertence ao controller,
    portanto funciona mesmo se a interface estiver ocupada ou redesenhando o gráfico.
    """

    def __init__(self) -> None:
        self._fast_promoted_candles: set[tuple] = set()
        self._fast_stability = FastSignalStability()
        self._last_fast_gate_reason = ""
        super().__init__()

    @staticmethod
    def _snapshot_candle(snapshot):
        history = snapshot.history_candles or snapshot.candles
        return history[-1] if history else None

    def _fast_candle_key(self, snapshot) -> tuple | None:
        candle = self._snapshot_candle(snapshot)
        if candle is None:
            return None
        return (snapshot.symbol, snapshot.timeframe, candle.open_time)

    def fast_intrabar_status(self, snapshot=None) -> tuple[bool, str]:
        snapshot = snapshot or self.snapshot
        if snapshot is None:
            return False, "sem snapshot"
        candle = self._snapshot_candle(snapshot)
        if candle is None:
            return False, "sem candles"
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

    def _promote_snapshot(self, snapshot, key: tuple):
        signal = snapshot.signal
        now = datetime.now(timezone.utc)
        note = (
            "Confirmação rápida MT5: direção estável em leituras consecutivas, "
            "score acima do piso rápido e plano de Entrada/SL/TP com R:R válido."
        )
        promoted_signal = replace(
            signal,
            state=SignalState.CONFIRMED,
            confirmed_candle=False,
            created_at=now,
            validation_note=f"{note} {signal.validation_note}".strip(),
        )
        promoted_snapshot = replace(snapshot, signal=promoted_signal, generated_at=now)
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
        self._fast_stability.reset()
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

    def _observe_intrabar(self, snapshot):
        signal = snapshot.signal
        candle = self._snapshot_candle(snapshot)
        if candle is None:
            self._fast_stability.reset()
            return snapshot

        candle_key = self._fast_candle_key(snapshot)
        if candle_key in self._fast_promoted_candles:
            return snapshot
        if signal.state != SignalState.FORMING or signal.direction == Direction.WAIT:
            self._fast_stability.reset()
            return snapshot

        candidate = (*candle_key, signal.direction.value)
        streak, stable_for, stable = self._fast_stability.observe(candidate)
        if not stable:
            self._last_fast_gate_reason = (
                f"estabilizando {signal.direction.value.lower()}: "
                f"{streak}/{FAST_STREAK_REQUIRED} leituras, {stable_for:.1f}s"
            )
            return snapshot

        eligible, reason = fast_intrabar_gate(
            signal,
            sensitivity=self.settings.sensitivity,
            mode=self.settings.mode,
            timeframe=snapshot.timeframe,
            minimum_rr=self.minimum_rr(),
            candle_open_time=candle.open_time,
            candle_closed=bool(candle.closed),
        )
        self._last_fast_gate_reason = reason
        if not eligible:
            return snapshot
        return self._promote_snapshot(snapshot, candle_key)

    def merge_live_candle(self, candle):
        snapshot = super().merge_live_candle(candle)
        if snapshot is None:
            return None
        return self._observe_intrabar(snapshot)

    def promote_intrabar_confirmation(self, snapshot=None):
        """Compatibilidade: promoção manual só ocorre quando o gate já está válido."""
        snapshot = snapshot or self.snapshot
        if snapshot is None:
            return None
        key = self._fast_candle_key(snapshot)
        if key is None or key in self._fast_promoted_candles:
            return None
        eligible, reason = self.fast_intrabar_status(snapshot)
        self._last_fast_gate_reason = reason
        if not eligible:
            return None
        return self._promote_snapshot(snapshot, key)


__all__ = [
    "MT5FastTradingController",
    "FastSignalStability",
    "fast_intrabar_gate",
]
