from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from ..core.models import Direction, Market, TIMEFRAME_MINUTES


@dataclass(frozen=True, slots=True)
class EntryReversalAssessment:
    """Evidências independentes e causais contra a entrada sugerida."""

    reasons: tuple[str, ...]
    immediate_horizon: bool

    @property
    def votes(self) -> int:
        return len(self.reasons)

    def blocks(self, sensitivity: str) -> bool:
        minimum = 2 if self.immediate_horizon or sensitivity == "CONSERVADOR" else 3
        return self.votes >= minimum


def _number(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def assess_entry_reversal(indicators: pd.DataFrame, features: pd.DataFrame,
                          direction: Direction, *, market: str,
                          timeframe: str, horizon_minutes: int,
                          candle_closed: bool) -> EntryReversalAssessment:
    """Detecta virada recente sem tratar indicadores atrasados como votos novos.

    Cada categoria entra uma única vez. Nada usa candles futuros, volume Forex
    inventado ou a vela aberta como confirmação de reversão.
    """
    minutes = TIMEFRAME_MINUTES.get(str(timeframe or ""), 5)
    immediate = int(horizon_minutes or minutes) <= max(minutes, 3)
    if direction == Direction.WAIT or not candle_closed or len(indicators) < 4:
        return EntryReversalAssessment((), immediate)

    last, previous, older = indicators.iloc[-1], indicators.iloc[-2], indicators.iloc[-3]
    feature = features.iloc[-1] if not features.empty else pd.Series(dtype=float)
    close = _number(last.get("close"))
    atr = max(_number(last.get("atr_14")), abs(close) * 1e-8, 1e-10)
    sign = 1.0 if direction == Direction.BUY else -1.0
    latest_move = sign * (close - _number(previous.get("close"), close)) / atr
    previous_move = sign * (
        _number(previous.get("close"), close) - _number(older.get("close"), close)
    ) / atr
    reasons: list[str] = []

    if latest_move <= -0.12 and (
        previous_move <= -0.08 or latest_move + previous_move <= -0.38
    ):
        reasons.append("Fechamentos recentes já caminham contra a entrada")

    macd_turn = sign * (
        _number(last.get("macd_hist")) - _number(previous.get("macd_hist"))
    ) / atr
    rsi_turn = sign * (
        _number(last.get("rsi_14"), 50.0) - _number(previous.get("rsi_14"), 50.0)
    )
    rsi_slope = sign * _number(feature.get("rsi_slope"))
    if macd_turn <= -0.012 and (rsi_turn <= -1.0 or rsi_slope <= -3.0):
        reasons.append("MACD e RSI perderam força na direção sugerida")

    close_position = _number(last.get("close_position"), 0.5)
    directional_close = close_position if direction == Direction.BUY else 1.0 - close_position
    wick = _number(last.get("upper_wick" if direction == Direction.BUY else "lower_wick")) / atr
    body = sign * (close - _number(last.get("open"), close)) / atr
    if wick >= 0.30 and directional_close <= 0.43 and body <= 0.18:
        reasons.append("Pavio contrário e fechamento fraco mostram rejeição")

    ema_9 = _number(last.get("ema_9"), close)
    previous_ema = _number(previous.get("ema_9"), ema_9)
    if (sign * (close - ema_9) / atr <= -0.16
            and sign * (ema_9 - previous_ema) <= 0
            and latest_move <= -0.08):
        reasons.append("Preço perdeu a EMA 9 e a média rápida já virou")

    reversal_pressure = sign * _number(feature.get("reversal_pressure"))
    if reversal_pressure <= -0.32 and latest_move <= -0.05:
        reasons.append("Divergência recente favorece o movimento oposto")

    if market == Market.CRYPTO.value:
        volume = _number(last.get("volume"))
        taker = _number(last.get("taker_buy_volume"))
        if volume > 0 and 0 < taker <= volume:
            imbalance = sign * (2.0 * taker / volume - 1.0)
            relative = _number(last.get("volume_relative"), 1.0)
            if imbalance <= -0.18 and relative >= 0.85 and (
                latest_move <= -0.06 or directional_close <= 0.46
            ):
                reasons.append("Fluxo real da Binance está dominado pelo lado contrário")

    return EntryReversalAssessment(tuple(reasons), immediate)


__all__ = ["EntryReversalAssessment", "assess_entry_reversal"]
