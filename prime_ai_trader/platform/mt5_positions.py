from __future__ import annotations

from typing import Any

from .mt5 import MT5ExecutionError, MT5OrderResult
from .mt5_robust import MT5Bridge as RobustMT5Bridge


class MT5Bridge(RobustMT5Bridge):
    """Ponte robusta com edição de proteção de posições abertas."""

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
