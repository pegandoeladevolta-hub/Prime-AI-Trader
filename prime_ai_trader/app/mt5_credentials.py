from __future__ import annotations

from ..config.settings import SecretStore


_LEGACY_MT5_PREFIXES = ("mt5_clear_real", "mt5_clear_simulator")
_LEGACY_MT5_SUFFIXES = ("login", "password", "server")


class MT5CredentialPurgeError(RuntimeError):
    """O armazenamento protegido não confirmou a remoção das credenciais antigas."""


def purge_saved_mt5_credentials(secret_store: SecretStore | None = None) -> bool:
    """Remove somente login/senha/servidor antigos do MT5.

    Outros segredos do Prime Trader permanecem intactos. Retorna ``True`` quando
    encontrou e removeu algum campo legado e ``False`` quando já estava limpo.
    """
    store = secret_store or SecretStore()
    values = store.load()
    keys = {
        f"{prefix}_{suffix}"
        for prefix in _LEGACY_MT5_PREFIXES
        for suffix in _LEGACY_MT5_SUFFIXES
    }
    found = any(key in values for key in keys)
    if not found:
        return False

    cleaned = {key: value for key, value in values.items() if key not in keys}
    store.save(cleaned)
    persisted = store.load()
    if any(key in persisted for key in keys):
        raise MT5CredentialPurgeError(
            "Não foi possível apagar completamente as credenciais MT5 antigas."
        )
    return True


__all__ = ["MT5CredentialPurgeError", "purge_saved_mt5_credentials"]
