from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from ..core.models import Direction, TIMEFRAME_MINUTES
from .structure import MarketStructure


@dataclass(frozen=True, slots=True)
class TechnicalLevels:
    """Referências técnicas para leitura; não representam ordens na plataforma."""

    entry: float
    invalidation: float
    target: float
    room_ratio: float
    invalidation_basis: str
    target_basis: str


def _finite(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _volatility(indicators: pd.DataFrame, entry: float) -> float:
    atr = _finite(indicators.iloc[-1].get("atr_14"))
    if atr > 0:
        return atr
    ranges = (indicators["high"] - indicators["low"]).tail(20)
    fallback = _finite(ranges.median())
    return fallback if fallback > 0 else max(abs(entry) * 0.001, 1e-9)


def _pivot_prices(indicators: pd.DataFrame, indexes: list[int], field: str) -> list[float]:
    result: list[float] = []
    for index in indexes[-6:]:
        if 0 <= index < len(indicators):
            value = _finite(indicators[field].iloc[index])
            if value > 0:
                result.append(value)
    return result


def calculate_technical_levels(indicators: pd.DataFrame, structure: MarketStructure,
                               direction: Direction, timeframe: str,
                               horizon_minutes: int) -> TechnicalLevels | None:
    """Calcula invalidação estrutural e alvo técnico simétricos para compra/venda.

    A projeção combina ATR, duração da expiração, pivôs e a zona oposta mais
    próxima. Em contratos de expiração fixa estes níveis servem para validar o
    espaço da entrada e ensinar a leitura; não encerram a operação.
    """
    if indicators.empty or direction == Direction.WAIT:
        return None
    entry = _finite(indicators.iloc[-1].get("close"))
    if entry <= 0:
        return None
    atr = _volatility(indicators, entry)
    timeframe_minutes = max(1, TIMEFRAME_MINUTES.get(timeframe, 1))
    horizon_bars = max(1.0, max(1, int(horizon_minutes)) / timeframe_minutes)
    root_horizon = math.sqrt(horizon_bars)
    base_stop = atr * min(1.30, 0.65 + root_horizon * 0.12)
    projected_room = atr * min(2.40, max(0.72, root_horizon * 0.72))
    structure_buffer = atr * 0.12
    opposing_buffer = atr * 0.08

    if direction == Direction.BUY:
        structural = [zone.low for zone in structure.support_zones if zone.low < entry]
        structural.extend(price for price in _pivot_prices(
            indicators, structure.pivot_lows, "low",
        ) if price < entry)
        nearest_floor = max(structural, default=0.0)
        structural_distance = entry - nearest_floor + structure_buffer if nearest_floor else 0.0
        if 0 < structural_distance <= atr * 2.25:
            stop_distance = max(base_stop, structural_distance)
            stop_basis = "abaixo do suporte/pivô confirmado"
        else:
            stop_distance = base_stop
            stop_basis = "proteção pela volatilidade ATR"
        invalidation = entry - stop_distance

        target_distance = max(projected_room, stop_distance)
        opposing = [zone.low for zone in structure.resistance_zones if zone.low > entry]
        resistance_cap = min(opposing, default=0.0) - opposing_buffer if opposing else 0.0
        if resistance_cap > entry:
            target_distance = min(target_distance, resistance_cap - entry)
            target_basis = "antes da resistência relevante"
        else:
            target_basis = "projeção de volatilidade ATR"
        target = entry + max(target_distance, atr * 0.05)
    else:
        structural = [zone.high for zone in structure.resistance_zones if zone.high > entry]
        structural.extend(price for price in _pivot_prices(
            indicators, structure.pivot_highs, "high",
        ) if price > entry)
        nearest_ceiling = min(structural, default=0.0)
        structural_distance = nearest_ceiling - entry + structure_buffer if nearest_ceiling else 0.0
        if 0 < structural_distance <= atr * 2.25:
            stop_distance = max(base_stop, structural_distance)
            stop_basis = "acima da resistência/pivô confirmado"
        else:
            stop_distance = base_stop
            stop_basis = "proteção pela volatilidade ATR"
        invalidation = entry + stop_distance

        target_distance = max(projected_room, stop_distance)
        opposing = [zone.high for zone in structure.support_zones if zone.high < entry]
        support_cap = max(opposing, default=0.0) + opposing_buffer if opposing else 0.0
        if 0 < support_cap < entry:
            target_distance = min(target_distance, entry - support_cap)
            target_basis = "antes do suporte relevante"
        else:
            target_basis = "projeção de volatilidade ATR"
        target = entry - max(target_distance, atr * 0.05)

    room = abs(target - entry)
    risk = abs(entry - invalidation)
    return TechnicalLevels(
        entry=entry,
        invalidation=invalidation,
        target=target,
        room_ratio=room / risk if risk > 0 else 0.0,
        invalidation_basis=stop_basis,
        target_basis=target_basis,
    )
