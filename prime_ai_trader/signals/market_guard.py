"""Market-specific confirmation guard for short-horizon signals.

The legacy engine remains responsible for scoring, price action and model
probabilities.  This guard is deliberately conservative: it only vetoes an
entry when the selected market's mandatory confirmations are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class MarketPolicy:
    key: str
    label: str
    minimum_history: int
    minimum_score: dict[str, int]
    minimum_probability: dict[str, float]
    minimum_adx: float
    minimum_body_ratio: float
    buy_close_position: float
    sell_close_position: float
    maximum_extension_atr: float
    minimum_volume_relative: float | None


@dataclass(frozen=True, slots=True)
class GuardDecision:
    allowed: bool
    profile: str
    reasons: tuple[str, ...] = ()
    confirmations: tuple[str, ...] = ()


POLICIES = {
    "CRYPTO": MarketPolicy(
        key="CRYPTO",
        label="CRIPTO • tendência, volume e pullback confirmado",
        minimum_history=55,
        minimum_score={"RÁPIDO": 64, "EQUILIBRADO": 74, "CONSERVADOR": 86},
        minimum_probability={"RÁPIDO": 0.58, "EQUILIBRADO": 0.61, "CONSERVADOR": 0.66},
        minimum_adx=12.0,
        minimum_body_ratio=0.30,
        buy_close_position=0.58,
        sell_close_position=0.42,
        maximum_extension_atr=2.0,
        minimum_volume_relative=0.55,
    ),
    "FOREX": MarketPolicy(
        key="FOREX",
        label="FOREX • tendência, força direcional e sessão",
        minimum_history=60,
        minimum_score={"RÁPIDO": 66, "EQUILIBRADO": 76, "CONSERVADOR": 88},
        minimum_probability={"RÁPIDO": 0.60, "EQUILIBRADO": 0.63, "CONSERVADOR": 0.68},
        minimum_adx=14.0,
        minimum_body_ratio=0.34,
        buy_close_position=0.60,
        sell_close_position=0.40,
        maximum_extension_atr=1.8,
        minimum_volume_relative=None,
    ),
}


def normalize_market(value: Any) -> str | None:
    text = str(getattr(value, "value", value) or "").strip().upper()
    if "CRIPTO" in text or text == "CRYPTO":
        return "CRYPTO"
    if "FOREX" in text or "CÂMBIO" in text or "CAMBIO" in text:
        return "FOREX"
    return None


def _direction_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _number(value: Any, default: float = math.nan) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _profile_value(mapping: dict[str, Any], sensitivity: str) -> Any:
    name = str(sensitivity or "EQUILIBRADO").upper()
    return mapping.get(name, mapping["EQUILIBRADO"])


def _macro_trend(indicators: pd.DataFrame) -> str | None:
    last = indicators.iloc[-1]
    earlier = indicators.iloc[-4]
    ema_21 = _number(last.get("ema_21"))
    ema_50 = _number(last.get("ema_50"))
    old_21 = _number(earlier.get("ema_21"))
    atr = max(_number(last.get("atr_14"), 0.0), 1e-12)
    separation = abs(ema_21 - ema_50) / atr
    if separation < 0.08:
        return None
    if ema_21 > ema_50 and ema_21 > old_21:
        return "COMPRA"
    if ema_21 < ema_50 and ema_21 < old_21:
        return "VENDA"
    return None


def _countertrend_reversal_confirmed(indicators: pd.DataFrame, direction: str) -> bool:
    last = indicators.iloc[-1]
    previous = indicators.iloc[-2]
    close = _number(last.get("close"))
    previous_close = _number(previous.get("close"))
    ema_9 = _number(last.get("ema_9"))
    ema_21 = _number(last.get("ema_21"))
    previous_ema_21 = _number(previous.get("ema_21"))
    plus_di = _number(last.get("plus_di"), 0.0)
    minus_di = _number(last.get("minus_di"), 0.0)
    macd_hist = _number(last.get("macd_hist"), 0.0)
    previous_high = _number(indicators["high"].iloc[-9:-1].max())
    previous_low = _number(indicators["low"].iloc[-9:-1].min())
    if direction == "COMPRA":
        return (
            close > ema_21
            and previous_close > previous_ema_21
            and ema_9 > ema_21
            and plus_di >= minus_di + 3.0
            and macd_hist > 0
            and close > previous_high
        )
    return (
        close < ema_21
        and previous_close < previous_ema_21
        and ema_9 < ema_21
        and minus_di >= plus_di + 3.0
        and macd_hist < 0
        and close < previous_low
    )


def _local_direction_confirmed(indicators: pd.DataFrame, direction: str, policy: MarketPolicy) -> bool:
    last = indicators.iloc[-1]
    close = _number(last.get("close"))
    open_price = _number(last.get("open"))
    ema_9 = _number(last.get("ema_9"))
    ema_21 = _number(last.get("ema_21"))
    plus_di = _number(last.get("plus_di"), 0.0)
    minus_di = _number(last.get("minus_di"), 0.0)
    macd_hist = _number(last.get("macd_hist"), 0.0)
    close_position = _number(last.get("close_position"), 0.5)
    if direction == "COMPRA":
        return (
            close > open_price
            and close >= ema_9 >= ema_21
            and plus_di >= minus_di
            and macd_hist >= 0
            and close_position >= policy.buy_close_position
        )
    return (
        close < open_price
        and close <= ema_9 <= ema_21
        and minus_di >= plus_di
        and macd_hist <= 0
        and close_position <= policy.sell_close_position
    )


def _selected_probability(probabilities: dict[str, float] | None, direction: str) -> float | None:
    if not probabilities:
        return None
    value = _number(probabilities.get(direction))
    return value if math.isfinite(value) else None


def evaluate_market_entry(
    *,
    indicators: pd.DataFrame,
    features: pd.DataFrame | None,
    direction: Any,
    market: Any,
    sensitivity: str,
    mode: str,
    candle_closed: bool,
    score: int,
    probabilities: dict[str, float] | None,
    payout_percent: int,
) -> GuardDecision:
    direction_value = _direction_value(direction)
    market_key = normalize_market(market)
    if direction_value not in {"COMPRA", "VENDA"}:
        return GuardDecision(True, POLICIES.get(market_key, POLICIES["CRYPTO"]).label)
    if market_key is None:
        return GuardDecision(True, "MERCADO NÃO INFORMADO")

    policy = POLICIES[market_key]
    reasons: list[str] = []
    confirmations: list[str] = [policy.label]
    if str(mode or "").upper() == "CONFIRMAÇÃO" and not candle_closed:
        reasons.append("Modo confirmação: aguarde o fechamento real da vela")
    if indicators is None or len(indicators) < policy.minimum_history:
        reasons.append(f"Histórico insuficiente para o perfil {market_key}")
        return GuardDecision(False, policy.label, tuple(reasons), tuple(confirmations))

    last = indicators.iloc[-1]
    required = ("open", "high", "low", "close", "ema_9", "ema_21", "ema_50", "atr_14", "adx_14")
    if any(not math.isfinite(_number(last.get(column))) for column in required):
        reasons.append("Indicadores obrigatórios ainda estão em formação")
        return GuardDecision(False, policy.label, tuple(reasons), tuple(confirmations))

    minimum_score = int(_profile_value(policy.minimum_score, sensitivity))
    if int(score) < minimum_score:
        reasons.append(f"Score {int(score)} abaixo do mínimo {minimum_score} do perfil {market_key}")

    payout = max(1, min(100, int(payout_percent))) / 100.0
    break_even = 1.0 / (1.0 + payout)
    probability_floor = max(float(_profile_value(policy.minimum_probability, sensitivity)), break_even + 0.025)
    selected_probability = _selected_probability(probabilities, direction_value)
    if selected_probability is not None and selected_probability < probability_floor:
        reasons.append(
            f"Probabilidade {selected_probability:.1%} abaixo da confirmação {probability_floor:.1%}"
        )

    high = _number(last.get("high"))
    low = _number(last.get("low"))
    close = _number(last.get("close"))
    open_price = _number(last.get("open"))
    span = max(high - low, 1e-12)
    body_ratio = abs(close - open_price) / span
    close_position = (close - low) / span
    if body_ratio < policy.minimum_body_ratio:
        reasons.append("Vela dominada por pavio; entrada sem corpo direcional suficiente")
    if direction_value == "COMPRA" and close_position < policy.buy_close_position:
        reasons.append("Compra sem fechamento próximo da máxima da vela")
    if direction_value == "VENDA" and close_position > policy.sell_close_position:
        reasons.append("Venda sem fechamento próximo da mínima da vela")

    atr = max(_number(last.get("atr_14"), 0.0), 1e-12)
    ema_21 = _number(last.get("ema_21"))
    extension_atr = abs(close - ema_21) / atr
    if extension_atr > policy.maximum_extension_atr:
        reasons.append(
            f"Preço esticado {extension_atr:.2f} ATR; aguarde pullback ou reteste"
        )

    adx_value = _number(last.get("adx_14"), 0.0)
    if adx_value < policy.minimum_adx:
        reasons.append(f"ADX {adx_value:.1f} abaixo do mínimo {policy.minimum_adx:.0f} para {market_key}")

    macro = _macro_trend(indicators)
    if macro and direction_value != macro:
        if not _countertrend_reversal_confirmed(indicators, direction_value):
            reasons.append(
                f"Movimento contrário à tendência {macro}; pullback não é reversão confirmada"
            )
        else:
            confirmations.append("Reversão confirmada por duas velas, DI/MACD e quebra estrutural")
    elif not _local_direction_confirmed(indicators, direction_value, policy):
        reasons.append("Retomada direcional ainda não confirmou EMA, DI, MACD e fechamento")
    else:
        confirmations.append("Retomada confirmada após fechamento da vela")

    if market_key == "CRYPTO":
        volume = _number(last.get("volume"), 0.0)
        relative = _number(last.get("volume_relative"), 0.0)
        if volume <= 0 or relative < float(policy.minimum_volume_relative):
            reasons.append("Cripto sem volume relativo suficiente para confirmar o movimento")
        else:
            confirmations.append(f"Volume cripto confirmado ({relative:.2f}x)")
    else:
        # Spot Forex usually exposes no centralized real volume.  Do not treat
        # zero/tick volume as a bearish or bullish confirmation.
        timestamp = getattr(indicators.index[-1], "to_pydatetime", lambda: None)()
        if timestamp is not None and timestamp.weekday() >= 5:
            reasons.append("Forex fechado no fim de semana")
        elif timestamp is not None and 7 <= timestamp.hour <= 20:
            confirmations.append("Sessão líquida de Londres/Nova York")
        else:
            confirmations.append("Forex validado sem usar volume de cripto")

    return GuardDecision(not reasons, policy.label, tuple(reasons), tuple(confirmations))
