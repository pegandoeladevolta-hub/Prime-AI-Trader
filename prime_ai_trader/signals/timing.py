from __future__ import annotations

from datetime import datetime, timezone

from ..core.models import Direction, Signal, SignalState


def confirmed_entry_window_seconds(timeframe: str, horizon_minutes: int,
                                   sensitivity: str, mode: str) -> float:
    """Janela curta para o usuário enxergar e executar manualmente um sinal M1.

    A análise continua sendo feita somente depois do fechamento real da vela.
    A janela apenas evita que o primeiro tick da vela nova apague imediatamente
    um sinal que acabou de ser confirmado.
    """
    if (str(timeframe).lower() == "1m" and int(horizon_minutes) <= 1
            and str(sensitivity).upper() == "RÁPIDO"
            and str(mode).upper() == "CONFIRMAÇÃO"):
        return 8.0
    return 0.0


def preserve_recent_confirmed_signal(signal: Signal | None, *, candle_closed: bool,
                                     timeframe: str, horizon_minutes: int,
                                     sensitivity: str, mode: str,
                                     now: datetime | None = None) -> bool:
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
    return 0.0 <= age <= window


__all__ = ["confirmed_entry_window_seconds", "preserve_recent_confirmed_signal"]
