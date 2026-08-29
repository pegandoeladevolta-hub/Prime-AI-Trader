from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..app.mt5_profiles import REAL, SIMULATOR, classify_account_environment
from .mt5 import MT5ExecutionError, MT5UnavailableError
from .mt5_positions import MT5Bridge as BaseMT5Bridge


class MT5Bridge(BaseMT5Bridge):
    """Ponte MT5 com seleção explícita de ambiente REAL ou SIMULADOR.

    O login pode ser fornecido pelo Prime Trader ao pacote oficial MetaTrader5.
    A senha nunca é incluída em mensagens, logs ou diagnóstico de erro.
    """

    def __init__(self, terminal_path=None, *, environment: str = REAL) -> None:
        super().__init__(terminal_path)
        self.environment = environment if environment in {REAL, SIMULATOR} else REAL
        self._login: int | None = None
        self._password = ""
        self._server = ""

    def set_environment(self, environment: str, terminal_path: str | Path | None = None) -> None:
        if environment not in {REAL, SIMULATOR}:
            raise ValueError(f"Ambiente MT5 inválido: {environment}")
        if self.connected:
            self.disconnect()
        self.environment = environment
        self.terminal_path = str(terminal_path) if terminal_path else None

    def set_credentials(self, *, login: int | None, password: str = "", server: str = "") -> None:
        """Define credenciais somente em memória para a próxima conexão."""
        if self.connected:
            self.disconnect()
        try:
            self._login = int(login) if login else None
        except (TypeError, ValueError):
            self._login = None
        self._password = str(password or "")
        self._server = str(server or "").strip()

    def credentials_configured(self) -> bool:
        return bool(self._login and self._password and self._server)

    @staticmethod
    def _simulator_path(path: Path) -> bool:
        text = str(path).lower()
        return any(token in text for token in ("simul", "demo", "practice"))

    def discover_for_environment(self, configured: str | Path | None = None) -> list[Path]:
        paths = list(super().discover_terminal_paths(configured))
        if not paths:
            return []

        configured_key = self._path_key(configured) if configured else ""
        wanted_simulator = self.environment == SIMULATOR

        def score(path: Path) -> tuple[int, str]:
            text = str(path).lower()
            is_sim = self._simulator_path(path)
            value = 0
            if "clear" in text:
                value += 1000
            if is_sim == wanted_simulator:
                value += 700
            elif is_sim:
                value -= 500
            if configured_key and self._path_key(path) == configured_key:
                value += 900
            if path.name.lower() == "terminal64.exe":
                value += 20
            return (-value, text)

        return sorted(paths, key=score)

    def _connection_kwargs(self, candidate: Path | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if candidate is not None:
            kwargs["path"] = str(candidate)
        if self.credentials_configured():
            kwargs["login"] = int(self._login or 0)
            kwargs["password"] = self._password
            kwargs["server"] = self._server
        return kwargs

    def connect(self):
        mt5 = self._module()
        candidates = self.discover_for_environment(self.terminal_path)
        paths: list[Path | None] = list(candidates) if candidates else [None]
        attempts: list[str] = []
        auth_failed = False
        mismatch = False

        for candidate in paths:
            try:
                mt5.shutdown()
            except Exception:
                pass

            kwargs = self._connection_kwargs(candidate)
            initialized = bool(mt5.initialize(**kwargs))
            error = mt5.last_error()
            if not initialized and candidate is not None:
                try:
                    code = int(error[0])
                except Exception:
                    code = 0
                auth_failed = auth_failed or code == -6
                self._launch_terminal(candidate)
                time.sleep(1.4)
                initialized = bool(mt5.initialize(**kwargs))
                error = mt5.last_error()

            label = str(candidate) if candidate is not None else "autodetecção MetaTrader5"
            if not initialized:
                try:
                    code = int(error[0])
                except Exception:
                    code = 0
                auth_failed = auth_failed or code == -6
                attempts.append(f"{label}: {error}")
                continue

            info = mt5.account_info()
            if info is None:
                attempts.append(f"{label}: terminal aberto, mas sem conta autenticada")
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                continue

            actual_login = int(getattr(info, "login", 0) or 0)
            if self._login and actual_login != int(self._login):
                mismatch = True
                attempts.append(
                    f"{label}: conta {actual_login} autenticada, mas o perfil selecionado espera a conta {self._login}"
                )
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                continue

            server = str(getattr(info, "server", "") or "")
            name = str(getattr(info, "name", "") or "")
            detected = classify_account_environment(server, name)
            if detected != self.environment:
                mismatch = True
                attempts.append(
                    f"{label}: sessão autenticada como {detected}, mas o Prime Trader está em {self.environment}"
                )
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                continue

            self.connected = True
            if candidate is not None:
                self.terminal_path = str(candidate)
            return self._account_snapshot(info)

        self.connected = False
        details = "\n".join(attempts[-4:]) if attempts else str(mt5.last_error())
        if mismatch:
            wanted = "conta de SIMULAÇÃO/DEMO" if self.environment == SIMULATOR else "conta REAL"
            raise MT5UnavailableError(
                f"O MT5 abriu, mas a sessão ativa não corresponde ao perfil {self.environment}.\n\n"
                f"O Prime Trader tentou entrar automaticamente na {wanted} cadastrada. "
                "Confira LOGIN, SERVIDOR e SENHA em CONTAS / LOGIN MT5.\n\n"
                f"Diagnóstico:\n{details}"
            )
        if auth_failed or any("sem conta autenticada" in item for item in attempts):
            hint = (
                "Confira se o MetaTrader 5 (Simulador) está ativo na Clear e se LOGIN/SENHA/SERVIDOR DEMO estão corretos."
                if self.environment == SIMULATOR
                else "Confira se o MetaTrader 5 real está ativo na Clear e se LOGIN/SENHA/SERVIDOR REAL estão corretos."
            )
            raise MT5UnavailableError(
                f"Não foi possível autenticar automaticamente o perfil {self.environment}.\n\n"
                f"{hint}\n\nDiagnóstico:\n{details}"
            )
        raise MT5UnavailableError(
            f"Não foi possível conectar ao perfil {self.environment}.\n\n"
            "Selecione manualmente o terminal64.exe correspondente e confira as credenciais cadastradas.\n\n"
            f"Diagnóstico:\n{details}"
        )

    def estimate_trade_profit(self, symbol: str, side: str, volume: float,
                              open_price: float, close_price: float) -> float | None:
        """P/L estimado na moeda da conta usando a fórmula oficial do terminal."""
        if volume <= 0 or open_price <= 0 or close_price <= 0:
            return None
        self._ensure_connected()
        mt5 = self._module()
        order_type = mt5.ORDER_TYPE_BUY if str(side).upper() in {"BUY", "COMPRA"} else mt5.ORDER_TYPE_SELL
        value = mt5.order_calc_profit(
            order_type, str(symbol), float(volume), float(open_price), float(close_price)
        )
        return None if value is None else float(value)


__all__ = ["MT5Bridge"]
