from __future__ import annotations

from collections.abc import Callable

from ..core.models import Direction, SignalState, TIMEFRAME_MINUTES
from ..priceaction.mt5_levels import calculate_mt5_trade_plan
from .engine import SignalEngine


class MT5SignalEngine(SignalEngine):
    """Motor final de decisão para mercado com posição, Stop Loss e Take Profit.

    O SignalEngine 1.2.6 continua produzindo a leitura técnica/IA. Esta camada
    substitui a decisão final herdada de expiração fixa por uma tese de trade que
    só é válida quando existe invalidação estrutural e espaço para o R:R escolhido.
    """

    def __init__(self, model_manager, context_provider: Callable[[], dict] | None = None) -> None:
        super().__init__(model_manager)
        self.context_provider = context_provider

    @staticmethod
    def _translate_legacy_text(text: str) -> str:
        return (
            str(text)
            .replace("antes da expiração", "antes de alcançar o alvo técnico")
            .replace("para payout", "para o filtro probabilístico")
            .replace("payout de", "parâmetro legado de")
            .replace("Expiração", "Gestão")
            .replace("expiração", "gestão")
        )

    def generate(self, indicators, features, structure, fib, horizon_minutes,
                 sensitivity, candle_closed, blockers=None, mode="CONFIRMAÇÃO",
                 model_context=None, payout_percent=80,
                 source_lag_seconds=None):
        context = dict(model_context or {})
        if self.context_provider is not None:
            try:
                runtime_context = dict(self.context_provider() or {})
            except Exception:
                runtime_context = {}
            # No analyze() legado o controller ainda monta um contexto mínimo.
            # O runtime MT5 completa esse contexto aqui com gestão, R:R e modelo.
            context.update(runtime_context)
        timeframe = str(context.get("timeframe") or "1m")
        # O horizonte passado ao motor-base serve apenas para seus filtros locais de
        # reversão. Para MT5 ele deixa de representar vencimento/fechamento da ordem.
        internal_minutes = max(1, TIMEFRAME_MINUTES.get(timeframe, 1))
        signal = super().generate(
            indicators, features, structure, fib, internal_minutes,
            sensitivity, candle_closed, blockers, mode, context,
            payout_percent=payout_percent, source_lag_seconds=source_lag_seconds,
        )
        signal.horizon_minutes = 0
        signal.waiting_reasons = [
            self._translate_legacy_text(item) for item in signal.waiting_reasons
        ]
        signal.all_waiting_reasons = [
            self._translate_legacy_text(item) for item in signal.all_waiting_reasons
        ]
        signal.warnings = [self._translate_legacy_text(item) for item in signal.warnings]
        signal.validation_note = self._translate_legacy_text(signal.validation_note)

        if str(context.get("trade_management") or "").upper() != "SLTP":
            return signal
        try:
            minimum_rr = int(context.get("minimum_rr_x100", 150)) / 100.0
        except (TypeError, ValueError):
            minimum_rr = 1.5
        management_mode = str(context.get("management_mode") or "SCALP").upper()

        # Se os filtros técnicos ainda mandam aguardar, não fabricamos uma entrada.
        if signal.direction == Direction.WAIT:
            return signal

        plan = calculate_mt5_trade_plan(
            indicators, structure, signal.direction,
            management_mode=management_mode, minimum_rr=minimum_rr,
        )
        if plan is None:
            signal.direction = Direction.WAIT
            signal.state = SignalState.WAITING
            signal.entry = None
            reason = "Não foi possível construir Stop e Alvo técnicos válidos"
            signal.waiting_reasons = [reason, *signal.waiting_reasons][:4]
            signal.all_waiting_reasons = list(dict.fromkeys([
                reason, *signal.all_waiting_reasons,
            ]))
            return signal

        signal.technical_stop = plan.stop
        signal.technical_target = plan.target
        signal.technical_room_ratio = plan.rr
        signal.technical_levels_note = (
            f"SL {plan.stop_basis}; TP {plan.target_basis}; "
            f"R:R {plan.rr:.2f} (mínimo {plan.minimum_rr:.2f})."
        )
        if not plan.viable:
            reason = (
                f"Espaço técnico oferece somente {plan.rr:.2f}R; "
                f"a configuração exige no mínimo {plan.minimum_rr:.2f}R"
            )
            signal.direction = Direction.WAIT
            signal.state = SignalState.WAITING
            signal.entry = None
            signal.waiting_reasons = [reason, *signal.waiting_reasons][:4]
            signal.all_waiting_reasons = list(dict.fromkeys([
                reason, *signal.all_waiting_reasons,
            ]))
            signal.validation_note = (
                "Entrada rejeitada por relação risco/retorno. Aguarde preço melhor "
                "ou nova estrutura de Stop/Alvo."
            )
            return signal

        signal.entry = plan.entry
        rr_note = (
            f"Plano MT5: entrada {plan.entry:g} • SL {plan.stop:g} • "
            f"TP {plan.target:g} • R:R {plan.rr:.2f}."
        )
        signal.validation_note = f"{rr_note} {signal.validation_note}".strip()
        return signal


__all__ = ["MT5SignalEngine"]
