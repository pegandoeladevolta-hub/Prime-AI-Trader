from __future__ import annotations

from dataclasses import dataclass


MT5_HISTORY_EPOCH = "prime-trader-mt5-sltp-2026-08-27-v2"


@dataclass(frozen=True, slots=True)
class HistoryResetResult:
    reset: bool
    deleted_signals: int = 0
    deleted_decisions: int = 0


def initialize_mt5_history_epoch(repository) -> HistoryResetResult:
    """Apaga uma única vez históricos incompatíveis com a etapa MT5-SLTP.

    O banco continua sendo o mesmo para preservar configurações e estrutura, mas
    signals/decision_history começam do zero nesta lógica de Entrada + Stop + Alvo.
    Um marcador persistente impede que os novos sinais sejam apagados nas próximas
    aberturas. O histórico oficial da conta no MetaTrader/corretora não é alterado.
    """
    with repository.connect() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key='mt5_history_epoch'"
        ).fetchone()
        current = str(row["value"]) if row is not None else ""
        if current == MT5_HISTORY_EPOCH:
            return HistoryResetResult(False)

        signal_count = int(connection.execute("SELECT COUNT(*) FROM signals").fetchone()[0])
        decision_count = int(
            connection.execute("SELECT COUNT(*) FROM decision_history").fetchone()[0]
        )
        connection.execute("DELETE FROM decision_history")
        connection.execute("DELETE FROM signals")
        try:
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('signals','decision_history')"
            )
        except Exception:
            pass
        connection.execute(
            """INSERT INTO app_metadata(key, value) VALUES('mt5_history_epoch', ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (MT5_HISTORY_EPOCH,),
        )
        return HistoryResetResult(True, signal_count, decision_count)


__all__ = ["HistoryResetResult", "MT5_HISTORY_EPOCH", "initialize_mt5_history_epoch"]
