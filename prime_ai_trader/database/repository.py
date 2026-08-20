from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..config.settings import app_data_dir
from ..core.models import Signal


SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    horizon_minutes INTEGER NOT NULL,
    direction TEXT NOT NULL,
    state TEXT NOT NULL,
    score INTEGER NOT NULL,
    entry REAL,
    exit REAL,
    result TEXT,
    probabilities_json TEXT NOT NULL,
    indicators_json TEXT NOT NULL,
    confluences_json TEXT NOT NULL,
    model_version TEXT NOT NULL,
    mode TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol, timeframe);
"""


class Repository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "prime_ai_trader.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def save_signal(self, signal: Signal, market: str, symbol: str, timeframe: str,
                    indicators: dict, mode: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO signals(created_at, market, symbol, timeframe, horizon_minutes, direction, state,
                score, entry, probabilities_json, indicators_json, confluences_json, model_version, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (signal.created_at.isoformat(), market, symbol, timeframe, signal.horizon_minutes,
                 signal.direction.value, signal.state.value, signal.score, signal.entry,
                 json.dumps(signal.probabilities), json.dumps(indicators), json.dumps(signal.confluences, ensure_ascii=False),
                 signal.model_version, mode),
            )
            return int(cursor.lastrowid)

    def set_result(self, signal_id: int, exit_price: float, result: str) -> None:
        if result not in {"WIN", "LOSS", "DRAW"}:
            raise ValueError("Resultado inválido.")
        with self.connect() as connection:
            connection.execute("UPDATE signals SET exit=?, result=? WHERE id=?", (exit_price, result, signal_id))

    def pending(self, symbol: str, timeframe: str) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM signals WHERE result IS NULL AND symbol=? AND timeframe=? ORDER BY id",
                (symbol, timeframe),
            )]

    def recent(self, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))]

    def statistics(self) -> dict:
        with self.connect() as connection:
            totals = dict(connection.execute("""SELECT COUNT(*) total,
                SUM(result='WIN') wins, SUM(result='LOSS') losses, SUM(result='DRAW') draws
                FROM signals WHERE result IS NOT NULL""").fetchone())
            grouped = [dict(row) for row in connection.execute("""SELECT symbol, timeframe, mode, COUNT(*) total,
                SUM(result='WIN') wins FROM signals WHERE result IS NOT NULL GROUP BY symbol, timeframe, mode""")]
            by_hour = [dict(row) for row in connection.execute("""SELECT CAST(strftime('%H', created_at) AS INTEGER) hour,
                COUNT(*) total, SUM(result='WIN') wins FROM signals WHERE result IS NOT NULL GROUP BY hour ORDER BY hour""")]
            by_score = [dict(row) for row in connection.execute("""SELECT CAST(score / 5 AS INTEGER) * 5 score_low,
                COUNT(*) total, SUM(result='WIN') wins FROM signals WHERE result IS NOT NULL GROUP BY score_low ORDER BY score_low""")]
            outcomes = [dict(row) for row in connection.execute(
                "SELECT direction, entry, exit, result FROM signals WHERE result IS NOT NULL AND entry IS NOT NULL AND exit IS NOT NULL ORDER BY id"
            )]
        total = totals.get("total") or 0
        wins = totals.get("wins") or 0
        returns = []
        for row in outcomes:
            move = (row["exit"] - row["entry"]) / row["entry"] if row["entry"] else 0
            returns.append(move if row["direction"] == "COMPRA" else -move)
        gains = sum(value for value in returns if value > 0)
        losses = abs(sum(value for value in returns if value < 0))
        result_sequence = [row["result"] for row in outcomes]
        def streak(target: str) -> int:
            best = current = 0
            for item in result_sequence:
                current = current + 1 if item == target else 0
                best = max(best, current)
            return best
        return {
            **totals, "accuracy": wins / total if total else None, "groups": grouped,
            "profit_factor": gains / losses if losses > 0 else None,
            "longest_win_streak": streak("WIN"), "longest_loss_streak": streak("LOSS"),
            "by_hour": by_hour, "by_score": by_score,
        }

    def calibration(self, score: int, width: int = 5) -> tuple[float | None, int]:
        low = score - score % width
        high = low + width - 1
        with self.connect() as connection:
            row = connection.execute("""SELECT COUNT(*) samples, SUM(result='WIN') wins FROM signals
                WHERE result IS NOT NULL AND score BETWEEN ? AND ?""", (low, high)).fetchone()
        samples, wins = int(row["samples"] or 0), int(row["wins"] or 0)
        return (wins / samples if samples >= 30 else None), samples
