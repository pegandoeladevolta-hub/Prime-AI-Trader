from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .vex import (
    VISIBLE_TRADEROOM_SCRIPT, VexBrowserBridge, VexPlatformSnapshot,
    compare_platform_market, merge_platform_quote, normalize_vex_asset,
    parse_localized_price, parse_vex_countdown, parse_vex_percent,
    snapshot_from_visible,
)


BULLEX_HOME_URL = "https://www.bullex.com.br/pt"
BULLEX_CVM_ALERT_URL = (
    "https://www.gov.br/cvm/pt-br/assuntos/noticias/2025/"
    "cvm-alerta-para-atuacao-irregular-da-digital-smart-llc-bullex-e-seu-responsavel"
)
BULLEX_ALLOWED_HOSTS = {
    "bullex.com.br", "www.bullex.com.br", "bull-ex.com", "www.bull-ex.com",
    "trade.bull-ex.com", "app.bull-ex.com",
}

BullexPlatformSnapshot = VexPlatformSnapshot
normalize_bullex_asset = normalize_vex_asset
parse_bullex_percent = parse_vex_percent
parse_bullex_countdown = parse_vex_countdown


def snapshot_from_bullex_visible(payload: dict) -> BullexPlatformSnapshot:
    # O caminho da sala pode mudar sem constituir uma API. A confiança é limitada
    # ao HTTPS e aos hosts explícitos da marca, e a leitura continua somente visual.
    snapshot = snapshot_from_visible(
        payload, allowed_hosts=BULLEX_ALLOWED_HOSTS, path_prefix=None,
        platform_name="BULLEX",
    )
    if snapshot.authenticated and (
        snapshot.asset is None
        or snapshot.payout_percent is None
        or snapshot.remaining_seconds is None and snapshot.horizon_minutes is None
    ):
        return replace(snapshot, authenticated=False, asset=None, market=None,
                       payout_percent=None, price=None)
    return snapshot


class BullexBrowserBridge(VexBrowserBridge):
    """Sincronização visual local, sem login interno, cliques ou execução."""

    def __init__(self, profile_dir: Path, on_snapshot, on_status) -> None:
        super().__init__(
            profile_dir, on_snapshot, on_status, platform_name="BULLEX",
            traderoom_url=BULLEX_HOME_URL, allowed_hosts=BULLEX_ALLOWED_HOSTS,
            visible_script=VISIBLE_TRADEROOM_SCRIPT,
            snapshot_parser=snapshot_from_bullex_visible,
        )


__all__ = [
    "BULLEX_ALLOWED_HOSTS", "BULLEX_CVM_ALERT_URL", "BULLEX_HOME_URL",
    "BullexBrowserBridge", "BullexPlatformSnapshot", "compare_platform_market",
    "merge_platform_quote", "normalize_bullex_asset", "parse_bullex_countdown",
    "parse_bullex_percent", "parse_localized_price", "snapshot_from_bullex_visible",
]
