from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ..core.models import Candle


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
    """Ponte única entre o Prime Trader e o terminal MetaTrader 5 local.

    Além de enviar/encerrar ordens, esta classe fornece os símbolos, ticks e
    candles usados pelo gráfico e pelo motor de sinais. Assim o Prime Trader não
    precisa misturar o preço do MT5 com Yahoo/Binance.
    """

    MAGIC = 260826
    name = "MetaTrader 5"
    last_provider_name = "MetaTrader 5"
    last_warning = ""
    recommended_poll_ms = 2_000
    recommended_quote_ms = 1_000

    _TIMEFRAME_SECONDS = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900,
        "30m": 1800, "1h": 3600, "4h": 14400,
    }

    def __init__(self, terminal_path: str | Path | None = None) -> None:
        self.terminal_path = str(terminal_path) if terminal_path else None
        self._mt5 = None
        self.connected = False
        self.reference = self

    def _module(self):
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:
            raise MT5UnavailableError(
                "O conector MetaTrader5 não está instalado. Mantenha o MetaTrader 5 "
                "instalado no Windows e reinstale o Prime Trader."
            ) from exc
        self._mt5 = mt5
        return mt5

    def _ensure_connected(self) -> None:
        if self.connected:
            mt5 = self._module()
            if mt5.account_info() is not None:
                return
            self.connected = False
        self.connect()

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
                "O MT5 foi encontrado, mas não existe conta autenticada no terminal. "
                "Entre na conta dentro do MetaTrader 5 e conecte novamente."
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
        self._ensure_connected()
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

    def _timeframe_constant(self, timeframe: str) -> int:
        mt5 = self._module()
        names = {
            "1m": "TIMEFRAME_M1", "3m": "TIMEFRAME_M3", "5m": "TIMEFRAME_M5",
            "15m": "TIMEFRAME_M15", "30m": "TIMEFRAME_M30",
            "1h": "TIMEFRAME_H1", "4h": "TIMEFRAME_H4",
        }
        name = names.get(timeframe)
        if not name or not hasattr(mt5, name):
            raise MT5UnavailableError(f"Time frame {timeframe} não é suportado pelo MT5.")
        return int(getattr(mt5, name))

    @staticmethod
    def _rate_value(row, key: str, default: float = 0.0):
        try:
            return row[key]
        except Exception:
            return getattr(row, key, default)

    def fetch_candles(
        self, symbol: str, timeframe: str, limit: int = 500,
        start: datetime | None = None, end: datetime | None = None,
    ) -> list[Candle]:
        self._ensure_connected()
        mt5 = self._module()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5UnavailableError(
                f"O ativo {symbol} não existe na conta/servidor MT5 conectado."
            )
        if not bool(getattr(info, "visible", False)):
            if not mt5.symbol_select(symbol, True):
                raise MT5UnavailableError(f"Não foi possível ativar {symbol} no Market Watch.")
        tf = self._timeframe_constant(timeframe)
        if start is not None and end is not None and hasattr(mt5, "copy_rates_range"):
            rows = mt5.copy_rates_range(symbol, tf, start, end)
        else:
            rows = mt5.copy_rates_from_pos(symbol, tf, 0, max(2, int(limit)))
            # Em um ativo recém-aberto, o terminal pode devolver só as barras já
            # carregadas no gráfico (como 108/200). Uma consulta por intervalo
            # solicita ao servidor da corretora o trecho anterior sem inventar
            # candles nem reduzir o mínimo analítico.
            minimum = min(200, max(2, int(limit)))
            if (
                (rows is None or len(rows) < minimum)
                and hasattr(mt5, "copy_rates_range")
            ):
                history_end = datetime.now(timezone.utc)
                span_days = max(
                    30,
                    min(3650, int(self._TIMEFRAME_SECONDS[timeframe] * int(limit) / 86400 * 6) + 1),
                )
                ranged = mt5.copy_rates_range(
                    symbol, tf, history_end - timedelta(days=span_days), history_end,
                )
                if ranged is not None and (rows is None or len(ranged) > len(rows)):
                    rows = ranged
        if rows is None or len(rows) == 0:
            raise MT5UnavailableError(
                f"O MT5 não retornou candles de {symbol} em {timeframe}: {mt5.last_error()}"
            )
        if len(rows) > int(limit):
            rows = rows[-int(limit):]
        seconds = self._TIMEFRAME_SECONDS[timeframe]
        now = datetime.now(timezone.utc)
        result: list[Candle] = []
        for row in rows:
            opened = datetime.fromtimestamp(int(self._rate_value(row, "time")), tz=timezone.utc)
            theoretical_close = opened + timedelta(seconds=seconds)
            closed = theoretical_close <= now
            real_volume = float(self._rate_value(row, "real_volume", 0.0) or 0.0)
            tick_volume = float(self._rate_value(row, "tick_volume", 0.0) or 0.0)
            result.append(Candle(
                open_time=opened,
                open=float(self._rate_value(row, "open")),
                high=float(self._rate_value(row, "high")),
                low=float(self._rate_value(row, "low")),
                close=float(self._rate_value(row, "close")),
                volume=real_volume if real_volume > 0 else tick_volume,
                close_time=theoretical_close if closed else None,
                quote_volume=0.0,
                trades=int(tick_volume),
                taker_buy_volume=0.0,
                closed=closed,
            ))
        return result[-int(limit):]

    async def stream_candles(
        self, symbol: str, timeframe: str, callback: Callable[[Candle], None], stop_event,
    ) -> None:
        """Atualiza o candle diretamente do terminal MT5, sem Binance/Yahoo."""
        last_signature = None
        while not stop_event.is_set():
            try:
                candles = self.fetch_candles(symbol, timeframe, limit=2)
                if candles:
                    candle = candles[-1]
                    signature = (
                        candle.open_time, candle.open, candle.high, candle.low,
                        candle.close, candle.volume, candle.closed,
                    )
                    if signature != last_signature:
                        last_signature = signature
                        callback(candle)
                await asyncio.sleep(0.75)
            except Exception:
                await asyncio.sleep(2.0)

    def test_connection(self) -> tuple[bool, float | None, str]:
        started = time.perf_counter()
        try:
            account = self.connect()
            return True, (time.perf_counter() - started) * 1000, f"{account.server} • {account.login}"
        except Exception as exc:
            return False, None, str(exc)

    def symbols(self) -> list[str]:
        return self.list_symbols()

    def list_symbols(self) -> list[str]:
        self._ensure_connected()
        mt5 = self._module()
        rows = mt5.symbols_get() or ()
        enabled: list[tuple[int, str]] = []
        disabled_mode = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", None)
        for row in rows:
            name = str(getattr(row, "name", "")).strip()
            if not name:
                continue
            trade_mode = getattr(row, "trade_mode", None)
            if disabled_mode is not None and trade_mode == disabled_mode:
                continue
            visible_rank = 0 if bool(getattr(row, "visible", False)) else 1
            enabled.append((visible_rank, name))
        return [name for _, name in sorted(set(enabled), key=lambda item: (item[0], item[1]))]

    def symbol_details(self, symbol: str) -> dict[str, Any]:
        self._ensure_connected()
        mt5 = self._module()
        info = mt5.symbol_info(symbol)
        if info is None:
            return {}
        return {
            "name": str(getattr(info, "name", symbol)),
            "description": str(getattr(info, "description", "")),
            "path": str(getattr(info, "path", "")),
            "currency_base": str(getattr(info, "currency_base", "")),
            "currency_profit": str(getattr(info, "currency_profit", "")),
            "visible": bool(getattr(info, "visible", False)),
            "trade_mode": int(getattr(info, "trade_mode", 0)),
        }

    def tick(self, symbol: str) -> dict[str, float]:
        self._ensure_connected()
        mt5 = self._module()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5UnavailableError(f"Sem cotação atual para {symbol}.")
        return {
            "bid": float(getattr(tick, "bid", 0.0)),
            "ask": float(getattr(tick, "ask", 0.0)),
            "last": float(getattr(tick, "last", 0.0)),
            "time": float(getattr(tick, "time", 0.0)),
        }

    def fetch_reference_rate(self, symbol: str) -> float | None:
        values = self.tick(symbol)
        bid, ask, last = values["bid"], values["ask"], values["last"]
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return last if last > 0 else bid if bid > 0 else ask if ask > 0 else None

    def positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        self._ensure_connected()
        mt5 = self._module()
        rows = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        return [row._asdict() for row in (rows or ())]

    def history(self, days: int = 30) -> list[dict[str, Any]]:
        self._ensure_connected()
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
        self._ensure_connected()
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
        self._ensure_connected()
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
