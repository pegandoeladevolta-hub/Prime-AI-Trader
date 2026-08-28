from __future__ import annotations

import asyncio
from typing import Any

from .mt5 import MT5ExecutionError, MT5OrderResult
from .mt5_robust import MT5Bridge as RobustMT5Bridge


class MT5Bridge(RobustMT5Bridge):
    """Ponte robusta com fechamento correto de candles e edição de posições."""

    async def stream_candles(self, symbol: str, timeframe: str, callback, stop_event) -> None:
        """Entrega tanto o candle em formação quanto o fechamento real ao motor.

        A implementação antiga publicava apenas ``candles[-1]``. Na virada do
        minuto o MT5 já passava a retornar a vela nova em ``[-1]`` e a vela que
        acabou de fechar ficava em ``[-2]``; por isso o SignalEngine quase nunca
        recebia ``closed=True`` e permanecia em SINAL EM FORMAÇÃO.
        """
        last_current_open = None
        last_current_signature = None
        last_closed_emitted = None

        while not stop_event.is_set():
            try:
                candles = self.fetch_candles(symbol, timeframe, limit=3)
                if candles:
                    current = candles[-1]

                    # Quando nasce uma nova vela, entrega primeiro a vela anterior
                    # já fechada. Isso é o gatilho de CONFIRMADO e da autoexecução.
                    if last_current_open is not None and current.open_time != last_current_open:
                        previous = next(
                            (
                                candle for candle in reversed(candles[:-1])
                                if candle.open_time == last_current_open
                            ),
                            None,
                        )
                        if (
                            previous is not None
                            and previous.closed
                            and previous.open_time != last_closed_emitted
                        ):
                            callback(previous)
                            last_closed_emitted = previous.open_time

                    signature = (
                        current.open_time,
                        current.open,
                        current.high,
                        current.low,
                        current.close,
                        current.volume,
                        current.closed,
                    )
                    if signature != last_current_signature:
                        callback(current)
                        last_current_signature = signature
                        if current.closed:
                            last_closed_emitted = current.open_time

                    last_current_open = current.open_time

                await asyncio.sleep(0.50)
            except Exception:
                # Mantém o stream vivo em falhas transitórias do terminal.
                await asyncio.sleep(1.25)

    def modify_position_protection(
        self, ticket: int, *, sl: float, tp: float, armed: bool = False,
    ) -> MT5OrderResult:
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
            raise MT5ExecutionError(f"Sem dados atuais de {symbol} para ajustar SL/TP.")

        digits = int(getattr(info, "digits", 0) or 0)
        point = float(getattr(info, "point", 0.0) or 0.0)
        stops_level = int(getattr(info, "trade_stops_level", 0) or 0)
        freeze_level = int(getattr(info, "trade_freeze_level", 0) or 0)
        minimum_points = max(stops_level, freeze_level)
        is_buy = int(position.type) == int(mt5.POSITION_TYPE_BUY)
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        reference = bid if is_buy else ask
        if reference <= 0 or point <= 0:
            raise MT5ExecutionError(f"Cotação inválida de {symbol} para ajustar proteção.")

        sl = round(float(sl or 0.0), digits) if sl else 0.0
        tp = round(float(tp or 0.0), digits) if tp else 0.0
        minimum_distance = minimum_points * point

        if is_buy:
            if sl and sl >= reference:
                raise MT5ExecutionError("Em uma compra, o Stop Loss precisa ficar abaixo do preço atual.")
            if tp and tp <= reference:
                raise MT5ExecutionError("Em uma compra, o Take Profit precisa ficar acima do preço atual.")
            if sl and minimum_distance and reference - sl < minimum_distance:
                raise MT5ExecutionError(
                    f"Stop Loss muito próximo. O servidor exige ao menos {minimum_points} pontos."
                )
            if tp and minimum_distance and tp - reference < minimum_distance:
                raise MT5ExecutionError(
                    f"Take Profit muito próximo. O servidor exige ao menos {minimum_points} pontos."
                )
        else:
            if sl and sl <= reference:
                raise MT5ExecutionError("Em uma venda, o Stop Loss precisa ficar acima do preço atual.")
            if tp and tp >= reference:
                raise MT5ExecutionError("Em uma venda, o Take Profit precisa ficar abaixo do preço atual.")
            if sl and minimum_distance and sl - reference < minimum_distance:
                raise MT5ExecutionError(
                    f"Stop Loss muito próximo. O servidor exige ao menos {minimum_points} pontos."
                )
            if tp and minimum_distance and reference - tp < minimum_distance:
                raise MT5ExecutionError(
                    f"Take Profit muito próximo. O servidor exige ao menos {minimum_points} pontos."
                )

        request: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(position.ticket),
            "symbol": symbol,
            "sl": sl,
            "tp": tp,
            "magic": self.MAGIC,
            "comment": "Prime Trader protection",
        }
        result = mt5.order_send(request)
        return self._result_or_raise(mt5, result)


__all__ = ["MT5Bridge"]
