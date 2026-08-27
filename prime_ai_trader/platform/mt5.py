from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..core.models import Candle, TIMEFRAME_MINUTES


class MT5UnavailableError(RuntimeError):
    """Falha de instalação, inicialização ou sessão do terminal local."""


TRADE_MODE_LABELS = {
    0: "DEMO",
    1: "CONCURSO",
    2: "REAL",
}


@dataclass(frozen=True, slots=True)
class MT5AccountSnapshot:
    mode: str
    balance: float
    equity: float
    profit: float
    margin: float
    margin_free: float
    currency: str
    server: str
    company: str
    trade_allowed: bool
    expert_allowed: bool


@dataclass(frozen=True, slots=True)
class MT5TerminalSnapshot:
    account: MT5AccountSnapshot
    terminal_name: str
    terminal_path: str
    connected: bool
    build: int | None = None


def _field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        return getattr(row, name, default)


class MetaTrader5Gateway:
    """Conector local e somente leitura para um terminal MT5 já autenticado.

    O gateway não recebe, solicita ou armazena login e senha. A sessão é sempre
    a sessão que o próprio usuário abriu no terminal oficial do MetaTrader 5.
    """

    def __init__(self, module: Any | None = None) -> None:
        self._module = module
        self._connected = False
        self._terminal_path = ""

    @staticmethod
    def discover_terminal_paths() -> list[Path]:
        if os.name != "nt":
            return []
        roots = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        candidates: list[Path] = []
        direct_names = (
            ("MetaTrader 5", "terminal64.exe"),
            ("Clear MetaTrader 5", "terminal64.exe"),
            ("Clear", "MetaTrader 5", "terminal64.exe"),
        )
        for raw_root in roots:
            if not raw_root:
                continue
            root = Path(raw_root)
            for parts in direct_names:
                candidate = root.joinpath(*parts)
                if candidate.is_file() and candidate not in candidates:
                    candidates.append(candidate)
        return candidates

    def _mt5(self) -> Any:
        if self._module is not None:
            return self._module
        if os.name != "nt":
            raise MT5UnavailableError(
                "O conector MetaTrader 5 funciona no Windows 10/11 com o terminal instalado."
            )
        try:
            self._module = importlib.import_module("MetaTrader5")
        except (ImportError, OSError) as exc:
            raise MT5UnavailableError(
                "O componente MetaTrader5 não está disponível. Reinstale o Prime AI Trader 1.3.0."
            ) from exc
        return self._module

    def connect(self, terminal_path: str = "") -> MT5TerminalSnapshot:
        mt5 = self._mt5()
        selected = Path(terminal_path) if terminal_path else None
        if selected is not None and not selected.is_file():
            raise MT5UnavailableError(f"Terminal MT5 não encontrado em: {selected}")
        if selected is None:
            discovered = self.discover_terminal_paths()
            selected = discovered[0] if discovered else None
        initialized = mt5.initialize(path=str(selected)) if selected else mt5.initialize()
        if not initialized:
            error = mt5.last_error() if hasattr(mt5, "last_error") else "erro desconhecido"
            raise MT5UnavailableError(
                f"Não foi possível conectar ao terminal MetaTrader 5: {error}. "
                "Abra o MT5, entre na conta da Clear e tente novamente."
            )
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        if account is None or terminal is None:
            mt5.shutdown()
            raise MT5UnavailableError(
                "O MetaTrader 5 abriu, mas nenhuma conta ativa foi encontrada. "
                "Faça login na Clear diretamente pelo terminal."
            )
        self._connected = True
        self._terminal_path = str(
            _field(terminal, "path", str(selected or "")) or str(selected or "")
        )
        return self._terminal_snapshot(account, terminal)

    def _terminal_snapshot(self, account: Any, terminal: Any) -> MT5TerminalSnapshot:
        trade_mode = int(_field(account, "trade_mode", -1))
        account_snapshot = MT5AccountSnapshot(
            mode=TRADE_MODE_LABELS.get(trade_mode, "DESCONHECIDA"),
            balance=float(_field(account, "balance", 0.0) or 0.0),
            equity=float(_field(account, "equity", 0.0) or 0.0),
            profit=float(_field(account, "profit", 0.0) or 0.0),
            margin=float(_field(account, "margin", 0.0) or 0.0),
            margin_free=float(_field(account, "margin_free", 0.0) or 0.0),
            currency=str(_field(account, "currency", "") or ""),
            server=str(_field(account, "server", "") or ""),
            company=str(_field(account, "company", "") or ""),
            trade_allowed=bool(_field(account, "trade_allowed", False)),
            expert_allowed=bool(_field(account, "trade_expert", False)),
        )
        version = self._module.version() if hasattr(self._module, "version") else None
        build = int(version[1]) if version and len(version) > 1 else None
        return MT5TerminalSnapshot(
            account=account_snapshot,
            terminal_name=str(_field(terminal, "name", "MetaTrader 5") or "MetaTrader 5"),
            terminal_path=self._terminal_path,
            connected=bool(_field(terminal, "connected", True)),
            build=build,
        )

    def refresh_account(self) -> MT5TerminalSnapshot:
        if not self._connected:
            raise MT5UnavailableError("MetaTrader 5 não está conectado.")
        mt5 = self._mt5()
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        if account is None or terminal is None:
            self._connected = False
            raise MT5UnavailableError("A sessão do MetaTrader 5 foi desconectada.")
        return self._terminal_snapshot(account, terminal)

    def symbols(self, *, visible_only: bool = True) -> list[str]:
        if not self._connected:
            raise MT5UnavailableError("Conecte o MetaTrader 5 antes de carregar os ativos.")
        rows = self._mt5().symbols_get()
        if rows is None:
            return []
        names = []
        for row in rows:
            if visible_only and not bool(_field(row, "visible", False)):
                continue
            name = str(_field(row, "name", "") or "").strip()
            if name:
                names.append(name)
        return sorted(set(names))

    def candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        if not self._connected:
            raise MT5UnavailableError("Conecte o MetaTrader 5 antes de solicitar candles.")
        if timeframe not in TIMEFRAME_MINUTES:
            raise ValueError(f"Timeframe não suportado: {timeframe}")
        mt5 = self._mt5()
        attr = {
            "1m": "TIMEFRAME_M1", "3m": "TIMEFRAME_M3", "5m": "TIMEFRAME_M5",
            "15m": "TIMEFRAME_M15", "30m": "TIMEFRAME_M30", "1h": "TIMEFRAME_H1",
            "4h": "TIMEFRAME_H4",
        }[timeframe]
        timeframe_id = getattr(mt5, attr)
        rows = mt5.copy_rates_from_pos(symbol, timeframe_id, 0, max(1, int(limit)))
        if rows is None:
            error = mt5.last_error() if hasattr(mt5, "last_error") else "erro desconhecido"
            raise MT5UnavailableError(f"O MT5 não entregou candles de {symbol}: {error}")
        now = datetime.now(timezone.utc)
        duration = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
        candles: list[Candle] = []
        for row in rows:
            opened = datetime.fromtimestamp(int(_field(row, "time", 0)), tz=timezone.utc)
            closed_at = opened + duration
            real_volume = float(_field(row, "real_volume", 0.0) or 0.0)
            tick_volume = float(_field(row, "tick_volume", 0.0) or 0.0)
            candles.append(Candle(
                open_time=opened,
                open=float(_field(row, "open", 0.0)),
                high=float(_field(row, "high", 0.0)),
                low=float(_field(row, "low", 0.0)),
                close=float(_field(row, "close", 0.0)),
                volume=real_volume if real_volume > 0 else tick_volume,
                close_time=closed_at,
                closed=closed_at <= now,
            ))
        return candles

    def positions(self) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        rows = self._mt5().positions_get()
        if rows is None:
            return []
        fields = ("ticket", "symbol", "type", "volume", "price_open", "price_current", "sl", "tp", "profit")
        return [{name: _field(row, name) for name in fields} for row in rows]

    def history(self, date_from: datetime, date_to: datetime) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        rows = self._mt5().history_deals_get(date_from, date_to)
        if rows is None:
            return []
        fields = ("ticket", "order", "time", "symbol", "type", "entry", "volume", "price", "profit", "commission", "swap")
        return [{name: _field(row, name) for name in fields} for row in rows]

    def disconnect(self) -> None:
        if self._module is not None and self._connected:
            self._module.shutdown()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected
