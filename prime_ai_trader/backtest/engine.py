from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import confusion_matrix

from ..features.builder import FEATURE_COLUMNS
from ..ml.models import candidate_models, temporal_folds


@dataclass(slots=True)
class BacktestResult:
    samples: int
    operations: int
    wins: int
    losses: int
    draws: int
    accuracy: float
    coverage: float
    confusion: list[list[int]]
    longest_win_streak: int
    longest_loss_streak: int
    signals_per_day: float
    by_hour: dict[int, dict[str, float]]
    train_samples: int
    validation_samples: int
    test_samples: int


def _longest(values: list[bool], target: bool) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value is target else 0
        best = max(best, current)
    return best


class BacktestEngine:
    def run(self, features: pd.DataFrame, labels: pd.Series, model_name: str = "Logistic Regression",
            confidence_threshold: float = 0.58) -> BacktestResult:
        valid = labels.notna()
        x, y = features.loc[valid, FEATURE_COLUMNS], labels.loc[valid].astype(int)
        if len(x) < 130:
            raise ValueError("Histórico insuficiente para backtest walk-forward.")
        folds = temporal_folds(len(x))
        if not folds:
            raise ValueError("Não foi possível criar blocos temporais de teste.")
        model_template = candidate_models()[model_name]
        predictions: list[int] = []
        truths: list[int] = []
        timestamps = []
        confidences = []
        for train_idx, test_idx in folds:
            model = clone(model_template)
            model.fit(x.iloc[train_idx], y.iloc[train_idx])
            proba = model.predict_proba(x.iloc[test_idx])
            classes = model.named_steps["model"].classes_
            best_idx = np.argmax(proba, axis=1)
            fold_predictions = classes[best_idx]
            fold_confidence = proba[np.arange(len(proba)), best_idx]
            predictions.extend(int(v) for v in fold_predictions)
            truths.extend(int(v) for v in y.iloc[test_idx])
            confidences.extend(float(v) for v in fold_confidence)
            timestamps.extend(x.index[test_idx])
        active = [i for i, (pred, confidence) in enumerate(zip(predictions, confidences)) if pred != 0 and confidence >= confidence_threshold]
        outcomes = [predictions[i] == truths[i] for i in active]
        wins = sum(outcomes)
        losses = len(outcomes) - wins
        draws = sum(truths[i] == 0 for i in active)
        matrix = confusion_matrix(truths, predictions, labels=[-1, 0, 1]).tolist()
        unique_days = max(len({timestamp.date() for timestamp in timestamps}), 1)
        by_hour: dict[int, dict[str, float]] = {}
        for hour in range(24):
            indices = [i for i in active if timestamps[i].hour == hour]
            if indices:
                hour_wins = sum(predictions[i] == truths[i] for i in indices)
                by_hour[hour] = {"signals": len(indices), "accuracy": hour_wins / len(indices)}
        first_train, last_test = folds[0][0], folds[-1][1]
        validation = sum(len(test) for _, test in folds[:-1])
        return BacktestResult(
            len(x), len(active), wins, losses, draws, wins / len(active) if active else 0.0,
            len(active) / len(predictions) if predictions else 0.0, matrix,
            _longest(outcomes, True), _longest(outcomes, False), len(active) / unique_days,
            by_hour, len(first_train), validation, len(last_test),
        )

