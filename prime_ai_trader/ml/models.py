from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config.settings import app_data_dir
from ..features.builder import FEATURE_COLUMNS


@dataclass(slots=True)
class FoldMetric:
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    balanced_accuracy: float
    macro_f1: float
    samples: int


@dataclass(slots=True)
class ModelMetric:
    model: str
    balanced_accuracy: float
    macro_f1: float
    folds: list[FoldMetric]


@dataclass(slots=True)
class TrainingReport:
    selected_model: str
    version: str
    trained_at: str
    samples: int
    features: int
    metrics: list[ModelMetric]
    context: dict[str, str | int]


def candidate_models(random_state: int = 42) -> dict[str, Pipeline]:
    scaled = ColumnTransformer([("numeric", Pipeline([
        ("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()),
    ]), FEATURE_COLUMNS)], remainder="drop")
    unscaled = ColumnTransformer([("numeric", SimpleImputer(strategy="median"), FEATURE_COLUMNS)], remainder="drop")
    return {
        "Logistic Regression": Pipeline([("prepare", scaled), ("model", LogisticRegression(max_iter=800, class_weight="balanced", random_state=random_state))]),
        "HistGradientBoosting": Pipeline([("prepare", unscaled), ("model", HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=15, learning_rate=0.06, l2_regularization=0.2, random_state=random_state))]),
        "Random Forest": Pipeline([("prepare", unscaled), ("model", RandomForestClassifier(n_estimators=100, max_depth=7, min_samples_leaf=8, class_weight="balanced_subsample", n_jobs=1, random_state=random_state))]),
        "Gradient Boosting": Pipeline([("prepare", unscaled), ("model", GradientBoostingClassifier(n_estimators=90, max_depth=2, learning_rate=0.05, random_state=random_state))]),
    }


def temporal_folds(length: int, min_train: int = 300, test_size: int = 100, max_train: int = 1200) -> list[tuple[np.ndarray, np.ndarray]]:
    if length < min_train + test_size:
        min_train = max(100, int(length * 0.6))
        test_size = max(30, int(length * 0.15))
    folds = []
    train_end = min_train
    while train_end + test_size <= length:
        train_start = max(0, train_end - max_train)
        folds.append((np.arange(train_start, train_end), np.arange(train_end, train_end + test_size)))
        train_end += test_size
    return folds


def align_supervised_data(features: pd.DataFrame, labels: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Alinha features e labels pelo horário do candle antes de aplicar a máscara válida."""
    aligned_features = features.reindex(columns=FEATURE_COLUMNS)
    if not aligned_features.index.is_unique:
        aligned_features = aligned_features.loc[~aligned_features.index.duplicated(keep="last")]
    aligned_labels = labels
    if not aligned_labels.index.is_unique:
        aligned_labels = aligned_labels.loc[~aligned_labels.index.duplicated(keep="last")]
    aligned_labels = aligned_labels.reindex(aligned_features.index)
    valid_positions = aligned_labels.notna().to_numpy()
    x = aligned_features.iloc[valid_positions]
    y = aligned_labels.iloc[valid_positions].astype(int)
    return x, y


class ModelManager:
    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir or app_data_dir() / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model: Pipeline | None = None
        self.report: TrainingReport | None = None
        self._lock = RLock()
        self.load()

    @property
    def trained(self) -> bool:
        return self.model is not None and self.report is not None

    def train(self, features: pd.DataFrame, labels: pd.Series, context: dict[str, str | int] | None = None) -> TrainingReport:
        x, y = align_supervised_data(features, labels)
        if len(x) < 130:
            raise ValueError("São necessários pelo menos 130 candles válidos para treinar a IA.")
        if y.nunique() < 2:
            raise ValueError("O período não contém classes suficientes para treinamento.")
        folds = temporal_folds(len(x))
        if not folds:
            raise ValueError("Histórico insuficiente para validação walk-forward.")
        model_metrics: list[ModelMetric] = []
        models = candidate_models()
        for name, model in models.items():
            fold_metrics: list[FoldMetric] = []
            for train_idx, test_idx in folds:
                instance = clone(model)
                instance.fit(x.iloc[train_idx], y.iloc[train_idx])
                predicted = instance.predict(x.iloc[test_idx])
                fold_metrics.append(FoldMetric(
                    int(train_idx[0]), int(train_idx[-1]), int(test_idx[0]), int(test_idx[-1]),
                    float(balanced_accuracy_score(y.iloc[test_idx], predicted)),
                    float(f1_score(y.iloc[test_idx], predicted, average="macro", zero_division=0)), len(test_idx),
                ))
            model_metrics.append(ModelMetric(
                name, float(np.mean([f.balanced_accuracy for f in fold_metrics])),
                float(np.mean([f.macro_f1 for f in fold_metrics])), fold_metrics,
            ))
        selected = max(model_metrics, key=lambda metric: (metric.macro_f1, metric.balanced_accuracy))
        trained_model = models[selected.model]
        trained_model.fit(x, y)
        stamp = datetime.now(timezone.utc)
        version = f"ml-{stamp.strftime('%Y%m%d-%H%M%S')}"
        report = TrainingReport(selected.model, version, stamp.isoformat(), len(x), len(FEATURE_COLUMNS), model_metrics, context or {})
        with self._lock:
            self.model = trained_model
            self.report = report
            self.save()
        return report

    def predict_proba(self, features: pd.DataFrame) -> dict[int, float]:
        with self._lock:
            if not self.model:
                raise RuntimeError("A IA ainda não foi treinada.")
            row = features.reindex(columns=FEATURE_COLUMNS).iloc[[-1]]
            probabilities = self.model.predict_proba(row)[0]
            classes = self.model.named_steps["model"].classes_
        return {int(label): float(probability) for label, probability in zip(classes, probabilities)}

    def is_compatible(self, context: dict[str, str | int] | None) -> bool:
        with self._lock:
            if context and (not self.report or self.report.context != context):
                self._activate_unlocked(context)
            if not self.trained:
                return False
            if not context:
                return not bool(self.report.context)
            return self.report.context == context

    @staticmethod
    def _context_key(context: dict[str, str | int]) -> str:
        payload = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()[:24]

    def _context_paths(self, context: dict[str, str | int]) -> tuple[Path, Path]:
        directory = self.model_dir / "contexts"
        directory.mkdir(parents=True, exist_ok=True)
        key = self._context_key(context)
        return directory / f"{key}.joblib", directory / f"{key}.json"

    def _activate_unlocked(self, context: dict[str, str | int]) -> bool:
        model_path, report_path = self._context_paths(context)
        if not model_path.exists() or not report_path.exists():
            return False
        try:
            model = joblib.load(model_path)
            report = self._decode_report(json.loads(report_path.read_text(encoding="utf-8")))
            if report.context != context:
                return False
            self.model, self.report = model, report
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def save(self) -> None:
        if not self.model or not self.report:
            return
        report_text = json.dumps(asdict(self.report), ensure_ascii=False, indent=2)
        joblib.dump(self.model, self.model_dir / "active_model.joblib")
        (self.model_dir / "training_report.json").write_text(report_text, encoding="utf-8")
        if self.report.context:
            model_path, report_path = self._context_paths(self.report.context)
            joblib.dump(self.model, model_path)
            report_path.write_text(report_text, encoding="utf-8")

    @staticmethod
    def _decode_report(raw: dict) -> TrainingReport:
        metrics = []
        for metric in raw["metrics"]:
            folds = [FoldMetric(**fold) for fold in metric["folds"]]
            metrics.append(ModelMetric(metric["model"], metric["balanced_accuracy"], metric["macro_f1"], folds))
        return TrainingReport(raw["selected_model"], raw["version"], raw["trained_at"], raw["samples"], raw["features"], metrics, raw.get("context", {}))

    def load(self) -> None:
        model_path = self.model_dir / "active_model.joblib"
        report_path = self.model_dir / "training_report.json"
        if not model_path.exists() or not report_path.exists():
            return
        try:
            self.model = joblib.load(model_path)
            self.report = self._decode_report(json.loads(report_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError):
            self.model = None
            self.report = None
