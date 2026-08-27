from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class MT5UnavailableError(RuntimeError):
    pass


class MT5ExecutionError(RuntimeError):
    pass


@dataclass(slots=True)
class MT5AccountSnapshot:
    login: int
    server: str
    name: str
    currency: str
    balance: float
    equity: float
    margin: float
    margin_free: float
    trade_allowed: bool


@dataclass(slots=True)
class MT5OrderResult:
    ok: bool
    retcode: int
    order: int | None
    deal: int | None
    volume: float
    price: float
    comment: str


class MT5Bridge:
    """Integração local com um terminal MetaTrader 5 instalado no Windows.

    O Prime Trader não armazena login/senha do broker. A conexão usa o terminal
    já autenticado pelo próprio usuário. A execução real só ocorre quando o
    chamador passa ``armed=True`` explicitamente.
    """

    MAGIC = 260826

    def __init__(self, terminal_path: str | Path | None = None) -> None:
        self.terminal_path = str(terminal_path) if terminal_path else None
        self._mt5 = None
        self.connected = False

    def _module(self):
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:
            raise MT5UnavailableError(
                "O conector MetaTrader5 não está instalado. Instale o componente "
                "oficial no ambiente do Prime Trader e mantenha o terminal MT5 instalado."
            ) from exc
        self._mt5 = mt5
        return mt5

    def connect(self) -> MT5AccountSnapshot:
        mt5 = self._module()
        kwargs: dict[str, Any] = {}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path
        if not mt5.initialize(**kwargs):
            raise MT5UnavailableError(f"Não foi possível conectar ao MT5: {mt5.last_error()}")
        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            raise MT5UnavailableError(
                "O MT5 abriu, mas não existe uma conta autenticada no terminal. "
                "Entre na conta diretamente no MetaTrader e tente novamente."
            )
        self.connected = True
        return self._account_snapshot(info)

    def disconnect(self) -> None:
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
            finally:
                self.connected = False

    def account(self) -> MT5AccountSnapshot:
        mt5 = self._module()
        info = mt5.account_info()
        if info is None:
            raise MT5UnavailableError("Conta MT5 não disponível.")
        return self._account_snapshot(info)

    @staticmethod
    def _account_snapshot(info) -> MT5AccountSnapshot:
        return MT5AccountSnapshot(
            login=int(getattr(info, "login", 0)),
            server=str(getattr(info, "server", "")),
            name=str(getattr(info, "name", "")),
            currency=str(getattr(info, "currency", "")),
            balance=float(getattr(info, "balance", 0.0)),
            equity=float(getattr(info, "equity", 0.0)),
            margin=float(getattr(info, "margin", 0.0)),
            margin_free=float(getattr(info, "margin_free", 0.0)),
            trade_allowed=bool(getattr(info, "trade_allowed", False)),
        )

    def symbols(self) -> list[str]:
        mt5 = self._module()
        rows = mt5.symbols_get() or ()
        return [str(row.name) for row in rows]

    def positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        mt5 = self._module()
        rows = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        return [row._asdict() for row in (rows or ())]

    def history(self, days: int = 30) -> list[dict[str, Any]]:
        mt5 = self._module()
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, days))
        rows = mt5.history_deals_get(start, end) or ()
        return [row._asdict() for row in rows]

    def buy(self, symbol: str, volume: float, *, sl: float = 0.0, tp: float = 0.0,
            deviation: int = 20, armed: bool = False) -> MT5OrderResult:
        return self._market_order(
            symbol=symbol, volume=volume, side="BUY", sl=sl, tp=tp,
            deviation=deviation, armed=armed,
        )

    def sell(self, symbol: str, volume: float, *, sl: float = 0.0, tp: float = 0.0,
             deviation: int = 20, armed: bool = False) -> MT5OrderResult:
        return self._market_order(
            symbol=symbol, volume=volume, side="SELL", sl=sl, tp=tp,
            deviation=deviation, armed=armed,
        )

    def _market_order(self, *, symbol: str, volume: float, side: str, sl: float,
                      tp: float, deviation: int, armed: bool) -> MT5OrderResult:
        if not armed:
            raise MT5ExecutionError(
                "Execução real desarmada. Ative explicitamente a execução antes de enviar ordens."
            )
        if volume <= 0:
            raise MT5ExecutionError("O volume deve ser maior que zero.")
        mt5 = self._module()
        account = self.account()
        if not account.trade_allowed:
            raise MT5ExecutionError("A conta/terminal MT5 não está autorizado a negociar.")
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5ExecutionError(f"Ativo {symbol} não encontrado no MT5.")
        if not info.visible and not mt5.symbol_select(symbol, True):
            raise MT5ExecutionError(f"Não foi possível habilitar {symbol} no Market Watch.")
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5ExecutionError(f"Sem cotação atual para {symbol}.")
        is_buy = side == "BUY"
        price = float(tick.ask if is_buy else tick.bid)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": float(sl or 0.0),
            "tp": float(tp or 0.0),
            "deviation": int(deviation),
            "magic": self.MAGIC,
            "comment": "Prime Trader",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(mt5, info),
        }
        checked = mt5.order_check(request)
        if checked is None:
            raise MT5ExecutionError(f"Falha ao validar ordem: {mt5.last_error()}")
        check_retcode = int(getattr(checked, "retcode", 0))
        accepted_checks = {0, int(getattr(mt5, "TRADE_RETCODE_DONE", 10009))}
        if check_retcode not in accepted_checks:
            raise MT5ExecutionError(
                f"A corretora/MT5 recusou a validação da ordem: {getattr(checked, 'comment', check_retcode)}"
            )
        result = mt5.order_send(request)
        return self._result_or_raise(mt5, result)

    def close_position(self, ticket: int, *, deviation: int = 20,
                       armed: bool = False) -> MT5OrderResult:
        if not armed:
            raise MT5ExecutionError("Execução real desarmada.")
        mt5 = self._module()
        rows = mt5.positions_get(ticket=int(ticket)) or ()
        if not rows:
            raise MT5ExecutionError(f"Posição {ticket} não encontrada.")
        position = rows[0]
        symbol = str(position.symbol)
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            raise MT5ExecutionError(f"Sem dados de mercado para encerrar {symbol}.")
        closing_buy = int(position.type) == int(mt5.POSITION_TYPE_SELL)
        price = float(tick.ask if closing_buy else tick.bid)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(position.ticket),
            "symbol": symbol,
            "volume": float(position.volume),
            "type": mt5.ORDER_TYPE_BUY if closing_buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": int(deviation),
            "magic": self.MAGIC,
            "comment": "Prime Trader close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(mt5, info),
        }
        result = mt5.order_send(request)
        return self._result_or_raise(mt5, result)

    @staticmethod
    def _filling_mode(mt5, info) -> int:
        value = int(getattr(info, "filling_mode", -1))
        known = {
            int(getattr(mt5, "ORDER_FILLING_FOK", 0)),
            int(getattr(mt5, "ORDER_FILLING_IOC", 1)),
            int(getattr(mt5, "ORDER_FILLING_RETURN", 2)),
        }
        return value if value in known else int(getattr(mt5, "ORDER_FILLING_RETURN", 2))

    @staticmethod
    def _result_or_raise(mt5, result) -> MT5OrderResult:
        if result is None:
            raise MT5ExecutionError(f"MT5 não retornou resultado: {mt5.last_error()}")
        retcode = int(getattr(result, "retcode", -1))
        done_codes = {
            int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)),
            int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)),
        }
        if retcode not in done_codes:
            raise MT5ExecutionError(
                f"Ordem não executada ({retcode}): {getattr(result, 'comment', '')}"
            )
        return MT5OrderResult(
            ok=True,
            retcode=retcode,
            order=int(getattr(result, "order", 0)) or None,
            deal=int(getattr(result, "deal", 0)) or None,
            volume=float(getattr(result, "volume", 0.0)),
            price=float(getattr(result, "price", 0.0)),
            comment=str(getattr(result, "comment", "")),
        )
