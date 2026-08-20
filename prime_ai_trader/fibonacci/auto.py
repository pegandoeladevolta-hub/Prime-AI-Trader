from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..priceaction.structure import detect_pivots


RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


@dataclass(slots=True)
class FibonacciResult:
    direction: str
    swing_low: float
    swing_high: float
    start_index: int
    end_index: int
    levels: dict[float, float]
    nearest_ratio: float
    nearest_price: float
    distance_pct: float


def automatic_fibonacci(frame: pd.DataFrame, lookback: int = 120) -> FibonacciResult | None:
    if len(frame) < 10:
        return None
    recent = frame.iloc[-lookback:]
    offset = len(frame) - len(recent)
    highs, lows = detect_pivots(recent, 2, 2)
    if not highs or not lows:
        high_i, low_i = int(recent["high"].to_numpy().argmax()), int(recent["low"].to_numpy().argmin())
    else:
        high_i, low_i = highs[-1], lows[-1]
        candidates = [(h, l) for h in highs[-5:] for l in lows[-5:] if abs(h - l) >= 3]
        if candidates:
            high_i, low_i = max(candidates, key=lambda pair: abs(float(recent["high"].iloc[pair[0]]) - float(recent["low"].iloc[pair[1]])))
    high, low = float(recent["high"].iloc[high_i]), float(recent["low"].iloc[low_i])
    if high <= low:
        return None
    direction = "IMPULSO DE ALTA" if low_i < high_i else "IMPULSO DE BAIXA"
    amplitude = high - low
    if direction == "IMPULSO DE ALTA":
        levels = {ratio: high - amplitude * ratio for ratio in RATIOS}
    else:
        levels = {ratio: low + amplitude * ratio for ratio in RATIOS}
    current = float(frame["close"].iloc[-1])
    nearest_ratio = min(levels, key=lambda ratio: abs(levels[ratio] - current))
    nearest = levels[nearest_ratio]
    return FibonacciResult(direction, low, high, offset + low_i, offset + high_i, levels, nearest_ratio, nearest, abs(current - nearest) / current * 100)

