from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..app.mt5_profiles import REAL, SIMULATOR, classify_account_environment
from .mt5 import MT5ExecutionError, MT5UnavailableError
from .mt5_positions import MT5Bridge as BaseMT5Bridge


class MT5ProfileMismatchError(MT5UnavailableError):
    """Sessão aberta pertence a outro ambiente/conta, sem expor credenciais."""

    def __init__(self, message: str, *, expected_environment: str,
                 detected_environment: str, detected_login: int | None,
                 credentials_configured: bool) -> None:
        super().__init__(message)
        self.expected_environment = expected_environment
        self.detected_environment = detected_environment
        self.detected_login = detected_login
        self.credentials_configured = credentials_configured


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
        detected_environment = ""
        detected_login: int | None = None

        def error_code(error: object) -> int:
            try:
                return int(error[0])  # type: ignore[index]
            except Exception:
                return 0

        def accept_active_account(info: object, candidate: Path | None,
                                  label: str, phase: str):
            nonlocal mismatch, detected_environment, detected_login
            if info is None:
                attempts.append(f"{label} ({phase}): terminal aberto, mas sem conta autenticada")
                return None

            actual_login = int(getattr(info, "login", 0) or 0)
            server = str(getattr(info, "server", "") or "")
            name = str(getattr(info, "name", "") or "")
            detected = classify_account_environment(server, name)
            if self._login and actual_login != int(self._login):
                mismatch = True
                detected_environment = detected
                detected_login = actual_login or None
                attempts.append(
                    f"{label} ({phase}): conta {actual_login} autenticada, "
                    f"mas o perfil selecionado espera a conta {self._login}"
                )
                return None

            if detected != self.environment:
                mismatch = True
                detected_environment = detected
                detected_login = actual_login or None
                attempts.append(
                    f"{label} ({phase}): sessão autenticada como {detected}, "
                    f"mas o Prime Trader está em {self.environment}"
                )
                return None

            self.connected = True
            if candidate is not None:
                self.terminal_path = str(candidate)
            return self._account_snapshot(info)

        for candidate in paths:
            try:
                mt5.shutdown()
            except Exception:
                pass

            # Primeiro anexa ao terminal já aberto sem reenviar a senha. A API
            # oficial pode recusar uma segunda autenticação (-6) mesmo quando a
            # conta correta já está conectada e recebendo cotações no MT5.
            attach_kwargs: dict[str, Any] = {}
            if candidate is not None:
                attach_kwargs["path"] = str(candidate)
            initialized = bool(mt5.initialize(**attach_kwargs))
            error = mt5.last_error()
            if not initialized and candidate is not None:
                auth_failed = auth_failed or error_code(error) == -6
                self._launch_terminal(candidate)
                time.sleep(1.4)
                initialized = bool(mt5.initialize(**attach_kwargs))
                error = mt5.last_error()

            label = str(candidate) if candidate is not None else "autodetecção MetaTrader5"
            if initialized:
                account = accept_active_account(
                    mt5.account_info(), candidate, label, "sessão ativa"
                )
                if account is not None:
                    return account
            else:
                auth_failed = auth_failed or error_code(error) == -6
                attempts.append(f"{label} (sessão ativa): {error}")

            # Só tenta login/senha quando não foi possível aproveitar exatamente
            # a conta esperada. Assim ainda é possível trocar de perfil sem
            # relaxar a validação de conta REAL versus DEMO.
            if not self.credentials_configured():
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                continue

            try:
                mt5.shutdown()
            except Exception:
                pass
            login_kwargs = self._connection_kwargs(candidate)
            initialized = bool(mt5.initialize(**login_kwargs))
            error = mt5.last_error()
            if not initialized:
                auth_failed = auth_failed or error_code(error) == -6
                attempts.append(f"{label} (login automático): {error}")
                continue

            account = accept_active_account(
                mt5.account_info(), candidate, label, "login automático"
            )
            if account is not None:
                return account
            try:
                mt5.shutdown()
            except Exception:
                pass

        self.connected = False
        details = "\n".join(attempts[-6:]) if attempts else str(mt5.last_error())
        if mismatch:
            wanted = "conta de SIMULAÇÃO/DEMO" if self.environment == SIMULATOR else "conta REAL"
            configured = self.credentials_configured()
            instruction = (
                f"Revise LOGIN, SERVIDOR e SENHA da {wanted} em CONTAS / LOGIN MT5."
                if configured else
                f"A {wanted} ainda não possui LOGIN, SERVIDOR e SENHA completos no Prime Trader."
            )
            raise MT5ProfileMismatchError(
                f"O MT5 abriu, mas a sessão ativa não corresponde ao perfil {self.environment}.\n\n"
                f"{instruction}\n\n"
                f"Você pode escolher explicitamente {detected_environment or 'a conta ativa'} "
                "ou corrigir o cadastro do perfil selecionado.\n\n"
                f"Diagnóstico:\n{details}",
                expected_environment=self.environment,
                detected_environment=detected_environment,
                detected_login=detected_login,
                credentials_configured=configured,
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


__all__ = ["MT5Bridge", "MT5ProfileMismatchError"]
