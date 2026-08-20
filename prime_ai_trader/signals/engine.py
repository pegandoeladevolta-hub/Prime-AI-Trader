from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..core.models import Direction, Signal, SignalState
from ..fibonacci.auto import FibonacciResult
from ..ml.models import ModelManager
from ..priceaction.structure import MarketStructure


# Perfil estável da v0.3.0. Mantém seleção suficiente para o backtest formar
# uma amostra útil, sem abandonar a confirmação de tendência e probabilidade.
THRESHOLDS = {"CONSERVADOR": 84, "EQUILIBRADO": 76, "RÁPIDO": 68}
PROBABILITY_FLOORS = {"CONSERVADOR": 0.68, "EQUILIBRADO": 0.62, "RÁPIDO": 0.56}
PROBABILITY_EDGES = {"CONSERVADOR": 0.16, "EQUILIBRADO": 0.14, "RÁPIDO": 0.12}


@dataclass(slots=True)
class RuleAssessment:
    buy_points: int
    sell_points: int
    buy_reasons: list[str]
    sell_reasons: list[str]


class SignalEngine:
    def __init__(self, model_manager: ModelManager) -> None:
        self.model_manager = model_manager

    @staticmethod
    def assess_rules(indicators: pd.DataFrame, structure: MarketStructure, fib: FibonacciResult | None) -> RuleAssessment:
        last = indicators.iloc[-1]
        buy, sell, buy_reasons, sell_reasons = 0, 0, [], []
        if last["ema_9"] > last["ema_21"] > last["ema_50"]:
            buy += 16; buy_reasons.append("EMAs 9/21/50 alinhadas para alta")
        elif last["ema_9"] < last["ema_21"] < last["ema_50"]:
            sell += 16; sell_reasons.append("EMAs 9/21/50 alinhadas para baixa")
        if 52 <= last["rsi_14"] <= 68:
            buy += 8; buy_reasons.append(f"RSI construtivo ({last['rsi_14']:.1f})")
        elif 32 <= last["rsi_14"] <= 48:
            sell += 8; sell_reasons.append(f"RSI enfraquecido ({last['rsi_14']:.1f})")
        if last["macd_hist"] > 0:
            buy += 6; buy_reasons.append("MACD acima da linha de sinal")
            if len(indicators) >= 2 and last["macd_hist"] > indicators["macd_hist"].iloc[-2]:
                buy += 4; buy_reasons.append("Momentum comprador acelerando")
        elif last["macd_hist"] < 0:
            sell += 6; sell_reasons.append("MACD abaixo da linha de sinal")
            if len(indicators) >= 2 and last["macd_hist"] < indicators["macd_hist"].iloc[-2]:
                sell += 4; sell_reasons.append("Momentum vendedor acelerando")
        if pd.notna(last["adx_14"]) and last["adx_14"] >= 22:
            if last["plus_di"] > last["minus_di"]:
                buy += 12; buy_reasons.append(f"ADX confirma força compradora ({last['adx_14']:.1f})")
            else:
                sell += 12; sell_reasons.append(f"ADX confirma força vendedora ({last['adx_14']:.1f})")
        if pd.notna(last["vwap"]):
            if last["close"] > last["vwap"]:
                buy += 7; buy_reasons.append("Preço acima da VWAP")
            else:
                sell += 7; sell_reasons.append("Preço abaixo da VWAP")
        if pd.notna(last["volume_relative"]) and last["volume_relative"] >= 1.2:
            if last["close"] >= last["open"]:
                buy += 8; buy_reasons.append(f"Volume relativo {last['volume_relative']:.2f}x")
            else:
                sell += 8; sell_reasons.append(f"Volume relativo {last['volume_relative']:.2f}x")
        if structure.trend == "ALTA":
            buy += 15; buy_reasons.append("Estrutura HH/HL")
        elif structure.trend == "BAIXA":
            sell += 15; sell_reasons.append("Estrutura LH/LL")
        if structure.breakout == "ROMPIMENTO DE ALTA":
            buy += 12; buy_reasons.append("Rompimento de resistência")
        elif structure.breakout == "ROMPIMENTO DE BAIXA":
            sell += 12; sell_reasons.append("Rompimento de suporte")
        if structure.retest and structure.trend == "ALTA":
            buy += 7; buy_reasons.append("Reteste confirmado na tendência de alta")
        elif structure.retest and structure.trend == "BAIXA":
            sell += 7; sell_reasons.append("Reteste confirmado na tendência de baixa")
        if structure.false_breakout:
            buy = max(0, buy - 8); sell = max(0, sell - 8)
        if fib and fib.distance_pct <= 0.35 and fib.nearest_ratio in {0.5, 0.618, 0.786}:
            if fib.direction == "IMPULSO DE ALTA":
                buy += 7; buy_reasons.append(f"Confluência Fibonacci {fib.nearest_ratio * 100:.1f}%")
            else:
                sell += 7; sell_reasons.append(f"Confluência Fibonacci {fib.nearest_ratio * 100:.1f}%")
        return RuleAssessment(min(buy, 100), min(sell, 100), buy_reasons, sell_reasons)

    def generate(self, indicators: pd.DataFrame, features: pd.DataFrame, structure: MarketStructure,
                 fib: FibonacciResult | None, horizon_minutes: int, sensitivity: str,
                 candle_closed: bool, blockers: list[str] | None = None, mode: str = "CONFIRMAÇÃO",
                 model_context: dict[str, str | int] | None = None) -> Signal:
        blockers = blockers or []
        if blockers:
            return Signal(Direction.WAIT, SignalState.BLOCKED, 0, {"COMPRA": 0, "VENDA": 0, "AGUARDAR": 1}, None, horizon_minutes, blockers=blockers)
        rules = self.assess_rules(indicators, structure, fib)
        probabilities = {"COMPRA": 0.0, "VENDA": 0.0, "AGUARDAR": 0.0}
        model_ready = self.model_manager.is_compatible(model_context)
        if model_ready:
            raw = self.model_manager.predict_proba(features)
            probabilities = {"COMPRA": raw.get(1, 0.0), "VENDA": raw.get(-1, 0.0), "AGUARDAR": raw.get(0, 0.0)}
            model_weight = {"PRICE ACTION": 0.40, "CONFIRMAÇÃO": 0.65, "QUANTITATIVO": 0.80}.get(mode, 0.65)
            rule_weight = 1 - model_weight
            buy_score = round(100 * (model_weight * probabilities["COMPRA"] + rule_weight * rules.buy_points / 100))
            sell_score = round(100 * (model_weight * probabilities["VENDA"] + rule_weight * rules.sell_points / 100))
            model_version = self.model_manager.report.version
        else:
            buy_score, sell_score = rules.buy_points, rules.sell_points
            total = max(buy_score + sell_score + 30, 1)
            probabilities = {"COMPRA": buy_score / total, "VENDA": sell_score / total, "AGUARDAR": 30 / total}
            model_version = "rules-v1"
        sensitivity_key = sensitivity.upper()
        threshold = THRESHOLDS.get(sensitivity_key, 76)
        if buy_score >= sell_score:
            direction, score, confluences = Direction.BUY, buy_score, rules.buy_reasons
        else:
            direction, score, confluences = Direction.SELL, sell_score, rules.sell_reasons
        last = indicators.iloc[-1]
        score_gap = abs(buy_score - sell_score)
        direction_sign = 1 if direction == Direction.BUY else -1
        momentum_votes = (
            direction_sign * float(last.get("ema_9", 0) - last.get("ema_21", 0)) > 0,
            direction_sign * float(last.get("macd_hist", 0) or 0) > 0,
            direction_sign * float((last.get("plus_di", 0) or 0) - (last.get("minus_di", 0) or 0)) > 0,
            structure.trend != ("BAIXA" if direction == Direction.BUY else "ALTA"),
        )
        weak_regime = pd.notna(last.get("adx_14")) and float(last["adx_14"]) < 18 and not structure.breakout
        atr_value = float(last.get("atr_14")) if pd.notna(last.get("atr_14")) else 0.0
        close_value = float(last.get("close"))
        ema_21 = float(last.get("ema_21")) if pd.notna(last.get("ema_21")) else close_value
        overextended = atr_value > 0 and abs(close_value - ema_21) > 2.2 * atr_value
        feature_row = features.iloc[-1] if not features.empty else pd.Series(dtype=float)
        atr_regime_value = feature_row.get("atr_regime")
        # Somente regimes realmente extremos são rejeitados. A faixa anterior
        # era estreita demais e reduzia o backtest a poucas operações.
        volatility_ok = pd.isna(atr_regime_value) or 0.40 <= float(atr_regime_value) <= 3.00
        probability_ok = True
        if model_ready:
            chosen = probabilities[direction.value]
            opposite = probabilities[Direction.SELL.value if direction == Direction.BUY else Direction.BUY.value]
            probability_ok = (
                chosen >= PROBABILITY_FLOORS.get(sensitivity_key, 0.64)
                and chosen - opposite >= PROBABILITY_EDGES.get(sensitivity_key, 0.16)
            )
        required_confluences = 4
        required_momentum = 3
        if (
            score < threshold or score_gap < 12 or len(confluences) < required_confluences
            or sum(momentum_votes) < required_momentum or weak_regime or not probability_ok
            or not volatility_ok or overextended
        ):
            return Signal(Direction.WAIT, SignalState.WAITING, max(buy_score, sell_score), probabilities, None, horizon_minutes, confluences[:4], model_version=model_version)
        state = SignalState.CONFIRMED if candle_closed else SignalState.FORMING
        entry = float(indicators["close"].iloc[-1])
        return Signal(direction, state, score, probabilities, entry, horizon_minutes, confluences[:6], model_version=model_version)
