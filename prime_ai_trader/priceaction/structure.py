from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..core.models import Zone


@dataclass(slots=True)
class MarketStructure:
    trend: str
    sequence: list[str]
    breakout: str | None
    retest: bool
    false_breakout: bool
    support_zones: list[Zone]
    resistance_zones: list[Zone]
    pivot_highs: list[int]
    pivot_lows: list[int]


def detect_pivots(frame: pd.DataFrame, left: int = 3, right: int = 3) -> tuple[list[int], list[int]]:
    highs, lows = [], []
    for index in range(left, max(left, len(frame) - right)):
        high_window = frame["high"].iloc[index - left:index + right + 1]
        low_window = frame["low"].iloc[index - left:index + right + 1]
        if frame["high"].iloc[index] == high_window.max() and (high_window == frame["high"].iloc[index]).sum() == 1:
            highs.append(index)
        if frame["low"].iloc[index] == low_window.min() and (low_window == frame["low"].iloc[index]).sum() == 1:
            lows.append(index)
    return highs, lows


def _cluster_levels(levels: list[tuple[float, int]], tolerance: float, kind: str) -> list[Zone]:
    clusters: list[list[tuple[float, int]]] = []
    for price, index in sorted(levels):
        if not clusters or abs(price - np.mean([p for p, _ in clusters[-1]])) > tolerance:
            clusters.append([(price, index)])
        else:
            clusters[-1].append((price, index))
    zones = []
    for cluster in clusters:
        prices = [item[0] for item in cluster]
        zones.append(Zone(kind, min(prices) - tolerance * 0.25, max(prices) + tolerance * 0.25, len(cluster), max(i for _, i in cluster)))
    return zones


def support_resistance_zones(frame: pd.DataFrame, atr_value: float | None = None, max_each: int = 4) -> tuple[list[Zone], list[Zone]]:
    if len(frame) < 9:
        return [], []
    pivot_highs, pivot_lows = detect_pivots(frame)
    current = float(frame["close"].iloc[-1])
    tolerance = max((atr_value or 0) * 0.45, current * 0.001)
    supports = _cluster_levels([(float(frame["low"].iloc[i]), i) for i in pivot_lows], tolerance, "SUPORTE")
    resistances = _cluster_levels([(float(frame["high"].iloc[i]), i) for i in pivot_highs], tolerance, "RESISTÊNCIA")
    supports = [z for z in supports if z.midpoint <= current * 1.002]
    resistances = [z for z in resistances if z.midpoint >= current * 0.998]
    supports.sort(key=lambda z: (abs(current - z.midpoint), -z.strength))
    resistances.sort(key=lambda z: (abs(current - z.midpoint), -z.strength))
    return supports[:max_each], resistances[:max_each]


def analyze_structure(frame: pd.DataFrame, atr_value: float | None = None) -> MarketStructure:
    if len(frame) < 9:
        return MarketStructure("INDEFINIDA", [], None, False, False, [], [], [], [])
    highs, lows = detect_pivots(frame)
    sequence = []
    if len(highs) >= 2:
        sequence.append("HH" if frame["high"].iloc[highs[-1]] > frame["high"].iloc[highs[-2]] else "LH")
    if len(lows) >= 2:
        sequence.append("HL" if frame["low"].iloc[lows[-1]] > frame["low"].iloc[lows[-2]] else "LL")
    trend = "ALTA" if set(sequence) == {"HH", "HL"} else "BAIXA" if set(sequence) == {"LH", "LL"} else "LATERAL"
    supports, resistances = support_resistance_zones(frame, atr_value)
    close = float(frame["close"].iloc[-1])
    previous = float(frame["close"].iloc[-2])
    breakout = None
    if resistances and previous <= resistances[0].high < close:
        breakout = "ROMPIMENTO DE ALTA"
    elif supports and previous >= supports[0].low > close:
        breakout = "ROMPIMENTO DE BAIXA"
    tolerance = max((atr_value or 0) * 0.25, close * 0.0005)
    retest = False
    if len(frame) >= 3:
        if resistances:
            retest |= abs(float(frame["low"].iloc[-1]) - resistances[0].midpoint) <= tolerance and close > resistances[0].midpoint
        if supports:
            retest |= abs(float(frame["high"].iloc[-1]) - supports[0].midpoint) <= tolerance and close < supports[0].midpoint
    false_breakout = False
    if resistances:
        false_breakout |= float(frame["high"].iloc[-1]) > resistances[0].high and close < resistances[0].high
    if supports:
        false_breakout |= float(frame["low"].iloc[-1]) < supports[0].low and close > supports[0].low
    return MarketStructure(trend, sequence, breakout, retest, false_breakout, supports, resistances, highs, lows)

