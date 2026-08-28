from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from ..core.models import Direction
from .structure import MarketStructure


@dataclass(frozen=True, slots=True)
class MT5TradePlan:
    entry: float
    stop: float
    target: float
    risk: float
    reward: float
    rr: float
    minimum_rr: float
    stop_basis: str
    target_basis: str
    viable: bool


def _finite(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _atr(indicators: pd.DataFrame, entry: float) -> float:
    atr = _finite(indicators.iloc[-1].get("atr_14"))
    if atr > 0:
        return atr
    ranges = (indicators["high"] - indicators["low"]).tail(24)
    fallback = _finite(ranges.median())
    return fallback if fallback > 0 else max(abs(entry) * 0.001, 1e-9)


def _pivot_prices(indicators: pd.DataFrame, indexes: list[int], field: str) -> list[float]:
    values: list[float] = []
    for index in indexes[-8:]:
        if 0 <= index < len(indicators):
            value = _finite(indicators[field].iloc[index])
            if value > 0:
                values.append(value)
    return values


def stop_atr_multiplier(management_mode: str) -> float:
    return 1.10 if str(management_mode or "SCALP").upper() == "INTRADAY" else 0.78


def label_lookahead_bars(management_mode: str) -> int:
    # É somente a janela usada para rotular o histórico da IA/backtest. Não fecha
    # posições reais por tempo e não funciona como expiração.
    return 80 if str(management_mode or "SCALP").upper() == "INTRADAY" else 30


def calculate_mt5_trade_plan(
    indicators: pd.DataFrame,
    structure: MarketStructure,
    direction: Direction,
    *,
    management_mode: str = "SCALP",
    minimum_rr: float = 1.5,
) -> MT5TradePlan | None:
    """Cria Entrada/SL/TP para MT5 sem qualquer conceito de expiração.

    Primeiro localiza a invalidação estrutural. Depois projeta o alvo mínimo por R:R
    e verifica se suporte/resistência opostos deixam espaço para esse alvo. Quando
    uma barreira técnica aparece antes do R:R exigido, o plano é marcado inviável
    e o motor deve aguardar outra entrada em vez de alongar artificialmente o TP.
    """
    if indicators.empty or direction == Direction.WAIT:
        return None
    entry = _finite(indicators.iloc[-1].get("close"))
    if entry <= 0:
        return None
    atr = _atr(indicators, entry)
    minimum_rr = min(5.0, max(0.5, float(minimum_rr or 1.5)))
    base_stop = atr * stop_atr_multiplier(management_mode)
    structure_buffer = atr * 0.10
    opposing_buffer = atr * 0.06

    if direction == Direction.BUY:
        floors = [zone.low for zone in structure.support_zones if 0 < zone.low < entry]
        floors.extend(price for price in _pivot_prices(
            indicators, structure.pivot_lows, "low",
        ) if price < entry)
        nearest_floor = max(floors, default=0.0)
        structural_distance = entry - nearest_floor + structure_buffer if nearest_floor else 0.0
        if 0 < structural_distance <= atr * 2.8:
            risk = max(base_stop, structural_distance)
            stop_basis = "abaixo do suporte/pivô que invalida a compra"
        else:
            risk = base_stop
            stop_basis = "invalidação pela volatilidade ATR"
        stop = entry - risk
        desired_target = entry + risk * minimum_rr

        resistances = [zone.low for zone in structure.resistance_zones if zone.low > entry]
        resistance_cap = min(resistances, default=0.0) - opposing_buffer if resistances else 0.0
        if resistance_cap > entry:
            target = min(desired_target, resistance_cap)
            target_basis = (
                "antes da resistência relevante" if resistance_cap < desired_target
                else f"projeção mínima {minimum_rr:.2f}R"
            )
        else:
            target = desired_target
            target_basis = f"projeção mínima {minimum_rr:.2f}R sem resistência anterior"
        reward = max(0.0, target - entry)
    else:
        ceilings = [zone.high for zone in structure.resistance_zones if zone.high > entry]
        ceilings.extend(price for price in _pivot_prices(
            indicators, structure.pivot_highs, "high",
        ) if price > entry)
        nearest_ceiling = min(ceilings, default=0.0)
        structural_distance = nearest_ceiling - entry + structure_buffer if nearest_ceiling else 0.0
        if 0 < structural_distance <= atr * 2.8:
            risk = max(base_stop, structural_distance)
            stop_basis = "acima da resistência/pivô que invalida a venda"
        else:
            risk = base_stop
            stop_basis = "invalidação pela volatilidade ATR"
        stop = entry + risk
        desired_target = entry - risk * minimum_rr

        supports = [zone.high for zone in structure.support_zones if 0 < zone.high < entry]
        support_cap = max(supports, default=0.0) + opposing_buffer if supports else 0.0
        if 0 < support_cap < entry:
            target = max(desired_target, support_cap)
            target_basis = (
                "antes do suporte relevante" if support_cap > desired_target
                else f"projeção mínima {minimum_rr:.2f}R"
            )
        else:
            target = desired_target
            target_basis = f"projeção mínima {minimum_rr:.2f}R sem suporte anterior"
        reward = max(0.0, entry - target)

    risk = abs(entry - stop)
    rr = reward / risk if risk > 0 else 0.0
    return MT5TradePlan(
        entry=entry,
        stop=stop,
        target=target,
        risk=risk,
        reward=reward,
        rr=rr,
        minimum_rr=minimum_rr,
        stop_basis=stop_basis,
        target_basis=target_basis,
        viable=bool(risk > 0 and reward > 0 and rr + 1e-9 >= minimum_rr),
    )


__all__ = [
    "MT5TradePlan", "calculate_mt5_trade_plan", "label_lookahead_bars",
    "stop_atr_multiplier",
]
