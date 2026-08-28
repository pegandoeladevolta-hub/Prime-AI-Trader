from __future__ import annotations

import math

import pandas as pd

from ..core.models import Candle
from ..priceaction.mt5_levels import label_lookahead_bars, stop_atr_multiplier


def _finite(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def build_mt5_barrier_labels(
    candles: list[Candle],
    indicators: pd.DataFrame,
    *,
    minimum_rr: float = 1.5,
    management_mode: str = "SCALP",
) -> pd.Series:
    """Rotula o histórico pelo primeiro resultado realista TP/SL.

    +1: uma compra teria alcançado o TP antes do SL.
    -1: uma venda teria alcançado o TP antes do SL.
     0: nenhum lado alcançou alvo antes da invalidação na janela de avaliação.

    A janela existe só para construir amostras finitas para IA/backtest; não é uma
    expiração e nunca manda fechar uma posição real do MT5 por tempo.
    """
    if not candles or indicators.empty:
        return pd.Series(dtype=float)
    frame = indicators.copy()
    count = min(len(candles), len(frame))
    candles = candles[-count:]
    frame = frame.iloc[-count:]
    lookahead = label_lookahead_bars(management_mode)
    rr = min(5.0, max(0.5, float(minimum_rr or 1.5)))
    stop_factor = stop_atr_multiplier(management_mode)
    labels = pd.Series(index=frame.index, dtype=float)

    for index in range(count):
        if index + 1 >= count:
            labels.iloc[index] = float("nan")
            continue
        entry = _finite(frame["close"].iloc[index])
        atr = _finite(frame["atr_14"].iloc[index]) if "atr_14" in frame else 0.0
        if entry <= 0 or atr <= 0:
            labels.iloc[index] = float("nan")
            continue
        risk = atr * stop_factor
        buy_stop = entry - risk
        buy_target = entry + risk * rr
        sell_stop = entry + risk
        sell_target = entry - risk * rr
        buy_outcome: tuple[str, int] | None = None
        sell_outcome: tuple[str, int] | None = None
        final = min(count, index + 1 + lookahead)

        for future in range(index + 1, final):
            candle = candles[future]
            high = float(candle.high)
            low = float(candle.low)
            if buy_outcome is None:
                hit_tp = high >= buy_target
                hit_sl = low <= buy_stop
                if hit_tp and hit_sl:
                    buy_outcome = ("LOSS", future)
                elif hit_sl:
                    buy_outcome = ("LOSS", future)
                elif hit_tp:
                    buy_outcome = ("WIN", future)
            if sell_outcome is None:
                hit_tp = low <= sell_target
                hit_sl = high >= sell_stop
                if hit_tp and hit_sl:
                    sell_outcome = ("LOSS", future)
                elif hit_sl:
                    sell_outcome = ("LOSS", future)
                elif hit_tp:
                    sell_outcome = ("WIN", future)
            if buy_outcome is not None and sell_outcome is not None:
                break

        buy_win = buy_outcome is not None and buy_outcome[0] == "WIN"
        sell_win = sell_outcome is not None and sell_outcome[0] == "WIN"
        if buy_win and sell_win:
            if buy_outcome[1] < sell_outcome[1]:
                labels.iloc[index] = 1.0
            elif sell_outcome[1] < buy_outcome[1]:
                labels.iloc[index] = -1.0
            else:
                labels.iloc[index] = 0.0
        elif buy_win:
            labels.iloc[index] = 1.0
        elif sell_win:
            labels.iloc[index] = -1.0
        else:
            labels.iloc[index] = 0.0

    # Os últimos candles não possuem futuro completo suficiente para uma avaliação
    # comparável e são removidos do conjunto supervisionado.
    if lookahead > 0:
        labels.iloc[-min(lookahead, len(labels)):] = float("nan")
    return labels


__all__ = ["build_mt5_barrier_labels"]
