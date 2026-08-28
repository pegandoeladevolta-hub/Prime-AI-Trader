from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config.settings import app_data_dir


CLEAN_START_EPOCH = "prime-trader-mt5-clean-2026-08-28-v1"
CLEAN_START_MARKER = ".prime_trader_clean_epoch"


@dataclass(frozen=True, slots=True)
class CleanStartResult:
    reset: bool
    removed_entries: int = 0
    data_dir: str = ""


def _remove_path(path: Path) -> None:
    """Remove arquivo/pasta local, inclusive itens somente-leitura no Windows."""
    if path.is_symlink() or path.is_file():
        try:
            path.chmod(0o700)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        return

    if not path.exists():
        return

    def onerror(func, target, exc_info):
        try:
            os.chmod(target, 0o700)
            func(target)
        except OSError:
            raise exc_info[1]

    shutil.rmtree(path, onerror=onerror)


def initialize_clean_mt5_start(data_dir: Path | None = None) -> CleanStartResult:
    """Inicia uma nova era local do Prime Trader MT5, uma única vez.

    A limpeza acontece antes do controller, banco, logs e modelos serem abertos.
    Tudo dentro da pasta de dados gerenciada pelo Prime Trader é removido: banco,
    sinais, decisões, configurações, segredos locais, modelos da IA, caches, logs e
    marcadores de migrações anteriores. O MetaTrader 5 e o histórico da corretora
    ficam fora dessa pasta e nunca são alterados por esta rotina.
    """
    root = Path(data_dir) if data_dir is not None else app_data_dir()
    root.mkdir(parents=True, exist_ok=True)

    marker = root / CLEAN_START_MARKER
    try:
        current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    except OSError:
        current = ""
    if current == CLEAN_START_EPOCH:
        return CleanStartResult(False, 0, str(root))

    # Defesa simples contra caminho acidentalmente amplo. O app_data_dir oficial
    # termina em PrimeAITrader; testes podem fornecer uma pasta temporária explícita.
    if data_dir is None and root.name.lower() != "primeaitrader":
        raise RuntimeError(f"Pasta de dados inesperada; limpeza cancelada: {root}")

    removed = 0
    for child in list(root.iterdir()):
        _remove_path(child)
        removed += 1

    root.mkdir(parents=True, exist_ok=True)
    marker.write_text(CLEAN_START_EPOCH, encoding="utf-8")
    return CleanStartResult(True, removed, str(root))


__all__ = [
    "CLEAN_START_EPOCH",
    "CLEAN_START_MARKER",
    "CleanStartResult",
    "initialize_clean_mt5_start",
]
