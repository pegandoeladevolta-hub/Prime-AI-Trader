from __future__ import annotations

from collections.abc import Callable

from ..core.models import Direction, SignalState, TIMEFRAME_MINUTES
from ..priceaction.mt5_levels import calculate_mt5_trade_plan
from .engine import SignalEngine


class MT5SignalEngine(SignalEngine):
    """Motor final de decisão para mercado com posição, Stop Loss e Take Profit.

    O motor-base continua produzindo a leitura técnica/IA. Esta camada
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
            .replace("antes da expiração", "no curto prazo")
            .replace("para payout", "para o filtro probabilístico")
            .replace("payout de", "parâmetro de retorno de")
            .replace("Expiração", "Gestão")
            .replace("expiração", "gestão")
        )

    @staticmethod
    def _only_legacy_timing_risk(signal) -> bool:
        """Detecta quando o único veto veio do horizonte herdado de binárias."""
        reasons = list(signal.all_waiting_reasons or signal.waiting_reasons or [])
        if not reasons:
            return False
        return all("Risco de reversão no curto prazo" in str(reason) for reason in reasons)

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
        try:
            minimum_rr = int(context.get("minimum_rr_x100", 150)) / 100.0
        except (TypeError, ValueError):
            minimum_rr = 1.5
        minimum_rr = min(5.0, max(0.5, minimum_rr))
        equivalent_return_percent = int(round(minimum_rr * 100))
        # O horizonte passado ao motor-base serve apenas para cálculos legados de
        # risco local. Ele nunca representa vencimento/fechamento da ordem MT5.
        internal_minutes = max(1, TIMEFRAME_MINUTES.get(timeframe, 1))
        signal = super().generate(
            indicators, features, structure, fib, internal_minutes,
            sensitivity, candle_closed, blockers, mode, context,
            # O motor-base expressa o ponto de equilíbrio como payout. Em MT5,
            # 1R de risco com alvo mínimo N*R é matematicamente equivalente a
            # retorno N*100% para esse cálculo probabilístico.
            payout_percent=equivalent_return_percent,
            source_lag_seconds=source_lag_seconds,
        )
        signal.horizon_minutes = 0
        signal.payout_percent = equivalent_return_percent
        signal.break_even_rate = 1 / (1 + minimum_rr)
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
        management_mode = str(context.get("management_mode") or "SCALP").upper()

        # No mercado real, uma leitura de reversão calculada pelo antigo horizonte
        # temporal não pode ser o único motivo para cancelar uma tese. Ela vira um
        # alerta; estrutura, momentum e principalmente SL/TP continuam decidindo.
        if signal.direction == Direction.WAIT and not signal.blockers and self._only_legacy_timing_risk(signal):
            candidate = (
                Direction.BUY
                if int(getattr(signal, "buy_score", 0) or 0) >= int(getattr(signal, "sell_score", 0) or 0)
                else Direction.SELL
            )
            timing_warning = signal.waiting_reasons[0] if signal.waiting_reasons else (
                "Possível reversão no curto prazo; risco considerado na gestão por Stop Loss"
            )
            signal.direction = candidate
            signal.state = SignalState.FORMING
            signal.waiting_reasons = []
            signal.all_waiting_reasons = []
            if timing_warning not in signal.warnings:
                signal.warnings.append(timing_warning)
            signal.validation_note = (
                "O risco temporal legado foi convertido em alerta; a tese MT5 será "
                "validada por contexto, estrutura e plano SL/TP. " + signal.validation_note
            ).strip()

        # Se os filtros técnicos reais ainda mandam aguardar, não fabricamos entrada.
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
