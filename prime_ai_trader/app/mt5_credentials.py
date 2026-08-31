from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..config.settings import SecretStore
from .mt5_profiles import ENVIRONMENTS, REAL, SIMULATOR


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


class MT5CredentialPersistenceError(RuntimeError):
    """O cofre local não conseguiu reler exatamente o cadastro gravado."""


def parse_mt5_credentials(
    environment: str,
    *,
    login_text: str,
    password: str,
    server: str,
) -> MT5Credentials | None:
    """Converte uma seção do formulário sem confundir servidor padrão com conta.

    Uma seção só é considerada preenchida quando há login ou senha. Isso permite
    cadastrar apenas a conta DEMO mesmo que o campo de servidor da conta REAL
    apareça preenchido automaticamente na interface.
    """
    if environment not in ENVIRONMENTS:
        raise ValueError(f"Ambiente MT5 inválido: {environment}")
    login_value = str(login_text or "").strip()
    password_value = str(password or "")
    server_value = str(server or "").strip()
    if not login_value and not password_value.strip():
        return None
    if not login_value:
        raise ValueError(f"{environment}: informe o LOGIN MT5.")
    if not password_value.strip():
        raise ValueError(f"{environment}: informe a SENHA MT5.")
    try:
        login = int(login_value)
    except ValueError as exc:
        raise ValueError(
            f"{environment}: o LOGIN deve conter somente números."
        ) from exc
    if login <= 0:
        raise ValueError(f"{environment}: o LOGIN MT5 é inválido.")
    return MT5Credentials(
        login=login,
        password=password_value,
        server=server_value or _DEFAULT_SERVERS[environment],
    )


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
        if environment not in ENVIRONMENTS:
            raise ValueError(f"Ambiente MT5 inválido: {environment}")
        return "mt5_clear_simulator" if environment == SIMULATOR else "mt5_clear_real"

    @staticmethod
    def default_server(environment: str) -> str:
        if environment not in ENVIRONMENTS:
            raise ValueError(f"Ambiente MT5 inválido: {environment}")
        return _DEFAULT_SERVERS[environment]

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
        credentials = MT5Credentials(
            login=int(login), password=str(password or ""), server=str(server or "").strip()
        )
        self.save_profiles({environment: credentials})

    @staticmethod
    def _validated(credentials: MT5Credentials) -> MT5Credentials:
        login = int(credentials.login or 0)
        password = str(credentials.password or "")
        server = str(credentials.server or "").strip()
        if login <= 0:
            raise ValueError("Login MT5 inválido.")
        if not password.strip():
            raise ValueError("Informe a senha do MT5.")
        if not server:
            raise ValueError("Informe o servidor MT5.")
        return MT5Credentials(login=login, password=password, server=server)

    def save_profiles(
        self,
        profiles: Mapping[str, MT5Credentials | None],
    ) -> None:
        """Valida todas as contas e faz uma única gravação verificada no cofre."""
        normalized: dict[str, MT5Credentials | None] = {}
        for environment, credentials in profiles.items():
            self._prefix(environment)
            normalized[environment] = (
                None if credentials is None else self._validated(credentials)
            )

        # A validação acima termina antes de tocar no arquivo. Assim, um erro na
        # segunda conta nunca deixa somente a primeira parcialmente atualizada.
        values = self.secret_store.load()
        for environment, credentials in normalized.items():
            prefix = self._prefix(environment)
            if credentials is None:
                for suffix in ("login", "password", "server"):
                    values.pop(f"{prefix}_{suffix}", None)
                continue
            values[f"{prefix}_login"] = str(credentials.login)
            values[f"{prefix}_password"] = credentials.password
            values[f"{prefix}_server"] = credentials.server
        self.secret_store.save(values)

        # O SecretStore pode devolver vazio quando o Windows não consegue abrir
        # o arquivo protegido. Confirmar a releitura impede mostrar um falso SALVO.
        persisted = self.secret_store.load()
        for environment, credentials in normalized.items():
            prefix = self._prefix(environment)
            if credentials is None:
                if any(persisted.get(f"{prefix}_{suffix}") for suffix in ("login", "password", "server")):
                    raise MT5CredentialPersistenceError(
                        f"Não foi possível remover o cadastro de {environment}."
                    )
                continue
            expected = {
                f"{prefix}_login": str(credentials.login),
                f"{prefix}_password": credentials.password,
                f"{prefix}_server": credentials.server,
            }
            if any(str(persisted.get(key, "")) != value for key, value in expected.items()):
                raise MT5CredentialPersistenceError(
                    f"O Windows não confirmou o salvamento da conta {environment}."
                )

    def clear(self, environment: str) -> None:
        self.save_profiles({environment: None})


__all__ = [
    "MT5Credentials", "MT5CredentialPersistenceError", "MT5CredentialStore",
    "parse_mt5_credentials",
]
