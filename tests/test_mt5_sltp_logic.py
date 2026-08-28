from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from prime_ai_trader.core.models import Candle, Direction, Zone
from prime_ai_trader.ml.triple_barrier import build_mt5_barrier_labels
from prime_ai_trader.priceaction.mt5_levels import calculate_mt5_trade_plan
from prime_ai_trader.priceaction.structure import MarketStructure


def _structure(*, supports=None, resistances=None):
    return MarketStructure(
        trend="ALTA",
        sequence=["HH", "HL"],
        breakout=None,
        retest=False,
        false_breakout=False,
        support_zones=supports or [],
        resistance_zones=resistances or [],
        pivot_highs=[],
        pivot_lows=[],
    )


def _indicators(close: float = 100.0, atr: float = 1.0, length: int = 60):
    index = pd.date_range("2026-08-27 18:00:00", periods=length, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [close] * length,
            "high": [close + 0.2] * length,
            "low": [close - 0.2] * length,
            "close": [close] * length,
            "atr_14": [atr] * length,
        },
        index=index,
    )


def test_mt5_plan_without_obstacle_reaches_minimum_rr():
    plan = calculate_mt5_trade_plan(
        _indicators(), _structure(), Direction.BUY,
        management_mode="SCALP", minimum_rr=1.5,
    )
    assert plan is not None
    assert plan.viable is True
    assert plan.stop < plan.entry < plan.target
    assert abs(plan.rr - 1.5) < 1e-9


def test_mt5_plan_rejects_trade_when_resistance_blocks_required_rr():
    resistance = Zone("RESISTÊNCIA", 100.50, 100.60, 3, 55)
    plan = calculate_mt5_trade_plan(
        _indicators(), _structure(resistances=[resistance]), Direction.BUY,
        management_mode="SCALP", minimum_rr=1.5,
    )
    assert plan is not None
    assert plan.viable is False
    assert plan.target < 100.50
    assert plan.rr < 1.5


def test_triple_barrier_labels_buy_when_tp_arrives_before_sl():
    start = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(45):
        opened = start + timedelta(minutes=i)
        candles.append(Candle(
            open_time=opened,
            open=100.0,
            high=100.2,
            low=99.8,
            close=100.0,
            volume=100.0,
            close_time=opened + timedelta(minutes=1),
            closed=True,
        ))
    # Para SCALP: risco = 0.78 ATR e alvo 1.5R = 1.17. A segunda vela toca
    # 101.17 sem tocar o stop de compra 99.22; para venda ela toca o stop 100.78.
    candles[1] = Candle(
        open_time=start + timedelta(minutes=1),
        open=100.0,
        high=101.30,
        low=99.80,
        close=101.0,
        volume=100.0,
        close_time=start + timedelta(minutes=2),
        closed=True,
    )
    indicators = _indicators(length=len(candles))
    indicators.index = pd.DatetimeIndex([c.open_time for c in candles])
    labels = build_mt5_barrier_labels(
        candles, indicators, minimum_rr=1.5, management_mode="SCALP",
    )
    assert labels.iloc[0] == 1.0


def test_triple_barrier_last_window_is_not_used_for_training():
    start = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
    candles = [
        Candle(
            open_time=start + timedelta(minutes=i),
            open=100.0, high=100.1, low=99.9, close=100.0,
            volume=100.0, close_time=start + timedelta(minutes=i + 1), closed=True,
        )
        for i in range(45)
    ]
    indicators = _indicators(length=len(candles))
    indicators.index = pd.DatetimeIndex([c.open_time for c in candles])
    labels = build_mt5_barrier_labels(
        candles, indicators, minimum_rr=1.5, management_mode="SCALP",
    )
    assert labels.tail(30).isna().all()
