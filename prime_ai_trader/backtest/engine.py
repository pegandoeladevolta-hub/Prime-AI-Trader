from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import confusion_matrix

from ..ml.models import align_supervised_data, candidate_models, temporal_folds
from ..signals.engine import sensitivity_profile


@dataclass(slots=True)
class BacktestResult:
    samples: int
    operations: int
    wins: int
    losses: int
    draws: int
    directional_operations: int
    accuracy: float
    draw_rate: float
    coverage: float
    confusion: list[list[int]]
    longest_win_streak: int
    longest_loss_streak: int
    signals_per_day: float
    by_hour: dict[int, dict[str, float]]
    train_samples: int
    validation_samples: int
    test_samples: int
    quality: str
    payout_percent: int = 80
    break_even_rate: float = 1 / 1.8
    expected_value: float = 0.0
    confidence_low: float = 0.0
    confidence_high: float = 1.0
    stake_amount: float = 1.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float | None = None


def _longest(values: list[bool | None], target: bool) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value is target else 0
        best = max(best, current)
    return best


def _directional_confluence(row: pd.Series, prediction: int,
                            sensitivity: str = "EQUILIBRADO") -> bool:
    """Filtra previsões isoladas que contradizem tendência e momentum."""
    if prediction not in {-1, 1}:
        return False
    profile = sensitivity_profile(sensitivity)
    adx = row.get("adx_14")
    if pd.isna(adx) or float(adx) < profile.minimum_adx:
        return False
    atr_regime = row.get("atr_regime")
    if pd.notna(atr_regime) and not profile.volatility_minimum <= float(atr_regime) <= profile.volatility_maximum:
        return False
    sign = float(prediction)
    extension = row.get("ema21_distance_atr")
    if pd.notna(extension) and abs(float(extension)) > profile.maximum_extension_atr:
        return False
    efficiency = row.get("trend_efficiency")
    if pd.notna(efficiency) and sign * float(efficiency) < -0.28:
        return False
    compression = row.get("compression_ratio")
    breakout = row.get("breakout_strength_atr")
    if pd.notna(compression) and float(compression) < 0.53 and (
        pd.isna(breakout) or sign * float(breakout) <= 0
    ):
        return False
    reversal = row.get("reversal_pressure")
    if pd.notna(reversal) and sign * float(reversal) < -0.32:
        return False
    votes = (
        sign * float(row.get("ema_distance_9_21", 0) or 0) > 0,
        sign * float(row.get("ema_distance_21_50", 0) or 0) > 0,
        sign * float(row.get("macd_hist", 0) or 0) > 0,
        sign * (float(row.get("plus_di", 0) or 0) - float(row.get("minus_di", 0) or 0)) > 0,
        sign * float(row.get("trend_code", 0) or 0) >= 0,
    )
    minimum = {"RÁPIDO": 2, "EQUILIBRADO": 3, "CONSERVADOR": 4}[profile.name]
    return sum(votes) >= minimum


def _wilson_interval(wins: int, samples: int, z: float = 1.96) -> tuple[float, float]:
    if samples <= 0:
        return 0.0, 1.0
    rate = wins / samples
    denominator = 1 + z * z / samples
    center = rate + z * z / (2 * samples)
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * samples)) / samples)
    return max(0.0, (center - margin) / denominator), min(1.0, (center + margin) / denominator)


class BacktestEngine:
    def run(self, features: pd.DataFrame, labels: pd.Series, model_name: str = "Logistic Regression",
            confidence_threshold: float = 0.58, probability_edge: float = 0.12,
            purge_size: int = 0, sensitivity: str = "EQUILIBRADO",
            payout_percent: int = 80, stake_amount: float = 1.0) -> BacktestResult:
        x, y = align_supervised_data(features, labels)
        if len(x) < 130:
            raise ValueError("Histórico insuficiente para backtest walk-forward.")
        folds = temporal_folds(len(x), purge_size=purge_size)
        if not folds:
            raise ValueError("Não foi possível criar blocos temporais de teste.")
        model_template = candidate_models()[model_name]
        predictions: list[int] = []
        truths: list[int] = []
        timestamps = []
        confidences = []
        probability_edges = []
        confluences = []
        for train_idx, test_idx in folds:
            model = clone(model_template)
            model.fit(x.iloc[train_idx], y.iloc[train_idx])
            proba = model.predict_proba(x.iloc[test_idx])
            classes = model.named_steps["model"].classes_
            best_idx = np.argmax(proba, axis=1)
            fold_predictions = classes[best_idx]
            fold_confidence = proba[np.arange(len(proba)), best_idx]
            class_positions = {int(label): position for position, label in enumerate(classes)}
            fold_rows = x.iloc[test_idx]
            for row_position, prediction in enumerate(fold_predictions):
                opposite_position = class_positions.get(-int(prediction))
                opposite_probability = float(proba[row_position, opposite_position]) if opposite_position is not None else 0.0
                probability_edges.append(float(fold_confidence[row_position]) - opposite_probability)
                confluences.append(_directional_confluence(
                    fold_rows.iloc[row_position], int(prediction), sensitivity,
                ))
            predictions.extend(int(v) for v in fold_predictions)
            truths.extend(int(v) for v in y.iloc[test_idx])
            confidences.extend(float(v) for v in fold_confidence)
            timestamps.extend(x.index[test_idx])
        active = [
            i for i, (pred, confidence, edge, confluence) in enumerate(
                zip(predictions, confidences, probability_edges, confluences)
            )
            if pred != 0 and confidence >= confidence_threshold and edge >= probability_edge and confluence
        ]
        directional = [i for i in active if truths[i] != 0]
        outcomes: list[bool | None] = [
            None if truths[i] == 0 else predictions[i] == truths[i] for i in active
        ]
        wins = sum(predictions[i] == truths[i] for i in directional)
        losses = len(directional) - wins
        draws = len(active) - len(directional)
        accuracy = wins / len(directional) if directional else 0.0
        payout = min(max(int(payout_percent or 80), 1), 200)
        break_even = 1 / (1 + payout / 100)
        expected_value = accuracy * payout / 100 - (1 - accuracy) if directional else 0.0
        stake = float(stake_amount) if math.isfinite(float(stake_amount)) and float(stake_amount) > 0 else 1.0
        gross_profit = wins * stake * payout / 100
        gross_loss = losses * stake
        net_profit = gross_profit - gross_loss
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
        confidence_low, confidence_high = _wilson_interval(wins, len(directional))
        quality = (
            "AMOSTRA EM FORMAÇÃO" if len(directional) < 20
            else "FRACA" if accuracy <= break_even
            else "FORTE" if accuracy >= break_even + 0.08
            else "MODERADA"
        )
        matrix = confusion_matrix(truths, predictions, labels=[-1, 0, 1]).tolist()
        unique_days = max(len({timestamp.date() for timestamp in timestamps}), 1)
        by_hour: dict[int, dict[str, float]] = {}
        for hour in range(24):
            indices = [i for i in active if timestamps[i].hour == hour]
            if indices:
                hour_directional = [i for i in indices if truths[i] != 0]
                hour_wins = sum(predictions[i] == truths[i] for i in hour_directional)
                by_hour[hour] = {
                    "signals": len(indices),
                    "draws": len(indices) - len(hour_directional),
                    "accuracy": hour_wins / len(hour_directional) if hour_directional else 0.0,
                }
        first_train, last_test = folds[0][0], folds[-1][1]
        validation = sum(len(test) for _, test in folds[:-1])
        return BacktestResult(
            len(x), len(active), wins, losses, draws, len(directional), accuracy,
            draws / len(active) if active else 0.0,
            len(active) / len(predictions) if predictions else 0.0, matrix,
            _longest(outcomes, True), _longest(outcomes, False), len(active) / unique_days,
            by_hour, len(first_train), validation, len(last_test), quality,
            payout, break_even, expected_value, confidence_low, confidence_high,
            stake, gross_profit, gross_loss, net_profit, profit_factor,
        )
