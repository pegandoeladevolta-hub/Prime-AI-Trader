from __future__ import annotations

import base64
import ctypes
import json
import os
import platform
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def app_data_dir() -> Path:
    explicit_root = os.environ.get("PRIME_AI_TRADER_DATA_HOME") or os.environ.get("XDG_DATA_HOME")
    if explicit_root:
        root = Path(explicit_root)
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
    else:
        root = Path.home() / ".local" / "share"
    path = root / "PrimeAITrader"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AppSettings:
    market: str = "Criptomoedas"
    crypto_symbol: str = "BTC/USDT"
    forex_symbol: str = "EUR/USD"
    timeframe: str = "5m"
    horizon_minutes: int = 5
    payout_percent: int = 80
    stake_amount: float = 80.0
    sensitivity: str = "EQUILIBRADO"
    mode: str = "CONFIRMAÇÃO"
    audio_enabled: bool = True
    audio_volume: int = 70
    voice_pre_signal: bool = False
    voice_confirmed: bool = True
    voice_alerts: bool = True
    high_impact_block_minutes: int = 10
    strict_risk_blocks: bool = False
    platform_sync_enabled: bool = False
    platform_name: str = "VEX"
    bullex_sync_authorized: bool = False
    platform_auto_asset: bool = True
    platform_auto_payout: bool = True
    platform_auto_horizon: bool = True
    platform_block_mismatch: bool = True
    overlays: dict[str, bool] = field(default_factory=lambda: {
        "sr": True, "fibonacci": True, "ema": True, "bollinger": True,
        "swings": True, "trend": True, "signals": True,
    })


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_protect(raw: bytes) -> bytes:
    source = _DataBlob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_byte)))
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "PrimeAITrader", None, None, None, 0, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _dpapi_unprotect(raw: bytes) -> bytes:
    source = _DataBlob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_byte)))
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _fallback_key() -> bytes:
    import hashlib
    seed = f"{platform.node()}|{os.getuid() if hasattr(os, 'getuid') else 0}|PrimeAITrader".encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


class SecretStore:
    """Usa Windows DPAPI; o fallback existe apenas para desenvolvimento fora do Windows."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "secrets.dat"

    def save(self, secrets: dict[str, str]) -> None:
        payload = json.dumps({k: v for k, v in secrets.items() if v}, ensure_ascii=False).encode()
        if os.name == "nt":
            encrypted = b"DPAPI1" + _dpapi_protect(payload)
        else:
            from cryptography.fernet import Fernet
            encrypted = b"FERNET" + Fernet(_fallback_key()).encrypt(payload)
        self.path.write_bytes(encrypted)

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        raw = self.path.read_bytes()
        try:
            if raw.startswith(b"DPAPI1") and os.name == "nt":
                clear = _dpapi_unprotect(raw[6:])
            elif raw.startswith(b"FERNET"):
                from cryptography.fernet import Fernet
                clear = Fernet(_fallback_key()).decrypt(raw[6:])
            else:
                return {}
            return json.loads(clear.decode())
        except Exception:
            return {}


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "settings.json"

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = AppSettings.__dataclass_fields__.keys()
            return AppSettings(**{k: v for k, v in values.items() if k in allowed})
        except (OSError, ValueError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")


def load_api_config_template() -> dict[str, Any]:
    return {
        "twelve_data_key": "", "alpha_vantage_key": "", "finnhub_key": "",
    }
