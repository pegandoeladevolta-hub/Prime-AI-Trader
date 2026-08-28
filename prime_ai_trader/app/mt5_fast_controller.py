from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone

from ..core.models import Direction, SignalState
from ..signals.engine import sensitivity_profile
from .mt5_controller import MT5TradingController


# Mantidos como aliases de compatibilidade com testes/versões anteriores.
FAST_STABLE_SECONDS = 0.75
FAST_STREAK_REQUIRED = 2

_PROFILE_STABILITY = {
    "RÁPIDO": (2, 0.75),
    "EQUILIBRADO": (3, 1.50),
    "CONSERVADOR": (4, 2.50),
}
_PROFILE_CONTEXT_SCORE = {
    "RÁPIDO": 4,
    "EQUILIBRADO": 5,
    "CONSERVADOR": 6,
}
_PROFILE_INDEPENDENT = {
    "RÁPIDO": 1,
    "EQUILIBRADO": 2,
    "CONSERVADOR": 3,
}


class MarketSignalStability:
    """Persistência da tese de mercado, sem vínculo com o fechamento de candle."""

    def __init__(self) -> None:
        self.candidate = None
        self.streak = 0
        self.first_seen = 0.0

    def reset(self) -> None:
        self.candidate = None
        self.streak = 0
        self.first_seen = 0.0

    def observe(
        self,
        key: tuple,
        *,
        required_streak: int = 2,
        required_seconds: float = 0.75,
        now: float | None = None,
    ) -> tuple[int, float, bool]:
        current = time.monotonic() if now is None else float(now)
        if key != self.candidate:
            self.candidate = key
            self.streak = 1
            self.first_seen = current
            return self.streak, 0.0, False
        self.streak += 1
        stable_for = max(0.0, current - self.first_seen)
        stable = self.streak >= max(1, int(required_streak)) and stable_for >= max(0.0, float(required_seconds))
        return self.streak, stable_for, stable


# Nome antigo preservado para não quebrar imports externos.
FastSignalStability = MarketSignalStability


def _aligned_structure(direction: Direction, structure_trend: str) -> bool:
    trend = str(structure_trend or "").upper()
    return (
        direction == Direction.BUY and trend == "ALTA"
        or direction == Direction.SELL and trend == "BAIXA"
    )


def _aligned_higher(direction: Direction, higher_bias: str) -> bool:
    bias = str(higher_bias or "").upper()
    return (
        direction == Direction.BUY and bias == "ALTA"
        or direction == Direction.SELL and bias == "BAIXA"
    )


def market_context_gate(
    signal,
    *,
    sensitivity: str,
    mode: str,
    minimum_rr: float,
    structure_trend: str = "",
) -> tuple[bool, str, int]:
    """Confirma se a tese já é negociável em mercado real.

    A decisão não depende da vela atual terminar. O candle aberto participa apenas
    como preço/gatilho; a autorização vem do conjunto: score, dominância entre os
    lados, estrutura, contexto superior, momentum, confirmações independentes e
    plano Entrada/SL/TP com R:R válido.
    """
    profile = sensitivity_profile(sensitivity)
    selected_mode = str(mode or "CONFIRMAÇÃO").upper()

    if signal.state not in {SignalState.FORMING, SignalState.CONFIRMED}:
        return False, "não existe tese direcional negociável", 0
    if signal.direction == Direction.WAIT:
        return False, "motor ainda recomenda aguardar", 0
    if signal.blockers or signal.waiting_reasons:
        return False, "a tese ainda possui bloqueios técnicos", 0

    entry = float(signal.entry or 0.0)
    stop = float(signal.technical_stop or 0.0)
    target = float(signal.technical_target or 0.0)
    rr = float(signal.technical_room_ratio or 0.0)
    if entry <= 0 or stop <= 0 or target <= 0:
        return False, "plano de Entrada/SL/TP incompleto", 0
    if rr + 1e-9 < float(minimum_rr):
        return False, f"R:R {rr:.2f} abaixo do mínimo {minimum_rr:.2f}", 0

    if int(signal.score or 0) < int(profile.score):
        return False, f"score {signal.score}/{profile.score}", 0

    buy_score = int(getattr(signal, "buy_score", 0) or 0)
    sell_score = int(getattr(signal, "sell_score", 0) or 0)
    if buy_score or sell_score:
        gap = abs(buy_score - sell_score)
        required_gap = max(3, int(profile.direction_gap) - (2 if selected_mode == "PRICE ACTION" else 0))
        if gap < required_gap:
            return False, f"dominância direcional {gap}/{required_gap}", 0

    context_score = 0
    trend = str(structure_trend or "").upper()
    if _aligned_structure(signal.direction, trend):
        context_score += 2
    elif trend in {"", "LATERAL", "INDEFINIDA"}:
        context_score += 1
    elif "CHOCH" in str(getattr(signal, "structure_event", "")).upper():
        # Reversão estrutural válida pode anteceder a atualização do rótulo HH/HL.
        context_score += 2

    higher = str(getattr(signal, "higher_timeframe_bias", "") or "").upper()
    if _aligned_higher(signal.direction, higher):
        context_score += 2
    elif higher in {"", "LATERAL", "INDEFINIDA"}:
        context_score += 1

    independent = list(getattr(signal, "independent_confirmations", []) or [])
    minimum_independent = _PROFILE_INDEPENDENT.get(profile.name, 2)
    if len(independent) >= minimum_independent:
        context_score += 2
    elif independent:
        context_score += 1

    momentum = int(getattr(signal, "momentum_votes", 0) or 0)
    if momentum >= int(profile.momentum):
        context_score += 2
    elif momentum > 0:
        context_score += 1

    setup = str(getattr(signal, "setup_name", "") or "").upper()
    if setup and "ANÁLISE EM FORMAÇÃO" not in setup:
        context_score += 1

    required_context = _PROFILE_CONTEXT_SCORE.get(profile.name, 5)
    if selected_mode == "PRICE ACTION":
        required_context = max(3, required_context - 1)
    elif selected_mode == "QUANTITATIVO":
        # O próprio motor-base já exige IA compatível no quantitativo.
        required_context += 1

    if context_score < required_context:
        return False, f"contexto de mercado {context_score}/{required_context}", context_score

    return True, (
        f"contexto contínuo válido ({context_score}/{required_context}) • "
        f"score {signal.score}/100 • R:R {rr:.2f}"
    ), context_score


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
    """Compatibilidade: a decisão MT5 não depende mais da idade/fechamento da vela."""
    allowed, reason, _ = market_context_gate(
        signal,
        sensitivity=sensitivity,
        mode=mode,
        minimum_rr=minimum_rr,
        structure_trend="",
    )
    return allowed, reason


class MT5FastTradingController(MT5TradingController):
    """Controller orientado a contexto contínuo de mercado real no MT5.

    O nome da classe é preservado para compatibilidade com o instalador atual. A
    lógica, porém, não é mais "rápida por candle": todos os perfis podem confirmar
    uma tese durante a vela aberta. O que muda entre RÁPIDO/EQUILIBRADO/CONSERVADOR
    é a quantidade de contexto e persistência exigida, não a espera pelo relógio.
    """

    def __init__(self) -> None:
        self._market_stability = MarketSignalStability()
        self._active_opportunity: tuple | None = None
        self._wait_observations = 0
        self._last_market_gate_reason = ""
        super().__init__()

    @staticmethod
    def _snapshot_candle(snapshot):
        history = snapshot.history_candles or snapshot.candles
        return history[-1] if history else None

    def _prepare_closed_candle_analysis(self, candle) -> None:
        """Garante que um fechamento recebido fora de ordem atualize o contexto.

        Fechar a vela não é mais requisito para sinal. Ainda assim, candles fechados
        alimentam estrutura, ATR, EMAs e demais cálculos históricos e não podem ser
        perdidos quando a nova vela já chegou ao stream.
        """
        if not getattr(candle, "closed", False) or self.snapshot is None:
            return
        history = list(self.snapshot.history_candles or self.snapshot.candles)
        if not history or history[-1].open_time <= candle.open_time:
            return
        trimmed = [item for item in history if item.open_time <= candle.open_time]
        if not trimmed:
            return
        self.snapshot = replace(self.snapshot, history_candles=trimmed)

    @staticmethod
    def _opportunity_key(snapshot) -> tuple | None:
        signal = snapshot.signal
        if signal.direction == Direction.WAIT or not signal.entry or not signal.technical_stop:
            return None
        risk = abs(float(signal.entry) - float(signal.technical_stop))
        bucket_size = max(risk * 0.50, abs(float(signal.entry)) * 1e-6, 1e-9)
        price_bucket = int(round(float(signal.entry) / bucket_size))
        return (
            snapshot.symbol,
            snapshot.timeframe,
            signal.direction.value,
            str(signal.setup_name or "CONTEXTO"),
            price_bucket,
        )

    def market_context_status(self, snapshot=None) -> tuple[bool, str, int]:
        snapshot = snapshot or self.snapshot
        if snapshot is None:
            return False, "sem snapshot", 0
        return market_context_gate(
            snapshot.signal,
            sensitivity=self.settings.sensitivity,
            mode=self.settings.mode,
            minimum_rr=self.minimum_rr(),
            structure_trend=getattr(snapshot.structure, "trend", ""),
        )

    def fast_intrabar_status(self, snapshot=None) -> tuple[bool, str]:
        allowed, reason, _ = self.market_context_status(snapshot)
        return allowed, reason

    def _promote_snapshot(self, snapshot, key: tuple, context_score: int):
        signal = snapshot.signal
        now = datetime.now(timezone.utc)
        note = (
            "Confirmação MT5 por contexto contínuo: tendência/estrutura, momentum, "
            "confluências e plano Entrada/SL/TP permaneceram válidos em leituras "
            "consecutivas. O fechamento da vela não foi usado como gatilho obrigatório."
        )
        promoted_signal = replace(
            signal,
            state=SignalState.CONFIRMED,
            confirmed_candle=False,
            created_at=now,
            validation_note=(
                f"{note} Contexto {context_score}/10. {signal.validation_note}"
            ).strip(),
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
        self._active_opportunity = key
        self._wait_observations = 0
        self._market_stability.reset()
        self.logger.info(
            "Sinal MT5 por contexto | %s %s score=%s contexto=%s R:R=%.2f",
            snapshot.symbol,
            promoted_signal.direction.value,
            promoted_signal.score,
            context_score,
            float(promoted_signal.technical_room_ratio or 0.0),
        )
        return promoted_snapshot

    def _observe_market_context(self, snapshot):
        signal = snapshot.signal

        # Um fechamento já confirmado pelo motor-base também marca a oportunidade
        # como ativa, mas ele não é necessário para chegar a CONFIRMADO.
        if signal.state == SignalState.CONFIRMED and signal.direction != Direction.WAIT:
            key = self._opportunity_key(snapshot)
            if key is not None:
                self._active_opportunity = key
            self._market_stability.reset()
            self._wait_observations = 0
            return snapshot

        if signal.state != SignalState.FORMING or signal.direction == Direction.WAIT:
            self._market_stability.reset()
            self._wait_observations += 1
            # Duas leituras sem tese encerram a oportunidade antiga e permitem uma
            # nova entrada futura, mesmo que seja no mesmo sentido/setup.
            if self._wait_observations >= 2:
                self._active_opportunity = None
            return snapshot

        self._wait_observations = 0
        key = self._opportunity_key(snapshot)
        if key is None:
            self._market_stability.reset()
            return snapshot
        if key == self._active_opportunity:
            return snapshot

        eligible, reason, context_score = self.market_context_status(snapshot)
        self._last_market_gate_reason = reason
        if not eligible:
            self._market_stability.reset()
            return snapshot

        profile_name = sensitivity_profile(self.settings.sensitivity).name
        required_streak, required_seconds = _PROFILE_STABILITY.get(profile_name, (3, 1.5))
        mode = str(self.settings.mode or "CONFIRMAÇÃO").upper()
        if mode == "PRICE ACTION":
            required_streak = max(2, required_streak - 1)
            required_seconds = max(0.50, required_seconds - 0.25)
        elif mode == "QUANTITATIVO":
            required_seconds += 0.50

        streak, stable_for, stable = self._market_stability.observe(
            key,
            required_streak=required_streak,
            required_seconds=required_seconds,
        )
        if not stable:
            self._last_market_gate_reason = (
                f"tese {signal.direction.value.lower()} válida; confirmando persistência "
                f"{streak}/{required_streak} • {stable_for:.1f}/{required_seconds:.1f}s"
            )
            return snapshot

        return self._promote_snapshot(snapshot, key, context_score)

    def merge_live_candle(self, candle):
        self._prepare_closed_candle_analysis(candle)
        snapshot = super().merge_live_candle(candle)
        if snapshot is None:
            return None
        return self._observe_market_context(snapshot)

    def promote_intrabar_confirmation(self, snapshot=None):
        """Compatibilidade para versões antigas da interface."""
        snapshot = snapshot or self.snapshot
        if snapshot is None:
            return None
        observed = self._observe_market_context(snapshot)
        return observed if observed is not snapshot else None


__all__ = [
    "MT5FastTradingController",
    "MarketSignalStability",
    "FastSignalStability",
    "market_context_gate",
    "fast_intrabar_gate",
    "FAST_STABLE_SECONDS",
    "FAST_STREAK_REQUIRED",
]
