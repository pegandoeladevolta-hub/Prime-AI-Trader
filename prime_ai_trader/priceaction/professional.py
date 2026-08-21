from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from ..core.models import Direction, TIMEFRAME_MINUTES
from ..fibonacci.auto import FibonacciResult
from .structure import MarketStructure


@dataclass(frozen=True, slots=True)
class TimeframePolicy:
    timeframe: str
    minutes: int
    pullback_bars: int
    structure_bars: int
    minimum_displacement_atr: float
    minimum_room_atr: float
    live_refresh_seconds: float


@dataclass(frozen=True, slots=True)
class MarketRegime:
    name: str
    direction: Direction
    efficiency: float
    compression_ratio: float
    extension_atr: float
    exhausted: bool
    transition: bool


@dataclass(frozen=True, slots=True)
class StructureEvent:
    kind: str
    direction: Direction
    level: float
    displacement_atr: float
    confirmed: bool

    @property
    def label(self) -> str:
        side = "ALTA" if self.direction == Direction.BUY else "BAIXA"
        name = "MUDANÇA DE TENDÊNCIA" if self.kind == "CHOCH" else "ROMPIMENTO DE ESTRUTURA"
        return f"{name} {self.kind} • {side}"


@dataclass(frozen=True, slots=True)
class PullbackSignal:
    direction: Direction
    retracement: float
    depth_atr: float
    zone: str
    confirmed: bool
    exhausted: bool
    confirmations: tuple[str, ...]

    @property
    def label(self) -> str:
        side = "COMPRADOR" if self.direction == Direction.BUY else "VENDEDOR"
        suffix = "CONFIRMADO" if self.confirmed else "EM FORMAÇÃO"
        return f"PULLBACK {side} {suffix} • {self.zone}"


@dataclass(frozen=True, slots=True)
class MomentumDivergence:
    direction: Direction
    oscillator: str
    hidden: bool
    strength: float

    @property
    def label(self) -> str:
        kind = "OCULTA" if self.hidden else "REGULAR"
        side = "ALTA" if self.direction == Direction.BUY else "BAIXA"
        return f"DIVERGÊNCIA {kind} DE {side} • {self.oscillator}"


@dataclass(frozen=True, slots=True)
class ProfessionalAssessment:
    policy: TimeframePolicy
    regime: MarketRegime
    event: StructureEvent | None
    pullback: PullbackSignal | None
    divergences: tuple[MomentumDivergence, ...]
    buy_reasons: tuple[str, ...]
    sell_reasons: tuple[str, ...]
    buy_penalties: tuple[str, ...]
    sell_penalties: tuple[str, ...]
    buy_setup: str | None
    sell_setup: str | None
    support_room_atr: float | None
    resistance_room_atr: float | None


def _number(value, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def timeframe_policy(timeframe: str | None, indicators: pd.DataFrame | None = None) -> TimeframePolicy:
    selected = str(timeframe or "").strip()
    if selected not in TIMEFRAME_MINUTES and indicators is not None and len(indicators) >= 3:
        if isinstance(indicators.index, pd.DatetimeIndex):
            spacing = indicators.index.to_series().diff().dropna().tail(30).median()
            if pd.notna(spacing):
                minutes = max(1, round(spacing.total_seconds() / 60))
                selected = next((name for name, value in TIMEFRAME_MINUTES.items() if value == minutes), "5m")
    if selected not in TIMEFRAME_MINUTES:
        selected = "5m"
    minutes = TIMEFRAME_MINUTES[selected]
    if minutes <= 3:
        pullback, structure, displacement, room, refresh = 7, 32, 0.12, 0.26, 5.0
    elif minutes <= 15:
        pullback, structure, displacement, room, refresh = 9, 42, 0.16, 0.32, 8.0
    elif minutes <= 60:
        pullback, structure, displacement, room, refresh = 11, 54, 0.19, 0.37, 12.0
    else:
        pullback, structure, displacement, room, refresh = 13, 72, 0.22, 0.42, 18.0
    return TimeframePolicy(selected, minutes, pullback, structure, displacement, room, refresh)


def live_refresh_interval(timeframe: str, sensitivity: str) -> float:
    policy = timeframe_policy(timeframe)
    factor = {"RÁPIDO": 0.72, "EQUILIBRADO": 1.0, "CONSERVADOR": 1.35}.get(str(sensitivity).upper(), 1.0)
    return max(3.0, min(30.0, round(policy.live_refresh_seconds * factor, 1)))


def detect_market_regime(indicators: pd.DataFrame) -> MarketRegime:
    if len(indicators) < 20:
        return MarketRegime("HISTÓRICO EM FORMAÇÃO", Direction.WAIT, 0.0, 1.0, 0.0, False, False)
    last = indicators.iloc[-1]
    close = _number(last.get("close"))
    atr = max(_number(last.get("atr_14")), abs(close) * 1e-8, 1e-10)
    ema_9 = _number(last.get("ema_9"), close)
    ema_21 = _number(last.get("ema_21"), close)
    ema_50 = _number(last.get("ema_50"), close)
    adx = _number(last.get("adx_14"))
    closes = indicators["close"].tail(16).astype(float)
    distance = abs(float(closes.iloc[-1] - closes.iloc[0]))
    travelled = float(closes.diff().abs().sum())
    efficiency = distance / travelled if travelled > 0 else 0.0
    widths = (indicators["bb_upper"] - indicators["bb_lower"]) if {"bb_upper", "bb_lower"}.issubset(indicators.columns) else pd.Series(dtype=float)
    width = _number(widths.iloc[-1]) if len(widths) else 0.0
    historical_width = _number(widths.tail(65).median(), width) if len(widths) else width
    compression = width / historical_width if width > 0 and historical_width > 0 else 1.0
    extension = (close - ema_21) / atr
    rsi = _number(last.get("rsi_14"), 50.0)
    macd = _number(last.get("macd_hist"))
    previous_macd = _number(indicators.iloc[-2].get("macd_hist"), macd)
    bullish = ema_9 > ema_21 > ema_50
    bearish = ema_9 < ema_21 < ema_50
    exhausted_buy = extension > 2.25 and rsi > 71 and macd < previous_macd
    exhausted_sell = extension < -2.25 and rsi < 29 and macd > previous_macd
    exhausted = exhausted_buy or exhausted_sell
    transition = not (bullish or bearish) and adx >= 15 and abs(ema_9 - ema_21) <= atr * 0.35
    if exhausted:
        name = "EXAUSTÃO COMPRADORA" if exhausted_buy else "EXAUSTÃO VENDEDORA"
        direction = Direction.BUY if exhausted_buy else Direction.SELL
    elif compression < 0.64 and efficiency < 0.36:
        name, direction = "COMPRESSÃO / LATERALIZAÇÃO", Direction.WAIT
    elif bullish and adx >= 14:
        name, direction = "TENDÊNCIA DE ALTA", Direction.BUY
    elif bearish and adx >= 14:
        name, direction = "TENDÊNCIA DE BAIXA", Direction.SELL
    elif transition:
        name, direction = "TRANSIÇÃO DE TENDÊNCIA", Direction.WAIT
    elif efficiency < 0.20 and adx < 19:
        name, direction = "MERCADO LATERAL", Direction.WAIT
    elif close >= ema_21:
        name, direction = "PRESSÃO COMPRADORA", Direction.BUY
    else:
        name, direction = "PRESSÃO VENDEDORA", Direction.SELL
    return MarketRegime(name, direction, round(efficiency, 4), round(compression, 4),
                        round(extension, 4), exhausted, transition)


def _prior_bias(indicators: pd.DataFrame, structure: MarketStructure) -> Direction:
    if structure.trend == "ALTA":
        return Direction.BUY
    if structure.trend == "BAIXA":
        return Direction.SELL
    position = max(0, len(indicators) - 5)
    row = indicators.iloc[position]
    fast, slow = _number(row.get("ema_9")), _number(row.get("ema_21"))
    if fast > slow:
        return Direction.BUY
    if fast < slow:
        return Direction.SELL
    return Direction.WAIT


def detect_structure_event(indicators: pd.DataFrame, structure: MarketStructure,
                           policy: TimeframePolicy) -> StructureEvent | None:
    if len(indicators) < 12:
        return None
    last, previous = indicators.iloc[-1], indicators.iloc[-2]
    close, prev_close = _number(last.get("close")), _number(previous.get("close"))
    atr = max(_number(last.get("atr_14")), abs(close) * 1e-8, 1e-10)
    position = _number(last.get("close_position"), 0.5)
    bias = _prior_bias(indicators, structure)
    highs = [index for index in structure.pivot_highs if len(indicators) - policy.structure_bars <= index <= len(indicators) - 3]
    lows = [index for index in structure.pivot_lows if len(indicators) - policy.structure_bars <= index <= len(indicators) - 3]
    if highs:
        level = float(indicators["high"].iloc[highs[-1]])
        displacement = (close - level) / atr
        if prev_close <= level + atr * 0.05 and displacement >= policy.minimum_displacement_atr and position >= 0.54:
            kind = "CHOCH" if bias == Direction.SELL else "BOS"
            return StructureEvent(kind, Direction.BUY, level, round(displacement, 4), True)
    if lows:
        level = float(indicators["low"].iloc[lows[-1]])
        displacement = (level - close) / atr
        if prev_close >= level - atr * 0.05 and displacement >= policy.minimum_displacement_atr and position <= 0.46:
            kind = "CHOCH" if bias == Direction.BUY else "BOS"
            return StructureEvent(kind, Direction.SELL, level, round(displacement, 4), True)
    return None


def _pullback_direction(indicators: pd.DataFrame, structure: MarketStructure) -> Direction:
    last = indicators.iloc[-1]
    ema_9, ema_21, ema_50 = (_number(last.get(name)) for name in ("ema_9", "ema_21", "ema_50"))
    if ema_9 >= ema_21 and ema_21 > ema_50 and structure.trend != "BAIXA":
        return Direction.BUY
    if ema_9 <= ema_21 and ema_21 < ema_50 and structure.trend != "ALTA":
        return Direction.SELL
    return Direction.WAIT


def detect_pullback(indicators: pd.DataFrame, structure: MarketStructure,
                    fib: FibonacciResult | None, policy: TimeframePolicy) -> PullbackSignal | None:
    if len(indicators) < 25:
        return None
    direction = _pullback_direction(indicators, structure)
    if direction == Direction.WAIT:
        return None
    last, previous = indicators.iloc[-1], indicators.iloc[-2]
    close, opened = _number(last.get("close")), _number(last.get("open"))
    atr = max(_number(last.get("atr_14")), abs(close) * 1e-8, 1e-10)
    ema_9, ema_21, ema_50 = (_number(last.get(name), close) for name in ("ema_9", "ema_21", "ema_50"))
    recent = indicators.iloc[-policy.pullback_bars:]
    earlier = indicators.iloc[-max(policy.pullback_bars * 3, 22):-policy.pullback_bars + 1]
    if len(earlier) < 4:
        return None
    reasons: list[str] = []
    zone = "EMA 21"
    if direction == Direction.BUY:
        swing_high = float(indicators["high"].iloc[-max(policy.pullback_bars * 2, 12):-1].max())
        swing_low = float(earlier["low"].min())
        correction = float(recent["low"].min())
        amplitude = swing_high - swing_low
        retracement = (swing_high - correction) / amplitude if amplitude > 0 else 0.0
        depth = (swing_high - correction) / atr
        touched = correction <= ema_21 + atr * 0.42 and correction >= ema_50 - atr * 0.78
        resumed = close > opened and close >= ema_21 - atr * 0.10
        rejection = _number(last.get("lower_wick")) >= max(_number(last.get("body")) * 0.55, atr * 0.10)
        momentum = _number(last.get("macd_hist")) >= _number(previous.get("macd_hist")) or _number(last.get("rsi_14")) >= _number(previous.get("rsi_14"))
        bearish_correction = bool((recent["close"].iloc[:-1] < recent["open"].iloc[:-1]).any())
        support_hit = any(abs(correction - item.midpoint) <= atr * 0.55 for item in structure.support_zones)
        invalidated = correction < ema_50 - atr * 0.95 or close < ema_50 - atr * 0.30
    else:
        swing_low = float(indicators["low"].iloc[-max(policy.pullback_bars * 2, 12):-1].min())
        swing_high = float(earlier["high"].max())
        correction = float(recent["high"].max())
        amplitude = swing_high - swing_low
        retracement = (correction - swing_low) / amplitude if amplitude > 0 else 0.0
        depth = (correction - swing_low) / atr
        touched = correction >= ema_21 - atr * 0.42 and correction <= ema_50 + atr * 0.78
        resumed = close < opened and close <= ema_21 + atr * 0.10
        rejection = _number(last.get("upper_wick")) >= max(_number(last.get("body")) * 0.55, atr * 0.10)
        momentum = _number(last.get("macd_hist")) <= _number(previous.get("macd_hist")) or _number(last.get("rsi_14")) <= _number(previous.get("rsi_14"))
        bearish_correction = bool((recent["close"].iloc[:-1] > recent["open"].iloc[:-1]).any())
        support_hit = any(abs(correction - item.midpoint) <= atr * 0.55 for item in structure.resistance_zones)
        invalidated = correction > ema_50 + atr * 0.95 or close > ema_50 + atr * 0.30
    if not touched or not bearish_correction or amplitude <= atr * 0.45 or not 0.12 <= retracement <= 0.92:
        return None
    reasons.append(f"Retração saudável de {retracement * 100:.0f}% após impulso")
    if support_hit:
        zone = "EMA 21 + ZONA ESTRUTURAL"
        reasons.append("Zona estrutural coincide com a média dinâmica")
    if fib and fib.nearest_ratio in {0.382, 0.5, 0.618, 0.786} and fib.distance_pct <= 0.40:
        zone = f"EMA 21 + FIBONACCI {fib.nearest_ratio * 100:.1f}%"
        reasons.append("Retração Fibonacci confirma a área de interesse")
    if resumed:
        reasons.append("Vela de retomada confirmou o sentido da tendência")
    if rejection:
        reasons.append("Pavio de rejeição protege a região do pullback")
    if momentum:
        reasons.append("Momentum volta a favorecer a direção principal")
    confirmations = int(resumed) + int(rejection) + int(momentum) + int(support_hit)
    confirmed = resumed and confirmations >= 2 and not invalidated
    return PullbackSignal(direction, round(retracement, 4), round(depth, 4), zone,
                          confirmed, invalidated or retracement > 0.82, tuple(reasons))


def _divergences_for_pivots(indicators: pd.DataFrame, indices: list[int],
                            kind: str) -> list[MomentumDivergence]:
    if len(indices) < 2:
        return []
    previous, latest = indices[-2], indices[-1]
    if latest <= previous or len(indicators) - 1 - latest > 12:
        return []
    atr = max(_number(indicators.iloc[-1].get("atr_14")), 1e-10)
    column = "low" if kind == "low" else "high"
    first_price, second_price = float(indicators[column].iloc[previous]), float(indicators[column].iloc[latest])
    if abs(second_price - first_price) < atr * 0.08:
        return []
    found: list[MomentumDivergence] = []
    for oscillator, minimum in (("rsi_14", 2.0), ("macd_hist", atr * 0.015)):
        if oscillator not in indicators.columns:
            continue
        first = _number(indicators[oscillator].iloc[previous], math.nan)
        second = _number(indicators[oscillator].iloc[latest], math.nan)
        if not math.isfinite(first) or not math.isfinite(second) or abs(second - first) < minimum:
            continue
        if kind == "low" and second_price < first_price and second > first:
            direction, hidden = Direction.BUY, False
        elif kind == "low" and second_price > first_price and second < first:
            direction, hidden = Direction.BUY, True
        elif kind == "high" and second_price > first_price and second < first:
            direction, hidden = Direction.SELL, False
        elif kind == "high" and second_price < first_price and second > first:
            direction, hidden = Direction.SELL, True
        else:
            continue
        label = "RSI" if oscillator == "rsi_14" else "MACD"
        strength = min(1.0, abs(second - first) / max(minimum * 4, 1e-10))
        found.append(MomentumDivergence(direction, label, hidden, round(strength, 4)))
    return found


def detect_momentum_divergences(indicators: pd.DataFrame,
                                structure: MarketStructure) -> tuple[MomentumDivergence, ...]:
    values = _divergences_for_pivots(indicators, structure.pivot_lows, "low")
    values.extend(_divergences_for_pivots(indicators, structure.pivot_highs, "high"))
    return tuple(sorted(values, key=lambda item: item.strength, reverse=True)[:4])


def _opposing_room(indicators: pd.DataFrame, structure: MarketStructure) -> tuple[float | None, float | None]:
    last = indicators.iloc[-1]
    close, atr = _number(last.get("close")), max(_number(last.get("atr_14")), 1e-10)
    supports = [zone.midpoint for zone in structure.support_zones if zone.midpoint < close - atr * 0.04]
    resistances = [zone.midpoint for zone in structure.resistance_zones if zone.midpoint > close + atr * 0.04]
    below = (close - max(supports)) / atr if supports else None
    above = (min(resistances) - close) / atr if resistances else None
    return below, above


def _liquidity_rejection(indicators: pd.DataFrame, structure: MarketStructure) -> Direction:
    if len(indicators) < 3:
        return Direction.WAIT
    last = indicators.iloc[-1]
    close, low, high = (_number(last.get(key)) for key in ("close", "low", "high"))
    opened = _number(last.get("open"))
    body = max(_number(last.get("body"), abs(close - opened)), 1e-10)
    atr = max(_number(last.get("atr_14")), 1e-10)
    lower, upper = _number(last.get("lower_wick")), _number(last.get("upper_wick"))
    for zone in structure.support_zones:
        if low < zone.low and close > zone.midpoint and lower >= max(body * 0.8, atr * 0.12):
            return Direction.BUY
    for zone in structure.resistance_zones:
        if high > zone.high and close < zone.midpoint and upper >= max(body * 0.8, atr * 0.12):
            return Direction.SELL
    return Direction.WAIT


def assess_professional_market(indicators: pd.DataFrame, structure: MarketStructure,
                               fib: FibonacciResult | None = None,
                               timeframe: str | None = None) -> ProfessionalAssessment:
    policy = timeframe_policy(timeframe, indicators)
    regime = detect_market_regime(indicators)
    if indicators.empty:
        return ProfessionalAssessment(policy, regime, None, None, (), (), (), (), (), None, None, None, None)
    event = detect_structure_event(indicators, structure, policy)
    pullback = detect_pullback(indicators, structure, fib, policy)
    divergences = detect_momentum_divergences(indicators, structure)
    support_room, resistance_room = _opposing_room(indicators, structure)
    buy_reasons: list[str] = []
    sell_reasons: list[str] = []
    buy_penalties: list[str] = []
    sell_penalties: list[str] = []
    buy_setup = sell_setup = None
    if event:
        target = buy_reasons if event.direction == Direction.BUY else sell_reasons
        target.append(f"{event.label} confirmada com {event.displacement_atr:.2f} ATR")
        if event.direction == Direction.BUY:
            buy_setup = event.label
        else:
            sell_setup = event.label
        opposite = sell_penalties if event.direction == Direction.BUY else buy_penalties
        opposite.append(f"Estrutura acabou de confirmar {event.label.lower()}")
    if pullback:
        target = buy_reasons if pullback.direction == Direction.BUY else sell_reasons
        target.append(pullback.label)
        target.extend(pullback.confirmations[:3])
        if pullback.confirmed:
            if pullback.direction == Direction.BUY:
                buy_setup = pullback.label
            else:
                sell_setup = pullback.label
        elif not pullback.exhausted:
            penalties = buy_penalties if pullback.direction == Direction.BUY else sell_penalties
            penalties.append("Pullback identificado, mas a retomada ainda não foi confirmada")
        if pullback.exhausted:
            penalties = buy_penalties if pullback.direction == Direction.BUY else sell_penalties
            penalties.append("Retração profunda descaracteriza o pullback de continuação")
    for divergence in divergences:
        target = buy_reasons if divergence.direction == Direction.BUY else sell_reasons
        target.append(divergence.label)
        if not divergence.hidden and divergence.strength >= 0.70:
            opposite = sell_penalties if divergence.direction == Direction.BUY else buy_penalties
            opposite.append(f"{divergence.label} sinaliza perda de força no movimento atual")
    rejection = _liquidity_rejection(indicators, structure)
    if rejection != Direction.WAIT:
        target = buy_reasons if rejection == Direction.BUY else sell_reasons
        target.append("Varredura de liquidez com rejeição estrutural confirmada")
        if rejection == Direction.BUY:
            buy_setup = buy_setup or "LIQUIDEZ + REVERSÃO CONFIRMADA"
        else:
            sell_setup = sell_setup or "LIQUIDEZ + REVERSÃO CONFIRMADA"
    if regime.exhausted:
        target = buy_penalties if regime.direction == Direction.BUY else sell_penalties
        target.append(f"{regime.name}; aguarde pullback ou reversão confirmada")
    if resistance_room is not None and resistance_room < policy.minimum_room_atr:
        buy_penalties.append(f"Resistência muito próxima: {resistance_room:.2f} ATR de espaço")
    if support_room is not None and support_room < policy.minimum_room_atr:
        sell_penalties.append(f"Suporte muito próximo: {support_room:.2f} ATR de espaço")
    if regime.name == "COMPRESSÃO / LATERALIZAÇÃO" and event is None and rejection == Direction.WAIT:
        message = "Compressão lateral sem rompimento ou rejeição confirmada"
        buy_penalties.append(message)
        sell_penalties.append(message)
    return ProfessionalAssessment(policy, regime, event, pullback, divergences,
                                  tuple(dict.fromkeys(buy_reasons)), tuple(dict.fromkeys(sell_reasons)),
                                  tuple(dict.fromkeys(buy_penalties)), tuple(dict.fromkeys(sell_penalties)),
                                  buy_setup, sell_setup, support_room, resistance_room)
