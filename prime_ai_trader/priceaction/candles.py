from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from ..core.models import Direction


@dataclass(frozen=True, slots=True)
class CandlestickPattern:
    """Padrão OHLC causal reconhecido na última vela disponível."""

    name: str
    direction: Direction
    family: str
    strength: float
    bars: int
    confirmed: bool
    description: str

    @property
    def label(self) -> str:
        suffix = "CONFIRMADO" if self.confirmed else "EM FORMAÇÃO"
        return f"{self.name} • {suffix}"


@dataclass(frozen=True, slots=True)
class CandlestickAssessment:
    patterns: tuple[CandlestickPattern, ...]
    bullish_pressure: float
    bearish_pressure: float
    indecision: float
    exhaustion_direction: Direction
    exhaustion_strength: float
    current_closed: bool

    def directional_strength(self, direction: Direction) -> float:
        if not self.current_closed or self.indecision >= 0.76:
            return 0.0
        return max(
            (item.strength for item in self.patterns
             if item.direction == direction and item.family != "RISCO" and item.confirmed),
            default=0.0,
        )

    def strongest(self, direction: Direction) -> CandlestickPattern | None:
        if self.indecision >= 0.76:
            return None
        values = [
            item for item in self.patterns
            if item.direction == direction and item.family != "RISCO"
        ]
        return max(values, key=lambda item: item.strength, default=None)

    @property
    def primary(self) -> CandlestickPattern | None:
        values = [item for item in self.patterns if item.family != "RISCO"]
        return max(values, key=lambda item: item.strength, default=None)

    @property
    def labels(self) -> list[str]:
        return [item.label for item in self.patterns]


def _number(value, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _empty_assessment(current_closed: bool) -> CandlestickAssessment:
    return CandlestickAssessment((), 0.0, 0.0, 0.0, Direction.WAIT, 0.0, current_closed)


def candlestick_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Features vetorizadas de candle usando somente a vela atual e o passado.

    Os valores são normalizados pelo range/ATR, portanto o mesmo detector serve
    para 1m, 3m, 5m, 15m, 30m, 1h e 4h sem limiares absolutos de preço.
    """
    columns = [
        "candlestick_bias", "candlestick_reversal", "candlestick_indecision",
        "candlestick_exhaustion", "engulfing_code", "pinbar_code",
        "three_candle_code",
    ]
    if frame.empty or not {"open", "high", "low", "close"}.issubset(frame.columns):
        return pd.DataFrame(0.0, index=frame.index, columns=columns)

    opened = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    candle_range = (high - low).replace(0, np.nan)
    body = (close - opened).abs()
    body_ratio = body / candle_range
    upper = high - pd.concat([opened, close], axis=1).max(axis=1)
    lower = pd.concat([opened, close], axis=1).min(axis=1) - low
    upper_ratio = upper / candle_range
    lower_ratio = lower / candle_range
    close_position = (close - low) / candle_range
    bullish = close > opened
    bearish = close < opened

    previous_open = opened.shift(1)
    previous_close = close.shift(1)
    previous_body = body.shift(1)
    previous_range = candle_range.shift(1)
    previous_body_ratio = body_ratio.shift(1)
    previous_bullish = bullish.shift(1, fill_value=False)
    previous_bearish = bearish.shift(1, fill_value=False)

    bullish_engulfing = (
        previous_bearish & bullish & (opened <= previous_close)
        & (close >= previous_open) & (body >= previous_body * 1.02)
    )
    bearish_engulfing = (
        previous_bullish & bearish & (opened >= previous_close)
        & (close <= previous_open) & (body >= previous_body * 1.02)
    )
    engulfing = np.select([bullish_engulfing, bearish_engulfing], [1.0, -1.0], default=0.0)

    bullish_pin = (
        (lower_ratio >= 0.48) & (lower >= body * 1.8)
        & (upper_ratio <= 0.24) & (close_position >= 0.60)
    )
    bearish_pin = (
        (upper_ratio >= 0.48) & (upper >= body * 1.8)
        & (lower_ratio <= 0.24) & (close_position <= 0.40)
    )
    pinbar = np.select([bullish_pin, bearish_pin], [1.0, -1.0], default=0.0)

    previous_midpoint = (previous_open + previous_close) / 2
    bullish_piercing = (
        previous_bearish & bullish & (previous_body_ratio >= 0.48)
        & (close > previous_midpoint) & (close < previous_open)
    )
    bearish_cloud = (
        previous_bullish & bearish & (previous_body_ratio >= 0.48)
        & (close < previous_midpoint) & (close > previous_open)
    )
    two_bar_reversal = np.select([bullish_piercing, bearish_cloud], [0.72, -0.72], default=0.0)

    first_open, first_close = opened.shift(2), close.shift(2)
    first_body_ratio = body_ratio.shift(2)
    middle_body_ratio = body_ratio.shift(1)
    morning_star = (
        (first_close < first_open) & (first_body_ratio >= 0.48)
        & (middle_body_ratio <= 0.36) & bullish
        & (body_ratio >= 0.42) & (close >= (first_open + first_close) / 2)
    )
    evening_star = (
        (first_close > first_open) & (first_body_ratio >= 0.48)
        & (middle_body_ratio <= 0.36) & bearish
        & (body_ratio >= 0.42) & (close <= (first_open + first_close) / 2)
    )
    three_bullish = bullish & bullish.shift(1, fill_value=False) & bullish.shift(2, fill_value=False)
    three_bearish = bearish & bearish.shift(1, fill_value=False) & bearish.shift(2, fill_value=False)
    soldiers = (
        three_bullish & (close > close.shift(1)) & (close.shift(1) > close.shift(2))
        & (body_ratio.rolling(3, min_periods=3).min() >= 0.48)
    )
    crows = (
        three_bearish & (close < close.shift(1)) & (close.shift(1) < close.shift(2))
        & (body_ratio.rolling(3, min_periods=3).min() >= 0.48)
    )
    three_code = np.select(
        [morning_star, evening_star, soldiers, crows],
        [1.0, -1.0, 0.82, -0.82], default=0.0,
    )

    doji = (body_ratio <= 0.10) & ~(bullish_pin | bearish_pin)
    spinning = (body_ratio <= 0.30) & (upper_ratio >= 0.25) & (lower_ratio >= 0.25)
    inside = (high < high.shift(1)) & (low > low.shift(1))
    indecision = np.select([doji, spinning, inside], [1.0, 0.72, 0.58], default=0.0)

    raw_pressure = (2 * close_position - 1) * body_ratio
    reversal = pd.Series(two_bar_reversal, index=frame.index)
    reversal = reversal.where(abs(reversal) >= abs(pd.Series(engulfing, index=frame.index)) * 0.88,
                              pd.Series(engulfing, index=frame.index) * 0.88)
    star_reversal = np.select([morning_star, evening_star], [0.96, -0.96], default=0.0)
    reversal = reversal.where(abs(reversal) >= abs(star_reversal), star_reversal)
    reversal = reversal.where(abs(reversal) >= abs(pd.Series(pinbar, index=frame.index)) * 0.72,
                              pd.Series(pinbar, index=frame.index) * 0.72)

    directional_patterns = pd.concat([
        raw_pressure.rename("pressure"),
        pd.Series(engulfing, index=frame.index).rename("engulfing"),
        pd.Series(pinbar, index=frame.index).mul(0.78).rename("pinbar"),
        pd.Series(three_code, index=frame.index).rename("three"),
        pd.Series(two_bar_reversal, index=frame.index).rename("two"),
    ], axis=1)
    strongest_index = directional_patterns.abs().idxmax(axis=1)
    bias = pd.Series(
        [directional_patterns.loc[index, column] for index, column in strongest_index.items()],
        index=frame.index, dtype=float,
    ).clip(-1.0, 1.0)

    atr = frame.get("atr_14", candle_range.rolling(14, min_periods=2).mean())
    atr = pd.Series(atr, index=frame.index, dtype=float).replace(0, np.nan)
    three_move = (close - close.shift(3)) / atr
    shrinking = body < body.shift(1) * 0.82
    opposite_wick = np.where(three_move > 0, upper_ratio, lower_ratio)
    stretched = three_move.abs() >= 1.35
    exhaustion = np.select(
        [three_bullish & stretched & (shrinking | (opposite_wick >= 0.32)),
         three_bearish & stretched & (shrinking | (opposite_wick >= 0.32))],
        [np.minimum(1.0, three_move.abs() / 2.2), -np.minimum(1.0, three_move.abs() / 2.2)],
        default=0.0,
    )

    return pd.DataFrame({
        "candlestick_bias": bias,
        "candlestick_reversal": reversal.clip(-1.0, 1.0),
        "candlestick_indecision": indecision,
        "candlestick_exhaustion": exhaustion,
        "engulfing_code": engulfing,
        "pinbar_code": pinbar,
        "three_candle_code": three_code,
    }, index=frame.index).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def analyze_candlestick_patterns(frame: pd.DataFrame, *, current_closed: bool = True,
                                 timeframe: str | None = None) -> CandlestickAssessment:
    """Reconhece padrões da última vela, sem consultar qualquer vela futura."""
    if len(frame) < 3 or not {"open", "high", "low", "close"}.issubset(frame.columns):
        return _empty_assessment(current_closed)
    data = frame.tail(8)
    features = candlestick_feature_frame(data)
    last = data.iloc[-1]
    previous = data.iloc[-2]
    third = data.iloc[-3]
    row = features.iloc[-1]
    patterns: list[CandlestickPattern] = []

    opened, high, low, close = (_number(last.get(name)) for name in ("open", "high", "low", "close"))
    candle_range = max(high - low, abs(close) * 1e-10, 1e-10)
    body = abs(close - opened)
    body_ratio = body / candle_range
    upper = high - max(opened, close)
    lower = min(opened, close) - low
    upper_ratio, lower_ratio = upper / candle_range, lower / candle_range
    close_position = (close - low) / candle_range
    atr = max(_number(last.get("atr_14")), candle_range * 0.5, abs(close) * 1e-10)
    range_strength = min(1.0, candle_range / max(atr, 1e-10))
    frame_name = str(timeframe or "").strip() or "timeframe atual"

    def add(name: str, direction: Direction, family: str, strength: float,
            bars: int, description: str) -> None:
        key = (name, direction)
        if any((item.name, item.direction) == key for item in patterns):
            return
        patterns.append(CandlestickPattern(
            name, direction, family, round(min(max(strength, 0.0), 1.0), 4),
            bars, current_closed, description,
        ))

    bullish_pin_shape = (
        lower_ratio >= 0.48 and lower >= body * 1.8
        and upper_ratio <= 0.24 and close_position >= 0.60
    )
    bearish_pin_shape = (
        upper_ratio >= 0.48 and upper >= body * 1.8
        and lower_ratio <= 0.24 and close_position <= 0.40
    )
    if body_ratio <= 0.10 and not (bullish_pin_shape or bearish_pin_shape):
        add("DOJI", Direction.WAIT, "INDECISÃO", 0.78, 1,
            f"Abertura e fechamento quase iguais no {frame_name}")
    elif body_ratio <= 0.30 and upper_ratio >= 0.25 and lower_ratio >= 0.25:
        add("SPINNING TOP", Direction.WAIT, "INDECISÃO", 0.66, 1,
            "Corpo pequeno com rejeição dos dois lados")

    if bullish_pin_shape:
        add("MARTELO / PIN BAR COMPRADOR", Direction.BUY, "REJEIÇÃO",
            0.72 + range_strength * 0.12, 1, "Pavio inferior rejeitou preços mais baixos")
    if bearish_pin_shape:
        add("ESTRELA CADENTE / PIN BAR VENDEDOR", Direction.SELL, "REJEIÇÃO",
            0.72 + range_strength * 0.12, 1, "Pavio superior rejeitou preços mais altos")
    if body_ratio >= 0.78 and upper_ratio <= 0.13 and lower_ratio <= 0.13 and range_strength >= 0.55:
        direction = Direction.BUY if close > opened else Direction.SELL
        add("MARUBOZU COMPRADOR" if direction == Direction.BUY else "MARUBOZU VENDEDOR",
            direction, "IMPULSO", 0.74 + range_strength * 0.12, 1,
            "Corpo dominante fechou próximo da extremidade")

    previous_open, previous_close = _number(previous.get("open")), _number(previous.get("close"))
    previous_body = abs(previous_close - previous_open)
    previous_range = max(_number(previous.get("high")) - _number(previous.get("low")), 1e-10)
    if previous_close < previous_open and close > opened and opened <= previous_close and close >= previous_open and body >= previous_body * 1.02:
        add("ENGOLFO COMPRADOR", Direction.BUY, "REVERSÃO", 0.90, 2,
            "O corpo comprador engoliu o corpo vendedor anterior")
    if previous_close > previous_open and close < opened and opened >= previous_close and close <= previous_open and body >= previous_body * 1.02:
        add("ENGOLFO VENDEDOR", Direction.SELL, "REVERSÃO", 0.90, 2,
            "O corpo vendedor engoliu o corpo comprador anterior")

    previous_midpoint = (previous_open + previous_close) / 2
    if previous_close < previous_open and previous_body / previous_range >= 0.48 and close > opened and previous_midpoint < close < previous_open:
        add("LINHA DE PERFURAÇÃO", Direction.BUY, "REVERSÃO", 0.73, 2,
            "Vela compradora recuperou mais da metade do corpo vendedor")
    if previous_close > previous_open and previous_body / previous_range >= 0.48 and close < opened and previous_open < close < previous_midpoint:
        add("NUVEM NEGRA", Direction.SELL, "REVERSÃO", 0.73, 2,
            "Vela vendedora devolveu mais da metade do corpo comprador")

    current_body_low, current_body_high = min(opened, close), max(opened, close)
    previous_body_low, previous_body_high = min(previous_open, previous_close), max(previous_open, previous_close)
    if body <= previous_body * 0.62 and current_body_low >= previous_body_low and current_body_high <= previous_body_high:
        if close > opened and previous_close < previous_open:
            add("HARAMI COMPRADOR", Direction.BUY, "REVERSÃO", 0.62, 2,
                "Corpo comprador pequeno ficou contido na vela vendedora")
        elif close < opened and previous_close > previous_open:
            add("HARAMI VENDEDOR", Direction.SELL, "REVERSÃO", 0.62, 2,
                "Corpo vendedor pequeno ficou contido na vela compradora")

    previous_high, previous_low = _number(previous.get("high")), _number(previous.get("low"))
    if high < previous_high and low > previous_low:
        add("INSIDE BAR", Direction.WAIT, "INDECISÃO", 0.58, 2,
            "Vela atual permaneceu dentro do range anterior")
    if high > previous_high and low < previous_low and body_ratio >= 0.42:
        direction = Direction.BUY if close_position >= 0.62 else Direction.SELL if close_position <= 0.38 else Direction.WAIT
        if direction != Direction.WAIT:
            add("OUTSIDE BAR COMPRADOR" if direction == Direction.BUY else "OUTSIDE BAR VENDEDOR",
                direction, "EXPANSÃO", 0.68, 2, "Expansão do range com fechamento direcional")

    tolerance = max(atr * 0.08, candle_range * 0.10, previous_range * 0.10)
    if abs(low - previous_low) <= tolerance and previous_close < previous_open and close > opened:
        add("TWEEZER BOTTOM", Direction.BUY, "REVERSÃO", 0.68, 2,
            "Duas velas rejeitaram a mesma região inferior")
    if abs(high - previous_high) <= tolerance and previous_close > previous_open and close < opened:
        add("TWEEZER TOP", Direction.SELL, "REVERSÃO", 0.68, 2,
            "Duas velas rejeitaram a mesma região superior")

    third_open, third_close = _number(third.get("open")), _number(third.get("close"))
    third_range = max(_number(third.get("high")) - _number(third.get("low")), 1e-10)
    third_body_ratio = abs(third_close - third_open) / third_range
    middle_body_ratio = previous_body / previous_range
    if third_close < third_open and third_body_ratio >= 0.48 and middle_body_ratio <= 0.36 and close > opened and body_ratio >= 0.42 and close >= (third_open + third_close) / 2:
        add("ESTRELA DA MANHÃ", Direction.BUY, "REVERSÃO", 0.94, 3,
            "Sequência de três velas confirmou reversão compradora")
    if third_close > third_open and third_body_ratio >= 0.48 and middle_body_ratio <= 0.36 and close < opened and body_ratio >= 0.42 and close <= (third_open + third_close) / 2:
        add("ESTRELA DA TARDE", Direction.SELL, "REVERSÃO", 0.94, 3,
            "Sequência de três velas confirmou reversão vendedora")

    recent = data.iloc[-3:]
    recent_open = recent["open"].astype(float)
    recent_close = recent["close"].astype(float)
    recent_range = (recent["high"].astype(float) - recent["low"].astype(float)).replace(0, np.nan)
    recent_body_ratio = (recent_close - recent_open).abs() / recent_range
    three_bullish = bool((recent_close > recent_open).all() and recent_close.is_monotonic_increasing)
    three_bearish = bool((recent_close < recent_open).all() and recent_close.is_monotonic_decreasing)
    if three_bullish and float(recent_body_ratio.min()) >= 0.48:
        add("TRÊS SOLDADOS BRANCOS", Direction.BUY, "CONTINUAÇÃO", 0.84, 3,
            "Três corpos compradores avançaram com fechamento progressivo")
    if three_bearish and float(recent_body_ratio.min()) >= 0.48:
        add("TRÊS CORVOS NEGROS", Direction.SELL, "CONTINUAÇÃO", 0.84, 3,
            "Três corpos vendedores recuaram com fechamento progressivo")

    exhaustion_value = _number(row.get("candlestick_exhaustion"))
    exhaustion_direction = Direction.BUY if exhaustion_value > 0 else Direction.SELL if exhaustion_value < 0 else Direction.WAIT
    exhaustion_strength = abs(exhaustion_value)
    if exhaustion_direction != Direction.WAIT:
        label = "EXAUSTÃO APÓS SEQUÊNCIA COMPRADORA" if exhaustion_direction == Direction.BUY else "EXAUSTÃO APÓS SEQUÊNCIA VENDEDORA"
        add(label, Direction.WAIT, "RISCO", max(0.64, exhaustion_strength), 3,
            "Movimento esticado perdeu qualidade no fechamento")

    patterns.sort(key=lambda item: item.strength, reverse=True)
    pressure = _number(row.get("candlestick_bias"))
    bullish_pressure = max(0.0, pressure)
    bearish_pressure = max(0.0, -pressure)
    return CandlestickAssessment(
        tuple(patterns[:6]), round(bullish_pressure, 4), round(bearish_pressure, 4),
        round(_number(row.get("candlestick_indecision")), 4), exhaustion_direction,
        round(exhaustion_strength, 4), current_closed,
    )


__all__ = [
    "CandlestickPattern", "CandlestickAssessment", "analyze_candlestick_patterns",
    "candlestick_feature_frame",
]
