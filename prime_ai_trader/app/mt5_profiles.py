from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config.settings import app_data_dir


REAL = "CLEAR REAL"
SIMULATOR = "CLEAR SIMULADOR"
ENVIRONMENTS = (REAL, SIMULATOR)


@dataclass
class MT5ProfilesConfig:
    environment: str = REAL
    shared_terminal_path: str = ""
    # Mantidos somente para migrar configurações das versões 1.3.1–1.3.3.
    real_terminal_path: str = ""
    simulator_terminal_path: str = ""
    real_daily_profit_target: float = 0.0
    real_daily_stop_loss: float = 0.0
    real_max_consecutive_losses: int = 2
    simulator_daily_profit_target: float = 0.0
    simulator_daily_stop_loss: float = 0.0
    simulator_max_consecutive_losses: int = 2
    migrated_legacy_limits: bool = False


class MT5ProfileStore:
    """Configuração local dos dois ambientes MT5 sem armazenar credenciais."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "mt5_profiles.json"
        self.config = self.load()

    def load(self) -> MT5ProfilesConfig:
        if not self.path.exists():
            return MT5ProfilesConfig()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = MT5ProfilesConfig.__dataclass_fields__.keys()
            config = MT5ProfilesConfig(**{key: value for key, value in raw.items() if key in allowed})
        except (OSError, ValueError, TypeError):
            config = MT5ProfilesConfig()
        if config.environment not in ENVIRONMENTS:
            config.environment = REAL
        if not str(config.shared_terminal_path or "").strip():
            config.shared_terminal_path = str(
                config.real_terminal_path or config.simulator_terminal_path or ""
            ).strip()
        for name in (
            "real_daily_profit_target", "real_daily_stop_loss",
            "simulator_daily_profit_target", "simulator_daily_stop_loss",
        ):
            try:
                setattr(config, name, max(0.0, float(getattr(config, name))))
            except (TypeError, ValueError):
                setattr(config, name, 0.0)
        for name in ("real_max_consecutive_losses", "simulator_max_consecutive_losses"):
            try:
                setattr(config, name, min(20, max(0, int(getattr(config, name)))))
            except (TypeError, ValueError):
                setattr(config, name, 2)
        return config

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(self.config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def environment(self) -> str:
        return self.config.environment

    def set_environment(self, environment: str) -> None:
        if environment not in ENVIRONMENTS:
            raise ValueError(f"Ambiente MT5 inválido: {environment}")
        self.config.environment = environment
        self.save()

    def terminal_path(self, environment: str | None = None) -> str:
        return str(self.config.shared_terminal_path or "")

    def set_terminal_path(self, path: str, environment: str | None = None) -> None:
        self.config.shared_terminal_path = str(path or "")
        self.config.real_terminal_path = ""
        self.config.simulator_terminal_path = ""
        self.save()

    def daily_limits(self, environment: str | None = None) -> tuple[float, float]:
        env = environment or self.environment
        if env == SIMULATOR:
            return (
                float(self.config.simulator_daily_profit_target),
                float(self.config.simulator_daily_stop_loss),
            )
        return (
            float(self.config.real_daily_profit_target),
            float(self.config.real_daily_stop_loss),
        )

    def set_daily_limits(self, target: float, stop: float,
                         environment: str | None = None) -> None:
        env = environment or self.environment
        target, stop = max(0.0, float(target)), max(0.0, float(stop))
        if env == SIMULATOR:
            self.config.simulator_daily_profit_target = target
            self.config.simulator_daily_stop_loss = stop
        else:
            self.config.real_daily_profit_target = target
            self.config.real_daily_stop_loss = stop
        self.save()

    def consecutive_loss_limit(self, environment: str | None = None) -> int:
        env = environment or self.environment
        value = (
            self.config.simulator_max_consecutive_losses
            if env == SIMULATOR else self.config.real_max_consecutive_losses
        )
        return min(20, max(0, int(value)))

    def set_consecutive_loss_limit(self, limit: int,
                                   environment: str | None = None) -> None:
        env = environment or self.environment
        value = min(20, max(0, int(limit)))
        if env == SIMULATOR:
            self.config.simulator_max_consecutive_losses = value
        else:
            self.config.real_max_consecutive_losses = value
        self.save()

    def migrate_legacy_limits_once(self, settings) -> None:
        if self.config.migrated_legacy_limits:
            return
        target = max(0.0, float(getattr(settings, "mt5_daily_profit_target", 0.0) or 0.0))
        stop = max(0.0, float(getattr(settings, "mt5_daily_stop_loss", 0.0) or 0.0))
        if target or stop:
            self.config.real_daily_profit_target = target
            self.config.real_daily_stop_loss = stop
        try:
            self.config.real_max_consecutive_losses = min(
                20, max(0, int(getattr(settings, "mt5_max_consecutive_losses", 2)))
            )
        except (TypeError, ValueError):
            self.config.real_max_consecutive_losses = 2
        legacy_path = str(getattr(settings, "mt5_terminal_path", "") or "").strip()
        if legacy_path and not self.config.shared_terminal_path:
            self.config.shared_terminal_path = legacy_path
        self.config.migrated_legacy_limits = True
        self.save()

    def journal_path(self, environment: str | None = None) -> Path:
        env = environment or self.environment
        suffix = "simulador" if env == SIMULATOR else "real"
        return app_data_dir() / f"prime_mt5_journal_{suffix}.db"


def classify_account_environment(server: str, name: str = "") -> str:
    text = f"{server} {name}".lower()
    if any(token in text for token in ("demo", "simul", "practice", "trial")):
        return SIMULATOR
    return REAL


def is_clear_account(server: str, name: str = "") -> bool:
    """Confirma que a sessão MT5 pertence à Clear antes de adotá-la."""
    return "clear" in f"{server} {name}".lower()


__all__ = [
    "REAL", "SIMULATOR", "ENVIRONMENTS", "MT5ProfilesConfig", "MT5ProfileStore",
    "classify_account_environment", "is_clear_account",
]
