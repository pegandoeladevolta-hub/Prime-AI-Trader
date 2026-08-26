from __future__ import annotations

from datetime import datetime, timezone
import math
from collections.abc import Sequence

from ..core.models import Candle, Direction, Signal, SignalState


def confirmed_entry_window_seconds(timeframe: str, horizon_minutes: int,
                                   sensitivity: str, mode: str) -> float:
    """Janela curta para o usuário enxergar e executar manualmente um sinal.

    A análise continua sendo feita somente depois do fechamento real da vela.
    A janela apenas evita que o primeiro tick da vela nova apague imediatamente
    um sinal que acabou de ser confirmado. Vale para todos os modos/perfis.
    """
    try:
        horizon_seconds = max(1, int(horizon_minutes)) * 60
    except (TypeError, ValueError):
        return 0.0
    timeframe_key = str(timeframe or "").lower()
    if timeframe_key not in {"1m", "3m", "5m", "15m", "30m", "1h", "4h"}:
        return 0.0
    base = 8.0 if timeframe_key == "1m" else 10.0 if timeframe_key in {"3m", "5m"} else 12.0
    return min(base, horizon_seconds * 0.15)


def use_last_closed_candle_for_entry(candles: Sequence[Candle], *, timeframe: str,
                                     horizon_minutes: int, sensitivity: str,
                                     mode: str, now: datetime | None = None) -> bool:
    """Confirma pela última vela fechada somente no início da vela seguinte."""
    if len(candles) < 2 or candles[-1].closed or not candles[-2].closed:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    opened = candles[-1].open_time
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    age = (current.astimezone(timezone.utc) - opened.astimezone(timezone.utc)).total_seconds()
    window = confirmed_entry_window_seconds(
        timeframe, horizon_minutes, sensitivity, mode,
    )
    return 0.0 <= age <= window


def effective_platform_entry_remaining_seconds(
    remaining_seconds: float | None, signal: Signal | None, *,
    timeframe: str, horizon_minutes: int, sensitivity: str, mode: str,
    platform_horizon_minutes: int | None = None,
    now: datetime | None = None,
) -> tuple[float | None, bool]:
    """Projeta o contador antigo para o ciclo seguinte após confirmação fechada.

    A projeção só existe durante a janela curta de um sinal novo confirmado pela
    vela anterior. Leituras comuns nos segundos finais continuam bloqueadas.
    """
    if remaining_seconds is None:
        return None, False
    try:
        remaining = float(remaining_seconds)
    except (TypeError, ValueError):
        return None, False
    if not math.isfinite(remaining):
        return remaining, False
    if (signal is None or signal.state != SignalState.CONFIRMED
            or signal.direction == Direction.WAIT or not signal.confirmed_candle
            or not signal.next_candle_entry):
        return remaining, False
    window = confirmed_entry_window_seconds(
        timeframe, horizon_minutes, sensitivity, mode,
    )
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    created = signal.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (current.astimezone(timezone.utc) - created.astimezone(timezone.utc)).total_seconds()
    minimum = min(window, 8.0)
    if window <= 0 or not 0.0 <= age <= window or remaining > minimum or remaining < -window:
        return remaining, False
    try:
        cycle_minutes = max(1, int(platform_horizon_minutes or horizon_minutes))
    except (TypeError, ValueError):
        cycle_minutes = max(1, int(horizon_minutes))
    cycle_seconds = cycle_minutes * 60.0
    projected = remaining
    while projected <= minimum:
        projected += cycle_seconds
    return projected, True


def preserve_recent_confirmed_signal(signal: Signal | None, *, candle_closed: bool,
                                     timeframe: str, horizon_minutes: int,
                                     sensitivity: str, mode: str,
                                     now: datetime | None = None,
                                     current_price: float | None = None,
                                     atr_value: float | None = None,
                                     platform_remaining_seconds: float | None = None) -> bool:
    if candle_closed or signal is None:
        return False
    if signal.state != SignalState.CONFIRMED or signal.direction == Direction.WAIT:
        return False
    window = confirmed_entry_window_seconds(
        timeframe, horizon_minutes, sensitivity, mode,
    )
    if window <= 0:
        return False
    current = now or datetime.now(timezone.utc)
    created = signal.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (current.astimezone(timezone.utc) - created.astimezone(timezone.utc)).total_seconds()
    if not 0.0 <= age <= window:
        return False
    if platform_remaining_seconds is not None:
        remaining, _ = effective_platform_entry_remaining_seconds(
            platform_remaining_seconds, signal,
            timeframe=timeframe, horizon_minutes=horizon_minutes,
            sensitivity=sensitivity, mode=mode, now=current,
        )
        if remaining is not None and math.isfinite(remaining) and remaining <= min(window, 8.0):
            return False
    if current_price is not None and signal.entry is not None:
        try:
            price = float(current_price)
            entry = float(signal.entry)
            atr = float(atr_value or 0.0)
        except (TypeError, ValueError):
            price = entry = atr = math.nan
        if math.isfinite(price) and math.isfinite(entry) and price > 0 and entry > 0:
            sign = 1.0 if signal.direction == Direction.BUY else -1.0
            adverse_move = sign * (price - entry)
            threshold = max(atr * 0.18 if math.isfinite(atr) else 0.0,
                            entry * 0.000001)
            if adverse_move <= -threshold:
                return False
            if signal.technical_stop is not None:
                try:
                    stop = float(signal.technical_stop)
                except (TypeError, ValueError):
                    stop = math.nan
                if math.isfinite(stop) and sign * (price - stop) <= 0:
                    return False
    return True


__all__ = [
    "confirmed_entry_window_seconds", "effective_platform_entry_remaining_seconds",
    "preserve_recent_confirmed_signal", "use_last_closed_candle_for_entry",
]
