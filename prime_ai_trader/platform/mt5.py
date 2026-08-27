from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..core.models import Candle, TIMEFRAME_MINUTES


class MT5UnavailableError(RuntimeError):
    """Falha de instalação, inicialização, sessão ou operação do terminal local."""


class MT5TradingDisabledError(RuntimeError):
    """Tentativa de envio de ordem sem habilitação explícita do usuário."""


TRADE_MODE_LABELS = {0: "DEMO", 1: "CONCURSO", 2: "REAL"}


@dataclass(frozen=True, slots=True)
class MT5AccountSnapshot:
    login: int
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
    trade_allowed: bool
    build: int | None = None


@dataclass(frozen=True, slots=True)
class MT5TradeResult:
    ok: bool
    retcode: int
    order: int
    deal: int
    volume: float
    price: float
    comment: str
    request_id: int | None = None


def _field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        return getattr(row, name, default)


class MetaTrader5Gateway:
    """Conector local para um MetaTrader 5 já autenticado pelo próprio usuário.

    O Prime Trader nunca recebe login, senha, assinatura eletrônica ou token da
    corretora. A autenticação continua no terminal oficial. A execução real fica
    bloqueada por padrão e precisa ser habilitada explicitamente na interface.
    """

    MAGIC = 260826
    COMMENT = "PrimeTrader"

    def __init__(self, module: Any | None = None) -> None:
        self._module = module
        self._connected = False
        self._terminal_path = ""
        self._live_trading_enabled = False

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
            ("MetaTrader 5 CLEAR", "terminal64.exe"),
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
                "O componente MetaTrader5 não está disponível. Reinstale o Prime Trader."
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
                "O MetaTrader 5 foi encontrado, mas nenhuma conta ativa foi detectada. "
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
            login=int(_field(account, "login", 0) or 0),
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
            trade_allowed=bool(_field(terminal, "trade_allowed", True)),
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
            self._live_trading_enabled = False
            raise MT5UnavailableError("A sessão do MetaTrader 5 foi desconectada.")
        return self._terminal_snapshot(account, terminal)

    def symbols(self, *, visible_only: bool = True) -> list[str]:
        if not self._connected:
            raise MT5UnavailableError("Conecte o MetaTrader 5 antes de carregar os ativos.")
        rows = self._mt5().symbols_get()
        if rows is None:
            return []
        names: list[str] = []
        for row in rows:
            if visible_only and not bool(_field(row, "visible", False)):
                continue
            name = str(_field(row, "name", "") or "").strip()
            if name:
                names.append(name)
        return sorted(set(names))

    def ensure_symbol(self, symbol: str) -> None:
        mt5 = self._mt5()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5UnavailableError(f"Ativo {symbol} não existe no MetaTrader 5 conectado.")
        if not bool(_field(info, "visible", False)):
            selected = mt5.symbol_select(symbol, True)
            if not selected:
                raise MT5UnavailableError(
                    f"Não foi possível adicionar {symbol} à Observação do Mercado do MT5."
                )

    def candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        if not self._connected:
            raise MT5UnavailableError("Conecte o MetaTrader 5 antes de solicitar candles.")
        if timeframe not in TIMEFRAME_MINUTES:
            raise ValueError(f"Timeframe não suportado: {timeframe}")
        self.ensure_symbol(symbol)
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

    def positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        mt5 = self._mt5()
        rows = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if rows is None:
            return []
        fields = (
            "ticket", "symbol", "type", "volume", "price_open", "price_current",
            "sl", "tp", "profit", "magic", "comment",
        )
        return [{name: _field(row, name) for name in fields} for row in rows]

    def history(self, date_from: datetime, date_to: datetime) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        rows = self._mt5().history_deals_get(date_from, date_to)
        if rows is None:
            return []
        fields = (
            "ticket", "order", "time", "symbol", "type", "entry", "volume",
            "price", "profit", "commission", "swap", "magic", "comment",
        )
        return [{name: _field(row, name) for name in fields} for row in rows]

    def set_live_trading_enabled(self, enabled: bool) -> None:
        if enabled and not self._connected:
            raise MT5UnavailableError("Conecte o MetaTrader 5 antes de habilitar ordens reais.")
        self._live_trading_enabled = bool(enabled)

    def _assert_can_trade(self) -> MT5TerminalSnapshot:
        if not self._connected:
            raise MT5UnavailableError("MetaTrader 5 não está conectado.")
        if not self._live_trading_enabled:
            raise MT5TradingDisabledError(
                "Execução real está bloqueada. Habilite conscientemente na interface."
            )
        snapshot = self.refresh_account()
        if not snapshot.connected:
            raise MT5UnavailableError("Terminal MetaTrader 5 está sem conexão com o servidor.")
        if not snapshot.trade_allowed or not snapshot.account.trade_allowed:
            raise MT5UnavailableError(
                "O MT5/corretora não autorizou negociação nesta sessão. Verifique AutoTrading e a conta."
            )
        return snapshot

    def _success_retcodes(self) -> set[int]:
        mt5 = self._mt5()
        values = set()
        for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_DONE_PARTIAL", "TRADE_RETCODE_PLACED"):
            value = getattr(mt5, name, None)
            if value is not None:
                values.add(int(value))
        return values

    def _normalize_volume(self, symbol: str, volume: float) -> float:
        mt5 = self._mt5()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5UnavailableError(f"Ativo {symbol} não encontrado.")
        minimum = float(_field(info, "volume_min", 0.01) or 0.01)
        maximum = float(_field(info, "volume_max", volume) or volume)
        step = float(_field(info, "volume_step", minimum) or minimum)
        value = min(max(float(volume), minimum), maximum)
        steps = round((value - minimum) / step)
        normalized = minimum + steps * step
        digits = max(0, min(8, len(str(step).split(".")[-1]) if "." in str(step) else 0))
        return round(normalized, digits)

    def _fill_candidates(self, info: Any) -> list[int]:
        mt5 = self._mt5()
        preferred: list[int] = []
        current = _field(info, "filling_mode", None)
        if current is not None:
            preferred.append(int(current))
        for name in ("ORDER_FILLING_FOK", "ORDER_FILLING_IOC", "ORDER_FILLING_RETURN"):
            value = getattr(mt5, name, None)
            if value is not None and int(value) not in preferred:
                preferred.append(int(value))
        return preferred or [0]

    def place_market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        deviation: int = 20,
        comment: str | None = None,
    ) -> MT5TradeResult:
        self._assert_can_trade()
        mt5 = self._mt5()
        self.ensure_symbol(symbol)
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            raise MT5UnavailableError(f"Cotação de {symbol} indisponível no MT5.")
        normalized_side = str(side).upper().strip()
        if normalized_side not in {"BUY", "SELL", "COMPRA", "VENDA"}:
            raise ValueError("Lado da ordem deve ser BUY/SELL ou COMPRA/VENDA.")
        buying = normalized_side in {"BUY", "COMPRA"}
        order_type = mt5.ORDER_TYPE_BUY if buying else mt5.ORDER_TYPE_SELL
        price = float(_field(tick, "ask" if buying else "bid", 0.0) or 0.0)
        if price <= 0:
            raise MT5UnavailableError(f"Preço executável de {symbol} indisponível.")
        volume = self._normalize_volume(symbol, volume)
        base_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": max(0, int(deviation)),
            "magic": self.MAGIC,
            "comment": (comment or self.COMMENT)[:31],
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if stop_loss is not None and float(stop_loss) > 0:
            base_request["sl"] = float(stop_loss)
        if take_profit is not None and float(take_profit) > 0:
            base_request["tp"] = float(take_profit)

        last_result = None
        for fill in self._fill_candidates(info):
            request = dict(base_request, type_filling=fill)
            check = mt5.order_check(request)
            if check is None:
                continue
            check_code = int(_field(check, "retcode", -1))
            check_comment = str(_field(check, "comment", "") or "")
            if check_code not in {0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)}:
                # Alguns servidores retornam 0 no check e outros usam códigos de trade.
                if "invalid fill" in check_comment.lower():
                    continue
            result = mt5.order_send(request)
            last_result = result
            if result is None:
                continue
            retcode = int(_field(result, "retcode", -1))
            if retcode in self._success_retcodes():
                return MT5TradeResult(
                    ok=True,
                    retcode=retcode,
                    order=int(_field(result, "order", 0) or 0),
                    deal=int(_field(result, "deal", 0) or 0),
                    volume=float(_field(result, "volume", volume) or volume),
                    price=float(_field(result, "price", price) or price),
                    comment=str(_field(result, "comment", "") or "executada"),
                    request_id=(int(_field(result, "request_id", 0) or 0) or None),
                )
            comment_text = str(_field(result, "comment", "") or "")
            if "fill" not in comment_text.lower():
                break

        if last_result is None:
            error = mt5.last_error() if hasattr(mt5, "last_error") else "sem retorno"
            raise MT5UnavailableError(f"O MT5 não retornou resultado da ordem: {error}")
        raise MT5UnavailableError(
            f"Ordem rejeitada pelo MT5/corretora: retcode={_field(last_result, 'retcode', -1)} "
            f"• {_field(last_result, 'comment', 'sem detalhe')}"
        )

    def close_position(self, ticket: int, *, deviation: int = 20) -> MT5TradeResult:
        self._assert_can_trade()
        mt5 = self._mt5()
        rows = mt5.positions_get(ticket=int(ticket))
        if not rows:
            raise MT5UnavailableError(f"Posição {ticket} não foi encontrada.")
        position = rows[0]
        symbol = str(_field(position, "symbol", "") or "")
        volume = float(_field(position, "volume", 0.0) or 0.0)
        position_type = int(_field(position, "type", -1))
        buying_position = position_type == int(mt5.POSITION_TYPE_BUY)
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            raise MT5UnavailableError(f"Cotação de {symbol} indisponível para encerramento.")
        order_type = mt5.ORDER_TYPE_SELL if buying_position else mt5.ORDER_TYPE_BUY
        price = float(_field(tick, "bid" if buying_position else "ask", 0.0) or 0.0)
        base_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(ticket),
            "symbol": symbol,
            "volume": self._normalize_volume(symbol, volume),
            "type": order_type,
            "price": price,
            "deviation": max(0, int(deviation)),
            "magic": self.MAGIC,
            "comment": f"{self.COMMENT}-close"[:31],
            "type_time": mt5.ORDER_TIME_GTC,
        }
        last_result = None
        for fill in self._fill_candidates(info):
            result = mt5.order_send(dict(base_request, type_filling=fill))
            last_result = result
            if result is None:
                continue
            retcode = int(_field(result, "retcode", -1))
            if retcode in self._success_retcodes():
                return MT5TradeResult(
                    ok=True, retcode=retcode,
                    order=int(_field(result, "order", 0) or 0),
                    deal=int(_field(result, "deal", 0) or 0),
                    volume=float(_field(result, "volume", volume) or volume),
                    price=float(_field(result, "price", price) or price),
                    comment=str(_field(result, "comment", "") or "encerrada"),
                    request_id=(int(_field(result, "request_id", 0) or 0) or None),
                )
            if "fill" not in str(_field(result, "comment", "") or "").lower():
                break
        raise MT5UnavailableError(
            f"Encerramento rejeitado: retcode={_field(last_result, 'retcode', -1)} "
            f"• {_field(last_result, 'comment', 'sem detalhe')}"
        )

    def close_symbol_positions(self, symbol: str) -> list[MT5TradeResult]:
        results: list[MT5TradeResult] = []
        for position in self.positions(symbol):
            results.append(self.close_position(int(position["ticket"])))
        if not results:
            raise MT5UnavailableError(f"Não existe posição aberta em {symbol}.")
        return results

    def disconnect(self) -> None:
        self._live_trading_enabled = False
        if self._module is not None and self._connected:
            self._module.shutdown()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def live_trading_enabled(self) -> bool:
        return self._live_trading_enabled
