from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import SecretStore
from .mt5_profiles import REAL, SIMULATOR


_DEFAULT_SERVERS = {
    REAL: "ClearInvestimentos-CLEAR",
    SIMULATOR: "ClearInvestimentos-DEMO",
}


@dataclass(frozen=True, slots=True)
class MT5Credentials:
    login: int | None = None
    password: str = ""
    server: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.login and self.password.strip() and self.server.strip())


class MT5CredentialStore:
    """Credenciais REAL/DEMO protegidas pelo SecretStore (DPAPI no Windows).

    Nenhuma senha é escrita em settings.json ou mt5_profiles.json. O SecretStore
    usa a proteção vinculada ao usuário do Windows, e este wrapper preserva outros
    segredos que já existam no mesmo arquivo.
    """

    def __init__(self, secret_store: SecretStore | None = None) -> None:
        self.secret_store = secret_store or SecretStore()

    @staticmethod
    def _prefix(environment: str) -> str:
        return "mt5_clear_simulator" if environment == SIMULATOR else "mt5_clear_real"

    @staticmethod
    def default_server(environment: str) -> str:
        return _DEFAULT_SERVERS.get(environment, _DEFAULT_SERVERS[REAL])

    def get(self, environment: str) -> MT5Credentials:
        values = self.secret_store.load()
        prefix = self._prefix(environment)
        raw_login = str(values.get(f"{prefix}_login", "") or "").strip()
        try:
            login = int(raw_login) if raw_login else None
        except ValueError:
            login = None
        password = str(values.get(f"{prefix}_password", "") or "")
        server = str(values.get(f"{prefix}_server", "") or "").strip()
        if not server:
            server = self.default_server(environment)
        return MT5Credentials(login=login, password=password, server=server)

    def save(self, environment: str, *, login: int, password: str, server: str) -> None:
        login = int(login)
        password = str(password or "")
        server = str(server or "").strip()
        if login <= 0:
            raise ValueError("Login MT5 inválido.")
        if not password:
            raise ValueError("Informe a senha do MT5.")
        if not server:
            raise ValueError("Informe o servidor MT5.")
        values = self.secret_store.load()
        prefix = self._prefix(environment)
        values[f"{prefix}_login"] = str(login)
        values[f"{prefix}_password"] = password
        values[f"{prefix}_server"] = server
        self.secret_store.save(values)

    def clear(self, environment: str) -> None:
        values = self.secret_store.load()
        prefix = self._prefix(environment)
        for suffix in ("login", "password", "server"):
            values.pop(f"{prefix}_{suffix}", None)
        self.secret_store.save(values)


__all__ = ["MT5Credentials", "MT5CredentialStore"]
