from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config.settings import app_data_dir


def configure_logging() -> logging.Logger:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("prime_ai_trader")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(handler)
    logger.info("Inicialização do PRIME AI TRADER")
    return logger

