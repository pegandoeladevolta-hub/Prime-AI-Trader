from __future__ import annotations

from pathlib import Path

from ..app.mt5_profiles import REAL, SIMULATOR, classify_account_environment
from .mt5_positions import MT5Bridge as BaseMT5Bridge


class MT5Bridge(BaseMT5Bridge):
    """Conecta somente à sessão já autenticada no MetaTrader 5 da Clear.

    Login, servidor e senha são administrados exclusivamente pelo terminal MT5.
    Depois da conexão, o servidor da conta define automaticamente se a sessão é
    REAL ou SIMULADOR; o Prime Trader nunca tenta trocar ou autenticar a conta.
    """

    def __init__(self, terminal_path=None, *, environment: str = REAL) -> None:
        super().__init__(terminal_path)
        self.environment = environment if environment in {REAL, SIMULATOR} else REAL

    def set_environment(
        self, environment: str, terminal_path: str | Path | None = None,
    ) -> None:
        """Mantém o último ambiente apenas até o MT5 informar a conta real."""
        if environment not in {REAL, SIMULATOR}:
            raise ValueError(f"Ambiente MT5 inválido: {environment}")
        if self.connected:
            self.disconnect()
        self.environment = environment
        self.terminal_path = str(terminal_path) if terminal_path else None

    def connect(self):
        account = super().connect()
        self.environment = classify_account_environment(account.server, account.name)
        return account

    def estimate_trade_profit(
        self, symbol: str, side: str, volume: float,
        open_price: float, close_price: float,
    ) -> float | None:
        """P/L estimado na moeda da conta usando a fórmula oficial do terminal."""
        if volume <= 0 or open_price <= 0 or close_price <= 0:
            return None
        self._ensure_connected()
        mt5 = self._module()
        order_type = (
            mt5.ORDER_TYPE_BUY
            if str(side).upper() in {"BUY", "COMPRA"}
            else mt5.ORDER_TYPE_SELL
        )
        value = mt5.order_calc_profit(
            order_type, str(symbol), float(volume),
            float(open_price), float(close_price),
        )
        return None if value is None else float(value)


__all__ = ["MT5Bridge"]
