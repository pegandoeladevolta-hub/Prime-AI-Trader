from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from prime_ai_trader.core.models import Candle


def synthetic_candles(count: int = 600, seed: int = 42) -> list[Candle]:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.00025, 0.005, count)
    close = 100 * np.exp(np.cumsum(returns))
    open_ = np.r_[100.0, close[:-1]]
    spread = rng.uniform(0.001, 0.01, count) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.uniform(100, 1200, count)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [Candle(start + timedelta(minutes=5 * i), float(open_[i]), float(high[i]), float(low[i]), float(close[i]), float(volume[i])) for i in range(count)]

