from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..config.settings import app_data_dir


SCHEMA = """
CREATE TABLE IF NOT EXISTS mt5_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    volume REAL NOT NULL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_reward REAL,
    exit_price REAL,
    realized_r REAL,
    profit REAL,
    commission REAL NOT NULL DEFAULT 0,
    swap REAL NOT NULL DEFAULT 0,
    fee REAL NOT NULL DEFAULT 0,
    net_profit REAL,
    result TEXT NOT NULL DEFAULT 'PENDENTE',
    exit_reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ABERTA',
    strategy TEXT NOT NULL DEFAULT '',
    sensitivity TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT '',
    management TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    order_ticket INTEGER,
    deal_ticket INTEGER,
    position_ticket INTEGER,
    signal_created_at TEXT,
    source TEXT NOT NULL DEFAULT 'MT5'
);
CREATE INDEX IF NOT EXISTS idx_mt5_trades_opened ON mt5_trades(opened_at);
CREATE INDEX IF NOT EXISTS idx_mt5_trades_status ON mt5_trades(status);
CREATE INDEX IF NOT EXISTS idx_mt5_trades_position ON mt5_trades(position_ticket);
"""


class MT5TradeJournal:
    """Diário da fase MT5: registra posição/lote/SL/TP/P&L, nunca payout ou stake."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "prime_mt5_journal.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _iso_from_epoch(value) -> str:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _prime_row(row: dict, magic: int) -> bool:
        try:
            row_magic = int(row.get("magic", 0) or 0)
        except (TypeError, ValueError):
            row_magic = 0
        comment = str(row.get("comment") or "").lower()
        return row_magic == int(magic) or comment.startswith("prime trader")

    def active(self) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM mt5_trades WHERE status='ABERTA' ORDER BY id DESC"
            )]

    def recent(self, limit: int = 1000) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM mt5_trades ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
            )]

    def record_open(self, snapshot, *, volume: float, strategy: str,
                    sensitivity: str, mode: str, management: str) -> int:
        signal = snapshot.signal
        current = self.active()
        if current:
            # Uma operação por vez: não duplica o diário se a UI repetir o callback.
            return int(current[0]["id"])
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO mt5_trades(
                    opened_at, symbol, timeframe, direction, volume, entry_price,
                    stop_loss, take_profit, risk_reward, strategy, sensitivity, mode,
                    management, score, signal_created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(), snapshot.symbol, snapshot.timeframe,
                    signal.direction.value, float(volume), float(signal.entry or 0.0) or None,
                    float(signal.technical_stop or 0.0) or None,
                    float(signal.technical_target or 0.0) or None,
                    float(signal.technical_room_ratio or 0.0) or None,
                    str(strategy or ""), str(sensitivity or ""), str(mode or ""),
                    str(management or ""), int(signal.score or 0),
                    signal.created_at.isoformat() if getattr(signal, "created_at", None) else None,
                ),
            )
            return int(cursor.lastrowid)

    def _import_position(self, row: dict, *, timeframe: str, strategy: str,
                         sensitivity: str, mode: str, management: str) -> int:
        type_value = int(row.get("type", 0) or 0)
        direction = "COMPRA" if type_value == 0 else "VENDA"
        entry = float(row.get("price_open", 0.0) or 0.0)
        sl = float(row.get("sl", 0.0) or 0.0)
        tp = float(row.get("tp", 0.0) or 0.0)
        risk = abs(entry - sl) if entry and sl else 0.0
        reward = abs(tp - entry) if entry and tp else 0.0
        rr = reward / risk if risk > 0 else None
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO mt5_trades(
                    opened_at, symbol, timeframe, direction, volume, entry_price,
                    stop_loss, take_profit, risk_reward, strategy, sensitivity, mode,
                    management, position_ticket, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MT5')""",
                (
                    self._iso_from_epoch(row.get("time")), str(row.get("symbol") or ""), timeframe,
                    direction, float(row.get("volume", 0.0) or 0.0), entry or None,
                    sl or None, tp or None, rr, strategy, sensitivity, mode, management,
                    int(row.get("ticket", 0) or 0) or None,
                ),
            )
            return int(cursor.lastrowid)

    def _attach_position(self, trade_id: int, row: dict) -> None:
        entry = float(row.get("price_open", 0.0) or 0.0)
        sl = float(row.get("sl", 0.0) or 0.0)
        tp = float(row.get("tp", 0.0) or 0.0)
        risk = abs(entry - sl) if entry and sl else 0.0
        reward = abs(tp - entry) if entry and tp else 0.0
        rr = reward / risk if risk > 0 else None
        with self.connect() as connection:
            connection.execute(
                """UPDATE mt5_trades SET position_ticket=?, volume=?, entry_price=?,
                   stop_loss=?, take_profit=?, risk_reward=? WHERE id=?""",
                (
                    int(row.get("ticket", 0) or 0) or None,
                    float(row.get("volume", 0.0) or 0.0), entry or None,
                    sl or None, tp or None, rr, int(trade_id),
                ),
            )

    @staticmethod
    def _reason_label(reason: int, module) -> str:
        mapping = {
            int(getattr(module, "DEAL_REASON_SL", -1001)): "STOP LOSS",
            int(getattr(module, "DEAL_REASON_TP", -1002)): "TAKE PROFIT",
            int(getattr(module, "DEAL_REASON_CLIENT", -1003)): "FECHAMENTO MANUAL",
            int(getattr(module, "DEAL_REASON_MOBILE", -1004)): "FECHAMENTO MANUAL",
            int(getattr(module, "DEAL_REASON_WEB", -1005)): "FECHAMENTO MANUAL",
            int(getattr(module, "DEAL_REASON_EXPERT", -1006)): "ROBÔ/EXPERT",
        }
        return mapping.get(int(reason), "OUTRO")

    def _close_trade(self, row: dict, deals: list[dict], module) -> bool:
        opened_at = datetime.fromisoformat(str(row["opened_at"]).replace("Z", "+00:00"))
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        position_ticket = int(row.get("position_ticket") or 0)
        magic = int(getattr(module, "MAGIC", 260826)) if hasattr(module, "MAGIC") else 260826
        entry_out = {
            int(getattr(module, "DEAL_ENTRY_OUT", 1)),
            int(getattr(module, "DEAL_ENTRY_OUT_BY", 3)),
        }
        candidates: list[dict] = []
        for deal in deals:
            if not self._prime_row(deal, magic):
                continue
            if str(deal.get("symbol") or "") != str(row.get("symbol") or ""):
                continue
            deal_time = datetime.fromtimestamp(float(deal.get("time", 0) or 0), tz=timezone.utc)
            if deal_time < opened_at:
                continue
            if int(deal.get("entry", -1) or -1) not in entry_out:
                continue
            deal_position = int(deal.get("position_id", 0) or 0)
            if position_ticket and deal_position and deal_position != position_ticket:
                continue
            candidates.append(deal)
        if not candidates:
            return False
        candidates.sort(key=lambda item: (float(item.get("time", 0) or 0), int(item.get("ticket", 0) or 0)))
        exit_deal = candidates[-1]
        exit_price = float(exit_deal.get("price", 0.0) or 0.0)
        profit = sum(float(item.get("profit", 0.0) or 0.0) for item in candidates)
        commission = sum(float(item.get("commission", 0.0) or 0.0) for item in candidates)
        swap = sum(float(item.get("swap", 0.0) or 0.0) for item in candidates)
        fee = sum(float(item.get("fee", 0.0) or 0.0) for item in candidates)
        net = profit + commission + swap + fee
        result = "WIN" if net > 0 else "LOSS" if net < 0 else "DRAW"
        entry = float(row.get("entry_price") or 0.0)
        stop = float(row.get("stop_loss") or 0.0)
        risk = abs(entry - stop) if entry and stop else 0.0
        if risk > 0 and exit_price > 0:
            realized_r = ((exit_price - entry) / risk
                          if str(row.get("direction")) == "COMPRA"
                          else (entry - exit_price) / risk)
        else:
            realized_r = None
        closed_at = self._iso_from_epoch(exit_deal.get("time"))
        reason = self._reason_label(int(exit_deal.get("reason", -1) or -1), module)
        with self.connect() as connection:
            connection.execute(
                """UPDATE mt5_trades SET closed_at=?, exit_price=?, realized_r=?,
                   profit=?, commission=?, swap=?, fee=?, net_profit=?, result=?,
                   exit_reason=?, status='ENCERRADA', deal_ticket=? WHERE id=?""",
                (
                    closed_at, exit_price or None, realized_r, profit, commission, swap, fee,
                    net, result, reason, int(exit_deal.get("ticket", 0) or 0) or None,
                    int(row["id"]),
                ),
            )
        return True

    def sync_with_mt5(self, bridge, *, timeframe: str, strategy: str,
                      sensitivity: str, mode: str, management: str) -> None:
        module = bridge._module()
        magic = int(getattr(bridge, "MAGIC", 260826))
        getter = getattr(bridge, "prime_positions", None)
        positions = list(getter()) if callable(getter) else [
            row for row in bridge.positions() if self._prime_row(row, magic)
        ]
        active = self.active()
        if positions:
            position = positions[0]
            if active:
                self._attach_position(int(active[0]["id"]), position)
            else:
                trade_id = self._import_position(
                    position, timeframe=timeframe, strategy=strategy,
                    sensitivity=sensitivity, mode=mode, management=management,
                )
                self._attach_position(trade_id, position)
            return
        if not active:
            return
        deals = list(bridge.history(days=30))
        # bridge.history devolve dicts; o módulo serve apenas para constantes MT5.
        for trade in active:
            self._close_trade(trade, deals, module)

    def statistics(self) -> dict:
        rows = [row for row in self.recent(100000) if row.get("status") == "ENCERRADA"]
        wins = sum(row.get("result") == "WIN" for row in rows)
        losses = sum(row.get("result") == "LOSS" for row in rows)
        draws = sum(row.get("result") == "DRAW" for row in rows)
        directional = wins + losses
        gross_profit = sum(max(0.0, float(row.get("net_profit") or 0.0)) for row in rows)
        gross_loss = abs(sum(min(0.0, float(row.get("net_profit") or 0.0)) for row in rows))
        net_profit = sum(float(row.get("net_profit") or 0.0) for row in rows)
        realized = [float(row["realized_r"]) for row in rows if row.get("realized_r") is not None]
        return {
            "total": len(rows), "wins": wins, "losses": losses, "draws": draws,
            "directional_total": directional,
            "accuracy": wins / directional if directional else None,
            "gross_profit": gross_profit, "gross_loss": gross_loss,
            "net_profit": net_profit,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
            "expectancy_per_operation": net_profit / len(rows) if rows else 0.0,
            "average_r": sum(realized) / len(realized) if realized else None,
            "tp": sum(row.get("exit_reason") == "TAKE PROFIT" for row in rows),
            "sl": sum(row.get("exit_reason") == "STOP LOSS" for row in rows),
            "manual": sum(row.get("exit_reason") == "FECHAMENTO MANUAL" for row in rows),
        }


__all__ = ["MT5TradeJournal"]
