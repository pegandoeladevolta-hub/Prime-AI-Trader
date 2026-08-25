from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from datetime import datetime, timezone

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
    mode TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'MANUAL',
    strategy TEXT NOT NULL DEFAULT '',
    sensitivity TEXT NOT NULL DEFAULT '',
    payout_percent INTEGER NOT NULL DEFAULT 80,
    stake_amount REAL NOT NULL DEFAULT 1.0,
    profit_loss REAL,
    result_source TEXT NOT NULL DEFAULT 'INFERRED',
    result_observed_at TEXT,
    technical_stop REAL,
    technical_target REAL,
    technical_room_ratio REAL
);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol, timeframe);
CREATE TABLE IF NOT EXISTS decision_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    signal_id INTEGER,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    horizon_minutes INTEGER NOT NULL,
    platform TEXT NOT NULL,
    strategy TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    mode TEXT NOT NULL,
    direction TEXT NOT NULL,
    state TEXT NOT NULL,
    score INTEGER NOT NULL,
    payout_percent INTEGER NOT NULL,
    stake_amount REAL NOT NULL,
    pullback_state TEXT NOT NULL DEFAULT '',
    market_regime TEXT NOT NULL DEFAULT '',
    structure_event TEXT NOT NULL DEFAULT '',
    reason_summary TEXT NOT NULL DEFAULT '',
    technical_score INTEGER NOT NULL DEFAULT 0,
    model_score INTEGER,
    source_name TEXT NOT NULL DEFAULT '',
    snapshot_json TEXT NOT NULL,
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decision_history(created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_context ON decision_history(symbol, timeframe, event_type);
CREATE INDEX IF NOT EXISTS idx_decisions_signal ON decision_history(signal_id);
"""

MIGRATION_COLUMNS = {
    "platform": "TEXT NOT NULL DEFAULT 'MANUAL'",
    "strategy": "TEXT NOT NULL DEFAULT ''",
    "sensitivity": "TEXT NOT NULL DEFAULT ''",
    "payout_percent": "INTEGER NOT NULL DEFAULT 80",
    "stake_amount": "REAL NOT NULL DEFAULT 1.0",
    "profit_loss": "REAL",
    "result_source": "TEXT NOT NULL DEFAULT 'INFERRED'",
    "result_observed_at": "TEXT",
    "technical_stop": "REAL",
    "technical_target": "REAL",
    "technical_room_ratio": "REAL",
}


class Repository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "prime_ai_trader.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(signals)")}
            for name, declaration in MIGRATION_COLUMNS.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE signals ADD COLUMN {name} {declaration}")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_context ON signals(platform, market, symbol, strategy)",
            )
            connection.execute(
                """UPDATE signals SET profit_loss=CASE
                WHEN result='WIN' THEN stake_amount * payout_percent / 100.0
                WHEN result='LOSS' THEN -stake_amount
                WHEN result='DRAW' THEN 0.0 ELSE NULL END
                WHERE result IS NOT NULL AND profit_loss IS NULL""",
            )
            connection.execute(
                """UPDATE signals SET result_observed_at=created_at
                WHERE result IS NOT NULL AND result_observed_at IS NULL""",
            )

    def save_signal(self, signal: Signal, market: str, symbol: str, timeframe: str,
                    indicators: dict, mode: str, *, platform: str = "MANUAL",
                    strategy: str = "", sensitivity: str = "",
                    stake_amount: float = 1.0) -> int:
        payout = min(max(int(signal.payout_percent or 80), 1), 200)
        stake = float(stake_amount) if math.isfinite(float(stake_amount)) and float(stake_amount) > 0 else 1.0
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO signals(created_at, market, symbol, timeframe, horizon_minutes, direction, state,
                score, entry, probabilities_json, indicators_json, confluences_json, model_version, mode,
                platform, strategy, sensitivity, payout_percent, stake_amount, result_source,
                technical_stop, technical_target, technical_room_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (signal.created_at.isoformat(), market, symbol, timeframe, signal.horizon_minutes,
                 signal.direction.value, signal.state.value, signal.score, signal.entry,
                 json.dumps(signal.probabilities), json.dumps(indicators), json.dumps(signal.confluences, ensure_ascii=False),
                 signal.model_version, mode, str(platform or "MANUAL").upper(), strategy,
                 sensitivity, payout, stake, "INFERRED", signal.technical_stop,
                 signal.technical_target, signal.technical_room_ratio),
            )
            return int(cursor.lastrowid)

    def set_result(self, signal_id: int, exit_price: float | None, result: str, *,
                   result_source: str = "INFERRED", payout_percent: int | None = None,
                   stake_amount: float | None = None,
                   observed_at: datetime | None = None) -> None:
        if result not in {"WIN", "LOSS", "DRAW"}:
            raise ValueError("Resultado inválido.")
        source = str(result_source or "INFERRED").upper()
        if source not in {"INFERRED", "MANUAL"}:
            raise ValueError("Fonte do resultado inválida.")
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payout_percent, stake_amount, entry, exit FROM signals WHERE id=?", (signal_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Sinal não encontrado.")
            payout = min(max(int(payout_percent if payout_percent is not None else row["payout_percent"]), 1), 200)
            raw_stake = stake_amount if stake_amount is not None else row["stake_amount"]
            stake = float(raw_stake)
            if not math.isfinite(stake) or stake <= 0:
                raise ValueError("Valor da entrada inválido.")
            profit_loss = stake * payout / 100 if result == "WIN" else -stake if result == "LOSS" else 0.0
            effective_exit = exit_price if exit_price is not None else row["exit"] if row["exit"] is not None else row["entry"]
            stamp = observed_at or datetime.now(timezone.utc)
            connection.execute(
                """UPDATE signals SET exit=?, result=?, payout_percent=?, stake_amount=?,
                profit_loss=?, result_source=?, result_observed_at=? WHERE id=?""",
                (effective_exit, result, payout, stake, profit_loss, source,
                 stamp.isoformat(), signal_id),
            )
            signal_row = connection.execute(
                "SELECT * FROM signals WHERE id=?", (signal_id,),
            ).fetchone()
            previous = connection.execute(
                """SELECT snapshot_json FROM decision_history WHERE signal_id=?
                   ORDER BY id DESC LIMIT 1""", (signal_id,),
            ).fetchone()
            snapshot = json.loads(previous["snapshot_json"]) if previous else {}
            signal_data = dict(signal_row)
            snapshot.update({
                "created_at": stamp.isoformat(),
                "event_type": "RESULTADO OBSERVADO" if source == "MANUAL" else "RESULTADO INFERIDO",
                "signal_id": signal_id,
                "market": signal_data["market"],
                "symbol": signal_data["symbol"],
                "timeframe": signal_data["timeframe"],
                "horizon_minutes": signal_data["horizon_minutes"],
                "platform": signal_data.get("platform") or "MANUAL",
                "strategy": signal_data.get("strategy") or "",
                "sensitivity": signal_data.get("sensitivity") or "",
                "mode": signal_data["mode"],
                "direction": signal_data["direction"],
                "state": signal_data["state"],
                "score": signal_data["score"],
                "payout_percent": payout,
                "stake_amount": stake,
                "result": result,
                "result_source": source,
                "exit_price": effective_exit,
                "profit_loss": profit_loss,
                "result_observed_at": stamp.isoformat(),
                "reason_summary": (
                    f"{result} {'observado na plataforma' if source == 'MANUAL' else 'inferido pela fonte pública'} "
                    f"• resultado R$ {profit_loss:+.2f}"
                ),
            })
            self._insert_decision(connection, snapshot)

    @staticmethod
    def _insert_decision(connection: sqlite3.Connection, snapshot: dict) -> int:
        created = snapshot.get("created_at") or datetime.now(timezone.utc).isoformat()
        data = dict(snapshot)
        data["created_at"] = created
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        cursor = connection.execute(
            """INSERT INTO decision_history(created_at, event_type, signal_id, market, symbol,
               timeframe, horizon_minutes, platform, strategy, sensitivity, mode,
               direction, state, score, payout_percent, stake_amount, pullback_state,
               market_regime, structure_event, reason_summary, technical_score,
               model_score, source_name, snapshot_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                created, str(data.get("event_type") or "ANÁLISE"), data.get("signal_id"),
                str(data.get("market") or ""), str(data.get("symbol") or ""),
                str(data.get("timeframe") or ""), int(data.get("horizon_minutes") or 1),
                str(data.get("platform") or "MANUAL"), str(data.get("strategy") or ""),
                str(data.get("sensitivity") or ""), str(data.get("mode") or ""),
                str(data.get("direction") or "AGUARDAR"), str(data.get("state") or ""),
                int(data.get("score") or 0), int(data.get("payout_percent") or 80),
                float(data.get("stake_amount") or 1.0), str(data.get("pullback_state") or ""),
                str(data.get("market_regime") or ""), str(data.get("structure_event") or ""),
                str(data.get("reason_summary") or ""), int(data.get("technical_score") or 0),
                data.get("model_score"), str(data.get("source_name") or ""), raw,
            ),
        )
        return int(cursor.lastrowid)

    def record_decision(self, snapshot: dict) -> int:
        """Persiste uma decisão real, inclusive espera, formação e resultados."""
        with self.connect() as connection:
            return self._insert_decision(connection, snapshot)

    def decision_history(self, limit: int = 500, *, symbol: str | None = None,
                         event_type: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if symbol:
            clauses.append("history.symbol=?")
            params.append(symbol)
        if event_type:
            clauses.append("history.event_type=?")
            params.append(event_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        maximum = min(max(int(limit), 1), 250_000)
        params.append(maximum)
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                f"""SELECT history.*, signals.result, signals.exit AS exit_price,
                       signals.profit_loss, signals.result_source, signals.result_observed_at
                    FROM decision_history AS history
                    LEFT JOIN signals ON signals.id=history.signal_id
                    {where} ORDER BY history.id DESC LIMIT ?""", params,
            )]

    def record_manual_result(self, signal_id: int, result: str, *,
                             payout_percent: int | None = None,
                             stake_amount: float | None = None,
                             exit_price: float | None = None) -> None:
        """Registra o resultado realmente observado pelo usuário na plataforma."""
        self.set_result(
            signal_id, exit_price, result, result_source="MANUAL",
            payout_percent=payout_percent, stake_amount=stake_amount,
        )

    def pending(self, symbol: str, timeframe: str) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM signals WHERE result IS NULL AND symbol=? AND timeframe=? ORDER BY id",
                (symbol, timeframe),
            )]

    def recent(self, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))]

    def statistics(self, *, platform: str | None = None, symbol: str | None = None,
                   strategy: str | None = None, result_source: str | None = None) -> dict:
        clauses = ["result IS NOT NULL"]
        params: list[object] = []
        for column, value in (("platform", platform), ("symbol", symbol),
                              ("strategy", strategy), ("result_source", result_source)):
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        where = " AND ".join(clauses)
        with self.connect() as connection:
            totals = dict(connection.execute(f"""SELECT COUNT(*) total,
                SUM(result='WIN') wins, SUM(result='LOSS') losses, SUM(result='DRAW') draws,
                SUM(result_source='MANUAL') manual_results,
                SUM(result_source='INFERRED') inferred_results,
                SUM(CASE WHEN profit_loss > 0 THEN profit_loss ELSE 0 END) gross_profit,
                ABS(SUM(CASE WHEN profit_loss < 0 THEN profit_loss ELSE 0 END)) gross_loss,
                SUM(COALESCE(profit_loss, 0)) net_profit,
                AVG(CASE WHEN result IN ('WIN','LOSS') THEN payout_percent END) average_payout,
                AVG(CASE WHEN result IN ('WIN','LOSS') THEN stake_amount END) average_stake
                FROM signals WHERE {where}""", params).fetchone())
            grouped = [dict(row) for row in connection.execute(f"""SELECT platform, symbol, timeframe,
                strategy, mode, COUNT(*) total, SUM(result='WIN') wins,
                SUM(result='LOSS') losses, SUM(result='DRAW') draws,
                SUM(COALESCE(profit_loss, 0)) net_profit
                FROM signals WHERE {where}
                GROUP BY platform, symbol, timeframe, strategy, mode""", params)]
            by_hour = [dict(row) for row in connection.execute(f"""SELECT CAST(strftime('%H', created_at) AS INTEGER) hour,
                COUNT(*) total, SUM(result='WIN') wins FROM signals WHERE {where}
                GROUP BY hour ORDER BY hour""", params)]
            by_score = [dict(row) for row in connection.execute(f"""SELECT CAST(score / 5 AS INTEGER) * 5 score_low,
                COUNT(*) total, SUM(result='WIN') wins FROM signals WHERE {where}
                GROUP BY score_low ORDER BY score_low""", params)]
            outcomes = [dict(row) for row in connection.execute(
                f"SELECT direction, entry, exit, result, profit_loss FROM signals WHERE {where} ORDER BY id",
                params,
            )]
        wins = totals.get("wins") or 0
        losses_count = totals.get("losses") or 0
        directional_total = wins + losses_count
        gains = float(totals.get("gross_profit") or 0.0)
        losses = float(totals.get("gross_loss") or 0.0)
        net = float(totals.get("net_profit") or 0.0)
        average_payout = float(totals.get("average_payout") or 0.0)
        confidence_low, confidence_high = self._wilson_interval(wins, directional_total)
        result_sequence = [row["result"] for row in outcomes]
        def streak(target: str) -> int:
            best = current = 0
            for item in result_sequence:
                current = current + 1 if item == target else 0
                best = max(best, current)
            return best
        return {
            **totals, "accuracy": wins / directional_total if directional_total else None,
            "directional_total": directional_total, "groups": grouped,
            "profit_factor": gains / losses if losses > 0 else None,
            "gross_profit": gains, "gross_loss": losses, "net_profit": net,
            "break_even_rate": 1 / (1 + average_payout / 100) if average_payout > 0 else None,
            "expectancy_per_operation": net / directional_total if directional_total else None,
            "confidence_low": confidence_low, "confidence_high": confidence_high,
            "longest_win_streak": streak("WIN"), "longest_loss_streak": streak("LOSS"),
            "by_hour": by_hour, "by_score": by_score,
        }

    @staticmethod
    def _wilson_interval(wins: int, samples: int, z: float = 1.96) -> tuple[float, float]:
        if samples <= 0:
            return 0.0, 1.0
        rate = wins / samples
        denominator = 1 + z * z / samples
        center = rate + z * z / (2 * samples)
        margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * samples)) / samples)
        return max(0.0, (center - margin) / denominator), min(1.0, (center + margin) / denominator)

    def calibration(self, score: int, market: str | None = None, symbol: str | None = None,
                    timeframe: str | None = None, horizon_minutes: int | None = None,
                    mode: str | None = None, width: int = 5, *,
                    sensitivity: str | None = None, strategy: str | None = None,
                    result_source: str | None = None) -> tuple[float | None, int]:
        low = score - score % width
        high = low + width - 1
        clauses = ["result IS NOT NULL", "score BETWEEN ? AND ?"]
        params: list[object] = [low, high]
        for column, value in (
            ("market", market), ("symbol", symbol), ("timeframe", timeframe),
            ("horizon_minutes", horizon_minutes), ("mode", mode),
            ("sensitivity", sensitivity), ("strategy", strategy),
            ("result_source", result_source),
        ):
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        with self.connect() as connection:
            row = connection.execute(
                f"""SELECT SUM(result IN ('WIN','LOSS')) samples, SUM(result='WIN') wins
                FROM signals WHERE {' AND '.join(clauses)}""", params,
            ).fetchone()
        samples, wins = int(row["samples"] or 0), int(row["wins"] or 0)
        return (wins / samples if samples >= 30 else None), samples
