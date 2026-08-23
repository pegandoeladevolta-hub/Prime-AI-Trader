"""Compatibility overlay that adds market-specific confirmation rules."""

from __future__ import annotations

from dataclasses import replace

from . import legacy_engine as _legacy
from .market_guard import evaluate_market_entry


SensitivityProfile = _legacy.SensitivityProfile
SENSITIVITY_PROFILES = _legacy.SENSITIVITY_PROFILES
sensitivity_profile = _legacy.sensitivity_profile
RuleAssessment = _legacy.RuleAssessment


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def _wait_probabilities(probabilities, rejected_direction):
    values = dict(probabilities or {})
    wait = max(float(values.get("AGUARDAR", 0.0)), 0.55)
    remaining = max(0.0, 1.0 - wait)
    buy = max(0.0, float(values.get("COMPRA", 0.0)))
    sell = max(0.0, float(values.get("VENDA", 0.0)))
    directional_total = buy + sell
    if directional_total:
        buy = remaining * buy / directional_total
        sell = remaining * sell / directional_total
    else:
        buy = sell = remaining / 2.0
    return {"COMPRA": buy, "VENDA": sell, "AGUARDAR": wait}


class SignalEngine(_legacy.SignalEngine):
    """Legacy scoring plus deterministic CRYPTO/FOREX entry confirmation."""

    def generate(
        self,
        indicators,
        features,
        structure,
        fib,
        horizon_minutes,
        sensitivity,
        candle_closed,
        blockers=None,
        mode="CONFIRMAÇÃO",
        model_context=None,
        payout_percent=80,
    ):
        signal = super().generate(
            indicators,
            features,
            structure,
            fib,
            horizon_minutes,
            sensitivity,
            candle_closed,
            blockers,
            mode,
            model_context,
            payout_percent=payout_percent,
        )
        context = model_context or {}
        decision = evaluate_market_entry(
            indicators=indicators,
            features=features,
            direction=signal.direction,
            market=context.get("market"),
            sensitivity=sensitivity,
            mode=mode,
            candle_closed=candle_closed,
            score=signal.score,
            probabilities=signal.probabilities,
            payout_percent=payout_percent,
        )
        note = f"Perfil aplicado: {decision.profile}"
        validation_note = " • ".join(part for part in (signal.validation_note, note) if part)
        if decision.allowed or signal.state == _legacy.SignalState.BLOCKED:
            return replace(
                signal,
                confluences=_unique([*signal.confluences, *decision.confirmations]),
                validation_note=validation_note,
            )

        reasons = _unique([*signal.waiting_reasons, *decision.reasons])
        rejected_direction = signal.direction.value
        minimum_visible_score = 63 if "CRIPTO" in decision.profile else 65
        return replace(
            signal,
            direction=_legacy.Direction.WAIT,
            state=_legacy.SignalState.WAITING,
            score=min(int(signal.score), minimum_visible_score),
            probabilities=_wait_probabilities(signal.probabilities, rejected_direction),
            entry=None,
            setup_name=f"AGUARDAR • {decision.profile.split(' • ', 1)[0]}",
            waiting_reasons=reasons,
            confluences=_unique([*signal.confluences, *decision.confirmations]),
            validation_note=validation_note,
        )
