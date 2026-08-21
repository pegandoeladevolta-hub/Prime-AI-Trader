from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from ..core.models import Direction, Signal, SignalState
from ..fibonacci.auto import FibonacciResult
from ..ml.models import ModelManager
from ..priceaction.professional import ProfessionalAssessment, assess_professional_market
from ..priceaction.structure import MarketStructure


@dataclass(frozen=True, slots=True)
class SensitivityProfile:
    name: str
    description: str
    score: int
    probability_floor: float
    probability_edge: float
    confluences: int
    momentum: int
    minimum_adx: int
    direction_gap: int
    maximum_extension_atr: float
    volatility_minimum: float
    volatility_maximum: float
    payout_margin: float
    model_weight_factor: float
    early_reading: bool = False


SENSITIVITY_PROFILES = {
    "CONSERVADOR": SensitivityProfile(
        "CONSERVADOR", "ALTA CONFIRMAÇÃO • menos sinais e maior exigência",
        86, 0.70, 0.18, 5, 3, 20, 16, 2.0, 0.45, 2.8, 0.05, 1.10,
    ),
    "EQUILIBRADO": SensitivityProfile(
        "EQUILIBRADO", "EQUILIBRADO • confirmação e frequência moderadas",
        73, 0.60, 0.12, 4, 2, 15, 10, 2.5, 0.35, 3.3, 0.02, 1.0,
    ),
    "RÁPIDO": SensitivityProfile(
        "RÁPIDO", "LEITURA RÁPIDA • direção imediata e mais oportunidades",
        57, 0.54, 0.06, 2, 1, 10, 5, 3.3, 0.22, 4.2, 0.002, 0.60, True,
    ),
}


def sensitivity_profile(name: str) -> SensitivityProfile:
    return SENSITIVITY_PROFILES.get(str(name or "").upper(), SENSITIVITY_PROFILES["EQUILIBRADO"])


THRESHOLDS = {name: profile.score for name, profile in SENSITIVITY_PROFILES.items()}
PROBABILITY_FLOORS = {name: profile.probability_floor for name, profile in SENSITIVITY_PROFILES.items()}
PROBABILITY_EDGES = {name: profile.probability_edge for name, profile in SENSITIVITY_PROFILES.items()}
CONFLUENCE_MINIMUMS = {name: profile.confluences for name, profile in SENSITIVITY_PROFILES.items()}
MOMENTUM_MINIMUMS = {name: profile.momentum for name, profile in SENSITIVITY_PROFILES.items()}


@dataclass(slots=True)
class RuleAssessment:
    buy_points: int
    sell_points: int
    buy_reasons: list[str]
    sell_reasons: list[str]
    buy_setup: str = "ANÁLISE EM FORMAÇÃO"
    sell_setup: str = "ANÁLISE EM FORMAÇÃO"
    higher_timeframe_bias: str = "INDEFINIDA"
    professional: ProfessionalAssessment | None = None


def _number(value, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _higher_timeframe_bias(indicators: pd.DataFrame) -> tuple[str, str]:
    if len(indicators) < 80 or not isinstance(indicators.index, pd.DatetimeIndex):
        return "INDEFINIDA", ""
    spacing = indicators.index.to_series().diff().dropna().tail(80).median()
    if pd.isna(spacing) or spacing.total_seconds() <= 0:
        return "INDEFINIDA", ""
    minutes = max(1, round(spacing.total_seconds() / 60))
    target = {1: 5, 3: 15, 5: 15, 15: 60, 30: 120, 60: 240, 240: 1440}.get(minutes, minutes * 3)
    frame = indicators[["open", "high", "low", "close", "volume"]].tail(600)
    bars = frame.resample(f"{target}min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()
    bars = bars.iloc[:-1]
    if len(bars) < 22:
        return "INDEFINIDA", ""
    fast = bars["close"].ewm(span=8, adjust=False).mean().iloc[-1]
    slow = bars["close"].ewm(span=21, adjust=False).mean().iloc[-1]
    close = float(bars["close"].iloc[-1])
    label = f"{target // 60}h" if target >= 60 and target % 60 == 0 else f"{target}m"
    if close > fast > slow:
        return "ALTA", label
    if close < fast < slow:
        return "BAIXA", label
    return "LATERAL", label


class SignalEngine:
    def __init__(self, model_manager: ModelManager) -> None:
        self.model_manager = model_manager

    @staticmethod
    def assess_rules(indicators: pd.DataFrame, structure: MarketStructure,
                     fib: FibonacciResult | None,
                     professional: ProfessionalAssessment | None = None,
                     mode: str = "CONFIRMAÇÃO") -> RuleAssessment:
        last = indicators.iloc[-1]
        previous = indicators.iloc[-2] if len(indicators) >= 2 else last
        buy = sell = 0
        buy_reasons: list[str] = []
        sell_reasons: list[str] = []
        buy_setup = sell_setup = "CONTINUIDADE DE TENDÊNCIA"
        close = _number(last.get("close"))
        opened = _number(last.get("open"))
        ema_9 = _number(last.get("ema_9"), close)
        ema_21 = _number(last.get("ema_21"), close)
        ema_50 = _number(last.get("ema_50"), close)
        atr = _number(last.get("atr_14"))
        rsi = _number(last.get("rsi_14"), 50.0)
        macd_hist = _number(last.get("macd_hist"))
        previous_macd = _number(previous.get("macd_hist"))
        adx = _number(last.get("adx_14"))
        plus_di = _number(last.get("plus_di"))
        minus_di = _number(last.get("minus_di"))
        close_position = _number(last.get("close_position"), 0.5)
        body = _number(last.get("body"), abs(close - opened))

        if ema_9 > ema_21 > ema_50:
            buy += 18; buy_reasons.append("EMAs 9/21/50 alinhadas para alta")
        elif ema_9 < ema_21 < ema_50:
            sell += 18; sell_reasons.append("EMAs 9/21/50 alinhadas para baixa")
        elif ema_9 > ema_21:
            buy += 8; buy_reasons.append("EMA 9 acima da EMA 21")
        elif ema_9 < ema_21:
            sell += 8; sell_reasons.append("EMA 9 abaixo da EMA 21")

        if 51 <= rsi <= 72:
            buy += 10; buy_reasons.append(f"RSI comprador sem excesso ({rsi:.1f})")
        elif 28 <= rsi <= 49:
            sell += 10; sell_reasons.append(f"RSI vendedor sem excesso ({rsi:.1f})")

        if macd_hist > 0:
            buy += 9; buy_reasons.append("MACD acima da linha de sinal")
            if macd_hist > previous_macd:
                buy += 6; buy_reasons.append("Momentum comprador acelerando")
        elif macd_hist < 0:
            sell += 9; sell_reasons.append("MACD abaixo da linha de sinal")
            if macd_hist < previous_macd:
                sell += 6; sell_reasons.append("Momentum vendedor acelerando")

        if adx >= 18:
            strength = 13 if adx >= 23 else 8
            if plus_di > minus_di:
                buy += strength; buy_reasons.append(f"ADX/+DI confirma força compradora ({adx:.1f})")
            elif minus_di > plus_di:
                sell += strength; sell_reasons.append(f"ADX/-DI confirma força vendedora ({adx:.1f})")

        vwap = _number(last.get("vwap"))
        if vwap > 0:
            if close > vwap:
                buy += 7; buy_reasons.append("Preço acima da VWAP")
            elif close < vwap:
                sell += 7; sell_reasons.append("Preço abaixo da VWAP")

        volume_relative = _number(last.get("volume_relative"))
        if volume_relative >= 1.15:
            if close >= opened:
                buy += 9; buy_reasons.append(f"Volume comprador {volume_relative:.2f}x")
            else:
                sell += 9; sell_reasons.append(f"Volume vendedor {volume_relative:.2f}x")

        stoch_k = _number(last.get("stoch_k"), 50)
        stoch_d = _number(last.get("stoch_d"), 50)
        if 20 <= stoch_k <= 82 and stoch_k > stoch_d and ema_9 >= ema_21:
            buy += 6; buy_reasons.append("Estocástico confirma continuação compradora")
        elif 18 <= stoch_k <= 80 and stoch_k < stoch_d and ema_9 <= ema_21:
            sell += 6; sell_reasons.append("Estocástico confirma continuação vendedora")

        if structure.trend == "ALTA":
            buy += 15; buy_reasons.append("Estrutura profissional HH/HL")
        elif structure.trend == "BAIXA":
            sell += 15; sell_reasons.append("Estrutura profissional LH/LL")

        higher_bias, higher_label = _higher_timeframe_bias(indicators)
        if higher_bias == "ALTA":
            buy += 10; buy_reasons.append(f"Timeframe superior {higher_label} alinhado para alta")
        elif higher_bias == "BAIXA":
            sell += 10; sell_reasons.append(f"Timeframe superior {higher_label} alinhado para baixa")

        if structure.breakout == "ROMPIMENTO DE ALTA" and close_position >= 0.55:
            buy += 14; buy_reasons.append("Rompimento de resistência com fechamento comprador")
            buy_setup = "ROMPIMENTO + CONFIRMAÇÃO"
        elif structure.breakout == "ROMPIMENTO DE BAIXA" and close_position <= 0.45:
            sell += 14; sell_reasons.append("Rompimento de suporte com fechamento vendedor")
            sell_setup = "ROMPIMENTO + CONFIRMAÇÃO"

        if structure.retest and structure.trend == "ALTA" and close > opened:
            buy += 12; buy_reasons.append("Reteste confirmado na tendência de alta")
            buy_setup = "ROMPIMENTO + RETESTE"
        elif structure.retest and structure.trend == "BAIXA" and close < opened:
            sell += 12; sell_reasons.append("Reteste confirmado na tendência de baixa")
            sell_setup = "ROMPIMENTO + RETESTE"

        if atr > 0 and ema_9 >= ema_21 and _number(last.get("low")) <= ema_21 + atr * 0.40 and close > ema_21 and close > opened:
            buy += 12; buy_reasons.append("Pullback na EMA 21 com rejeição compradora")
            buy_setup = "PULLBACK DE TENDÊNCIA"
        elif atr > 0 and ema_9 <= ema_21 and _number(last.get("high")) >= ema_21 - atr * 0.40 and close < ema_21 and close < opened:
            sell += 12; sell_reasons.append("Pullback na EMA 21 com rejeição vendedora")
            sell_setup = "PULLBACK DE TENDÊNCIA"

        lower_wick = _number(last.get("lower_wick"))
        upper_wick = _number(last.get("upper_wick"))
        if structure.support_zones:
            support = structure.support_zones[0]
            if _number(last.get("low")) < support.low and close > support.midpoint and lower_wick > max(body * 1.2, atr * 0.18):
                buy += 14; buy_reasons.append("Varredura de liquidez e rejeição no suporte")
                buy_setup = "LIQUIDEZ + REJEIÇÃO"
        if structure.resistance_zones:
            resistance = structure.resistance_zones[0]
            if _number(last.get("high")) > resistance.high and close < resistance.midpoint and upper_wick > max(body * 1.2, atr * 0.18):
                sell += 14; sell_reasons.append("Varredura de liquidez e rejeição na resistência")
                sell_setup = "LIQUIDEZ + REJEIÇÃO"

        previous_open = _number(previous.get("open"))
        previous_close = _number(previous.get("close"))
        if previous_close < previous_open and close > opened and close >= previous_open and opened <= previous_close:
            buy += 8; buy_reasons.append("Engolfo comprador confirmado")
        elif previous_close > previous_open and close < opened and close <= previous_open and opened >= previous_close:
            sell += 8; sell_reasons.append("Engolfo vendedor confirmado")

        if structure.false_breakout:
            if "LIQUIDEZ" not in buy_setup:
                buy = max(0, buy - 7)
            if "LIQUIDEZ" not in sell_setup:
                sell = max(0, sell - 7)

        if fib and fib.distance_pct <= 0.35 and fib.nearest_ratio in {0.5, 0.618, 0.786}:
            if fib.direction == "IMPULSO DE ALTA":
                buy += 8; buy_reasons.append(f"Retração Fibonacci {fib.nearest_ratio * 100:.1f}%")
            else:
                sell += 8; sell_reasons.append(f"Retração Fibonacci {fib.nearest_ratio * 100:.1f}%")

        if professional:
            action_factor = {"PRICE ACTION": 1.20, "CONFIRMAÇÃO": 1.0,
                             "QUANTITATIVO": 0.82}.get(mode, 1.0)
            if professional.event:
                points = round((18 if professional.event.kind == "CHOCH" else 13) * action_factor)
                if professional.event.direction == Direction.BUY:
                    buy += points
                else:
                    sell += points
            if professional.pullback and professional.pullback.confirmed:
                points = round(14 * action_factor)
                if professional.pullback.direction == Direction.BUY:
                    buy += points
                else:
                    sell += points
            strongest_buy = max((item.strength for item in professional.divergences
                                 if item.direction == Direction.BUY), default=0.0)
            strongest_sell = max((item.strength for item in professional.divergences
                                  if item.direction == Direction.SELL), default=0.0)
            buy += round(strongest_buy * 9)
            sell += round(strongest_sell * 9)
            if professional.regime.direction == Direction.BUY and not professional.regime.exhausted:
                buy += 5
            elif professional.regime.direction == Direction.SELL and not professional.regime.exhausted:
                sell += 5
            buy_reasons = list(dict.fromkeys((*professional.buy_reasons, *buy_reasons)))
            sell_reasons = list(dict.fromkeys((*professional.sell_reasons, *sell_reasons)))
            buy_setup = professional.buy_setup or buy_setup
            sell_setup = professional.sell_setup or sell_setup

        return RuleAssessment(
            min(buy, 100), min(sell, 100), buy_reasons, sell_reasons,
            buy_setup, sell_setup, higher_bias, professional,
        )

    @staticmethod
    def _technical_score(points: int, opposite: int, reasons: int) -> int:
        if points <= 0:
            return 0
        dominance = points / max(points + opposite + 12, 1)
        return min(100, round(18 + points * 0.68 + min(reasons, 8) * 3 + dominance * 17))

    @staticmethod
    def _independent_confirmations(reasons: list[str]) -> set[str]:
        categories: set[str] = set()
        for reason in reasons:
            text = reason.lower()
            if any(word in text for word in ("ema", "estrutura", "hh/hl", "lh/ll", "vwap", "bos", "choch", "regime")):
                categories.add("tendência")
            if any(word in text for word in ("rsi", "macd", "momentum", "adx", "+di", "-di", "estocástico", "divergência")):
                categories.add("momentum")
            if any(word in text for word in ("rompimento", "reteste", "pullback", "liquidez", "rejeição", "engolfo", "fibonacci", "retração", "vela")):
                categories.add("price action")
            if "volume" in text:
                categories.add("volume")
            if "timeframe superior" in text:
                categories.add("timeframe superior")
        return categories

    def generate(self, indicators: pd.DataFrame, features: pd.DataFrame,
                 structure: MarketStructure, fib: FibonacciResult | None,
                 horizon_minutes: int, sensitivity: str, candle_closed: bool,
                 blockers: list[str] | None = None, mode: str = "CONFIRMAÇÃO",
                 model_context: dict[str, str | int] | None = None,
                 payout_percent: int = 80) -> Signal:
        payout = min(max(int(payout_percent or 80), 1), 200)
        break_even = 1 / (1 + payout / 100)
        profile = sensitivity_profile(sensitivity)
        blockers = blockers or []
        if blockers:
            return Signal(
                Direction.WAIT, SignalState.BLOCKED, 0,
                {"COMPRA": 0, "VENDA": 0, "AGUARDAR": 1}, None,
                horizon_minutes, blockers=blockers,
                payout_percent=payout, break_even_rate=break_even,
            )

        context_timeframe = str(model_context.get("timeframe", "")) if model_context else ""
        professional = assess_professional_market(indicators, structure, fib, context_timeframe)
        rules = self.assess_rules(indicators, structure, fib, professional, mode)
        technical_buy = self._technical_score(rules.buy_points, rules.sell_points, len(rules.buy_reasons))
        technical_sell = self._technical_score(rules.sell_points, rules.buy_points, len(rules.sell_reasons))
        model_ready = self.model_manager.is_compatible(model_context)
        if model_ready:
            raw = self.model_manager.predict_proba(features)
            probabilities = {
                "COMPRA": raw.get(1, 0.0), "VENDA": raw.get(-1, 0.0),
                "AGUARDAR": raw.get(0, 0.0),
            }
            base_model_weight = {"PRICE ACTION": 0.30, "CONFIRMAÇÃO": 0.45,
                                 "QUANTITATIVO": 0.65}.get(mode, 0.45)
            model_weight = min(0.85, max(0.12, base_model_weight * profile.model_weight_factor))
            buy_agreement = 7 if probabilities["COMPRA"] > probabilities["VENDA"] and technical_buy >= 60 else 0
            sell_agreement = 7 if probabilities["VENDA"] > probabilities["COMPRA"] and technical_sell >= 60 else 0
            buy_score = min(100, round(model_weight * probabilities["COMPRA"] * 100 +
                                      (1 - model_weight) * technical_buy + buy_agreement))
            sell_score = min(100, round(model_weight * probabilities["VENDA"] * 100 +
                                       (1 - model_weight) * technical_sell + sell_agreement))
            model_version = self.model_manager.report.version
        else:
            buy_score, sell_score = technical_buy, technical_sell
            total = max(rules.buy_points + rules.sell_points + 40, 1)
            probabilities = {
                "COMPRA": (rules.buy_points + 10) / total,
                "VENDA": (rules.sell_points + 10) / total,
                "AGUARDAR": 20 / total,
            }
            model_version = "rules-professional-v2"

        sensitivity_key = profile.name
        threshold = profile.score
        if buy_score >= sell_score:
            direction, score, confluences = Direction.BUY, buy_score, rules.buy_reasons
            technical_score, setup_name = technical_buy, rules.buy_setup
        else:
            direction, score, confluences = Direction.SELL, sell_score, rules.sell_reasons
            technical_score, setup_name = technical_sell, rules.sell_setup

        last = indicators.iloc[-1]
        direction_sign = 1 if direction == Direction.BUY else -1
        momentum_votes = (
            direction_sign * (_number(last.get("ema_9")) - _number(last.get("ema_21"))) > 0,
            direction_sign * _number(last.get("macd_hist")) > 0,
            direction_sign * (_number(last.get("plus_di")) - _number(last.get("minus_di"))) > 0,
            structure.trend != ("BAIXA" if direction == Direction.BUY else "ALTA"),
        )
        adx = _number(last.get("adx_14"))
        weak_regime = adx > 0 and adx < profile.minimum_adx and not structure.breakout
        atr_value = _number(last.get("atr_14"))
        close_value = _number(last.get("close"))
        ema_21 = _number(last.get("ema_21"), close_value)
        overextended = (
            atr_value > 0 and
            abs(close_value - ema_21) > profile.maximum_extension_atr * atr_value
        )
        feature_row = features.iloc[-1] if not features.empty else pd.Series(dtype=float)
        atr_regime = feature_row.get("atr_regime")
        volatility_ok = (
            pd.isna(atr_regime) or
            profile.volatility_minimum <= _number(atr_regime) <= profile.volatility_maximum
        )
        required_confluences = profile.confluences
        required_momentum = profile.momentum
        required_gap = profile.direction_gap

        chosen = probabilities.get(direction.value, 0.0)
        opposite = probabilities.get(Direction.SELL.value if direction == Direction.BUY else Direction.BUY.value, 0.0)
        probability_floor = max(profile.probability_floor, break_even + profile.payout_margin)
        expected_value = chosen * payout / 100 - (1 - chosen)

        waiting: list[str] = []
        if score < threshold:
            waiting.append(f"Pontuação {score}/{threshold} para o modo {sensitivity_key.lower()}")
        if abs(buy_score - sell_score) < required_gap:
            waiting.append("Compra e venda ainda estão próximas; falta direção clara")
        if len(confluences) < required_confluences:
            waiting.append(f"Faltam confirmações: {len(confluences)}/{required_confluences}")
        if sum(momentum_votes) < required_momentum:
            waiting.append("Momentum e direção ainda não estão alinhados")
        if weak_regime:
            waiting.append(f"ADX {adx:.1f} indica tendência fraca para este perfil")
        if not volatility_ok:
            waiting.append("Volatilidade fora da faixa operacional")
        if overextended:
            waiting.append("Preço esticado; aguarde pullback ou reteste")
        if not profile.early_reading:
            against_higher = (
                direction == Direction.BUY and rules.higher_timeframe_bias == "BAIXA"
                or direction == Direction.SELL and rules.higher_timeframe_bias == "ALTA"
            )
            reversal_event = bool(
                professional.event and professional.event.direction == direction
                and professional.event.kind == "CHOCH"
            )
            if against_higher and not reversal_event:
                waiting.append("Direção contraria a tendência confirmada no timeframe superior")
            candle_delta = close_value - _number(last.get("open"), close_value)
            meaningful_candle = atr_value <= 0 or abs(candle_delta) >= atr_value * 0.03
            reversal_setup = "LIQUIDEZ" in setup_name or reversal_event
            if meaningful_candle and direction_sign * candle_delta < 0 and not reversal_setup:
                waiting.append("A última vela fechada não confirma a direção sugerida")
            independent = self._independent_confirmations(confluences)
            minimum_independent = 3 if profile.name == "CONSERVADOR" else 2
            if len(independent) < minimum_independent:
                waiting.append(
                    f"Confirmações independentes insuficientes: "
                    f"{len(independent)}/{minimum_independent}"
                )
        penalties = professional.buy_penalties if direction == Direction.BUY else professional.sell_penalties
        same_direction_event = bool(professional.event and professional.event.direction == direction)
        for reason in penalties:
            if (reason.startswith("Pullback identificado") and profile.early_reading
                    and professional.pullback is not None
                    and professional.pullback.direction == direction
                    and not professional.pullback.exhausted
                    and len(professional.pullback.confirmations) >= 2):
                continue
            if reason.startswith("Resistência muito próxima") or reason.startswith("Suporte muito próximo"):
                if same_direction_event:
                    continue
                room = professional.resistance_room_atr if direction == Direction.BUY else professional.support_room_atr
                if profile.early_reading and room is not None and room >= professional.policy.minimum_room_atr * 0.55:
                    continue
            if "Compressão lateral" in reason and profile.early_reading and professional.regime.efficiency >= 0.12:
                continue
            if "DIVERGÊNCIA" in reason and profile.early_reading and same_direction_event:
                continue
            if reason not in waiting:
                waiting.append(reason)
        if model_ready:
            if chosen < probability_floor:
                waiting.append(
                    f"IA indica {chosen * 100:.1f}%; mínimo {probability_floor * 100:.1f}% "
                    f"para payout de {payout}%"
                )
            if chosen - opposite < profile.probability_edge:
                waiting.append("A previsão ainda não tem vantagem suficiente sobre o lado oposto")

        kwargs = {
            "confluences": confluences[:8],
            "model_version": model_version,
            "setup_name": setup_name,
            "technical_score": technical_score,
            "model_score": round(chosen * 100) if model_ready else None,
            "payout_percent": payout,
            "break_even_rate": break_even,
            "expected_value": expected_value if model_ready else None,
            "market_regime": professional.regime.name,
            "structure_event": professional.event.label if professional.event else "",
            "pullback_state": professional.pullback.label if professional.pullback else "",
            "timeframe_context": professional.policy.timeframe,
        }
        if waiting:
            return Signal(Direction.WAIT, SignalState.WAITING, score, probabilities,
                          None, horizon_minutes, waiting_reasons=waiting[:4], **kwargs)
        state = SignalState.CONFIRMED if candle_closed else SignalState.FORMING
        return Signal(direction, state, score, probabilities, close_value,
                      horizon_minutes, **kwargs)
