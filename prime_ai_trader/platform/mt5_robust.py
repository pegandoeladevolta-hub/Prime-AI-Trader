from __future__ import annotations

from typing import Any

from .mt5 import (
    MT5AccountSnapshot,
    MT5Bridge as BaseMT5Bridge,
    MT5ExecutionError,
    MT5OrderResult,
    MT5UnavailableError,
)


class MT5Bridge(BaseMT5Bridge):
    """Ponte MT5 com negociação adaptativa por símbolo/servidor.

    O campo ``SYMBOL_FILLING_MODE`` do MT5 é uma máscara de capacidades e não
    deve ser enviado diretamente como ``ORDER_FILLING_*``. Esta classe resolve
    as políticas aceitas pelo ativo, valida cada alternativa e só então envia a
    ordem, evitando o erro comum ``Unsupported filling mode``.
    """

    def symbol_details(self, symbol: str) -> dict[str, Any]:
        details = super().symbol_details(symbol)
        self._ensure_connected()
        info = self._module().symbol_info(symbol)
        if info is None:
            return details
        details.update({
            "point": float(getattr(info, "point", 0.0) or 0.0),
            "digits": int(getattr(info, "digits", 0) or 0),
            "volume_min": float(getattr(info, "volume_min", 0.0) or 0.0),
            "volume_max": float(getattr(info, "volume_max", 0.0) or 0.0),
            "volume_step": float(getattr(info, "volume_step", 0.0) or 0.0),
            "trade_stops_level": int(getattr(info, "trade_stops_level", 0) or 0),
            "filling_mode": int(getattr(info, "filling_mode", 0) or 0),
            "trade_exemode": int(getattr(info, "trade_exemode", -1)),
        })
        return details

    def manual_protection_from_points(
        self, symbol: str, side: str, sl_points: float, tp_points: float,
    ) -> tuple[float, float]:
        """Converte distâncias em pontos do ativo para preços absolutos de SL/TP."""
        self._ensure_connected()
        mt5 = self._module()
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            raise MT5ExecutionError(f"Sem dados do ativo {symbol} para calcular SL/TP.")

        point = float(getattr(info, "point", 0.0) or 0.0)
        digits = int(getattr(info, "digits", 0) or 0)
        if point <= 0:
            raise MT5ExecutionError(f"O MT5 não informou o tamanho do ponto de {symbol}.")

        minimum = int(getattr(info, "trade_stops_level", 0) or 0)
        for label, value in (("SL", sl_points), ("TP", tp_points)):
            if value < 0:
                raise MT5ExecutionError(f"{label} em pontos não pode ser negativo.")
            if value > 0 and minimum > 0 and value < minimum:
                raise MT5ExecutionError(
                    f"{label} muito próximo para {symbol}: o servidor exige pelo menos "
                    f"{minimum} pontos."
                )

        is_buy = str(side).upper() == "BUY"
        base_price = float(tick.ask if is_buy else tick.bid)
        if base_price <= 0:
            raise MT5ExecutionError(f"Cotação inválida de {symbol} para calcular SL/TP.")

        sl = 0.0
        tp = 0.0
        if sl_points > 0:
            sl = base_price - sl_points * point if is_buy else base_price + sl_points * point
        if tp_points > 0:
            tp = base_price + tp_points * point if is_buy else base_price - tp_points * point
        return round(sl, digits) if sl else 0.0, round(tp, digits) if tp else 0.0

    @staticmethod
    def _append_unique(values: list[int], value: int) -> None:
        if value not in values:
            values.append(value)

    def _filling_candidates(self, mt5, info) -> list[int]:
        """Retorna ORDER_FILLING_* válidos em ordem de preferência.

        ``info.filling_mode`` contém flags SYMBOL_FILLING_FOK/IOC. RETURN não é
        permitido para símbolos com Market Execution.
        """
        order_fok = int(getattr(mt5, "ORDER_FILLING_FOK", 0))
        order_ioc = int(getattr(mt5, "ORDER_FILLING_IOC", 1))
        order_return = int(getattr(mt5, "ORDER_FILLING_RETURN", 2))
        flag_fok = int(getattr(mt5, "SYMBOL_FILLING_FOK", 1))
        flag_ioc = int(getattr(mt5, "SYMBOL_FILLING_IOC", 2))
        flags = int(getattr(info, "filling_mode", 0) or 0)
        execution = int(getattr(info, "trade_exemode", -1))
        market_execution = int(getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2))

        result: list[int] = []
        if flags & flag_fok:
            self._append_unique(result, order_fok)
        if flags & flag_ioc:
            self._append_unique(result, order_ioc)

        # Alguns servidores reportam flags incompletas. A validação order_check
        # abaixo permite tentar os demais sem enviar uma ordem inválida.
        self._append_unique(result, order_ioc)
        self._append_unique(result, order_fok)
        if execution != market_execution:
            self._append_unique(result, order_return)
        return result

    @staticmethod
    def _fill_name(mt5, value: int) -> str:
        names = {
            int(getattr(mt5, "ORDER_FILLING_FOK", 0)): "FOK",
            int(getattr(mt5, "ORDER_FILLING_IOC", 1)): "IOC",
            int(getattr(mt5, "ORDER_FILLING_RETURN", 2)): "RETURN",
        }
        return names.get(int(value), str(value))

    @staticmethod
    def _unsupported_fill(mt5, response) -> bool:
        if response is None:
            return False
        retcode = int(getattr(response, "retcode", -1))
        invalid_fill = int(getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030))
        text = str(getattr(response, "comment", "") or "").lower()
        return retcode == invalid_fill or any(token in text for token in (
            "unsupported filling", "unsupported fill", "invalid filling",
            "invalid fill", "filling mode",
        ))

    def _send_with_supported_filling(self, base_request: dict[str, Any], info) -> MT5OrderResult:
        mt5 = self._module()
        accepted_checks = {0, int(getattr(mt5, "TRADE_RETCODE_DONE", 10009))}
        attempts: list[str] = []

        for filling in self._filling_candidates(mt5, info):
            request = dict(base_request)
            request["type_filling"] = filling
            fill_name = self._fill_name(mt5, filling)

            checked = mt5.order_check(request)
            if checked is None:
                attempts.append(f"{fill_name}: validação sem resposta")
                continue
            check_code = int(getattr(checked, "retcode", -1))
            if check_code not in accepted_checks:
                comment = str(getattr(checked, "comment", check_code))
                attempts.append(f"{fill_name}: {comment}")
                if self._unsupported_fill(mt5, checked):
                    continue
                # Erros de margem, volume, stops, mercado fechado etc. não devem
                # ser mascarados por tentativas de outro filling mode.
                raise MT5ExecutionError(
                    f"A corretora/MT5 recusou a validação da ordem: {comment}"
                )

            result = mt5.order_send(request)
            if result is None:
                attempts.append(f"{fill_name}: MT5 sem resposta")
                continue
            if self._unsupported_fill(mt5, result):
                attempts.append(
                    f"{fill_name}: {getattr(result, 'comment', 'filling não aceito')}"
                )
                continue
            return self._result_or_raise(mt5, result)

        detail = " | ".join(attempts[-4:]) or "nenhuma política disponível"
        raise MT5ExecutionError(
            "O ativo não aceitou nenhum modo de preenchimento disponível no MT5. "
            f"Tentativas: {detail}"
        )

    def _market_order(
        self, *, symbol: str, volume: float, side: str, sl: float,
        tp: float, deviation: int, armed: bool,
    ) -> MT5OrderResult:
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
        if not bool(getattr(info, "visible", False)) and not mt5.symbol_select(symbol, True):
            raise MT5ExecutionError(f"Não foi possível habilitar {symbol} no Market Watch.")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5ExecutionError(f"Sem cotação atual para {symbol}.")
        is_buy = str(side).upper() == "BUY"
        price = float(tick.ask if is_buy else tick.bid)
        if price <= 0:
            raise MT5ExecutionError(f"Preço inválido para {symbol}.")

        request: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "sl": float(sl or 0.0),
            "tp": float(tp or 0.0),
            "deviation": int(deviation),
            "magic": self.MAGIC,
            "comment": "Prime Trader",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        execution = int(getattr(info, "trade_exemode", -1))
        market_execution = int(getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2))
        # No modo Market Execution o servidor define o preço; nos demais modos o
        # preço atual faz parte da requisição.
        if execution != market_execution:
            request["price"] = price

        return self._send_with_supported_filling(request, info)

    def close_position(
        self, ticket: int, *, deviation: int = 20, armed: bool = False,
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
            raise MT5ExecutionError(f"Sem dados de mercado para encerrar {symbol}.")

        closing_buy = int(position.type) == int(mt5.POSITION_TYPE_SELL)
        price = float(tick.ask if closing_buy else tick.bid)
        request: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(position.ticket),
            "symbol": symbol,
            "volume": float(position.volume),
            "type": mt5.ORDER_TYPE_BUY if closing_buy else mt5.ORDER_TYPE_SELL,
            "deviation": int(deviation),
            "magic": self.MAGIC,
            "comment": "Prime Trader close",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        execution = int(getattr(info, "trade_exemode", -1))
        market_execution = int(getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2))
        if execution != market_execution:
            request["price"] = price
        return self._send_with_supported_filling(request, info)


__all__ = [
    "MT5Bridge", "MT5AccountSnapshot", "MT5ExecutionError",
    "MT5OrderResult", "MT5UnavailableError",
]
