from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DailyLimitStatus:
    blocked: bool
    net_profit: float
    operations: int
    profit_target: float
    stop_loss: float
    reason: str = ""


def _local_date(value: str) -> object | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.date()
    return parsed.astimezone().date()


def evaluate_daily_limits(journal, *, profit_target: float, stop_loss: float,
                          now: datetime | None = None) -> DailyLimitStatus:
    """Avalia somente P/L realizado das operações do Prime Trader no dia local.

    O resultado flutuante de uma posição ainda aberta não encerra a sessão antes
    do TP/SL. Assim a trava é aplicada entre operações: quando um trade fecha e o
    P/L líquido realizado do dia alcança a meta ou o stop, nenhuma nova ordem é
    permitida. No próximo dia local o acumulado reinicia naturalmente.
    """
    current = now.astimezone() if now is not None and now.tzinfo else (
        now if now is not None else datetime.now().astimezone()
    )
    day = current.date()
    target = max(0.0, float(profit_target or 0.0))
    stop = max(0.0, float(stop_loss or 0.0))

    rows = journal.recent(100000)
    today = [
        row for row in rows
        if row.get("status") == "ENCERRADA"
        and row.get("closed_at")
        and _local_date(str(row.get("closed_at"))) == day
    ]
    net = sum(float(row.get("net_profit") or 0.0) for row in today)

    if target > 0 and net >= target:
        return DailyLimitStatus(
            True, net, len(today), target, stop,
            f"META DIÁRIA ATINGIDA • resultado do dia {net:+.2f} • meta {target:.2f}",
        )
    if stop > 0 and net <= -stop:
        return DailyLimitStatus(
            True, net, len(today), target, stop,
            f"STOP DIÁRIO ATINGIDO • resultado do dia {net:+.2f} • limite -{stop:.2f}",
        )
    return DailyLimitStatus(False, net, len(today), target, stop, "")


__all__ = ["DailyLimitStatus", "evaluate_daily_limits"]
