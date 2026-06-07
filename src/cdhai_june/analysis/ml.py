from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cdhai_june.models import PatientDataset
from cdhai_june.utils import write_json


def run_ml_prediction_baseline(dataset: PatientDataset, analysis_dir: Path, *, plot: bool = True) -> dict[str, Any]:
    """Fit a small deterministic next-glucose predictor for research triangulation."""
    analysis_dir.mkdir(parents=True, exist_ok=True)
    roles = dataset.column_roles
    glucose_col = roles.get("glucose")
    if not glucose_col or glucose_col not in dataset.primary:
        return _write_metrics(analysis_dir, {"available": False, "reason": "No glucose column detected."})

    df = dataset.primary.copy()
    time_col = roles.get("timestamp")
    has_time = bool(time_col and time_col in df and pd.api.types.is_datetime64_any_dtype(df[time_col]))
    if has_time:
        df = df.dropna(subset=[time_col]).sort_values(time_col).copy()
    else:
        df = df.reset_index(drop=True).copy()

    glucose = pd.to_numeric(df[glucose_col], errors="coerce")
    target = glucose.shift(-1)
    features = _feature_frame(df, roles, glucose_col, time_col if has_time else None)
    model_frame = features.copy()
    model_frame["target_next_glucose_mgdl"] = target
    model_frame["current_glucose_mgdl"] = glucose
    model_frame = model_frame.dropna(subset=["target_next_glucose_mgdl", "current_glucose_mgdl"]).copy()
    if len(model_frame) < 12:
        payload = {
            "available": False,
            "reason": "Need at least 12 paired current/next glucose rows for a time-aware baseline.",
            "n_pairs": int(len(model_frame)),
        }
        return _write_metrics(analysis_dir, payload)

    feature_names = list(features.columns)
    split = max(8, int(len(model_frame) * 0.8))
    split = min(split, len(model_frame) - 4)
    train = model_frame.iloc[:split].copy()
    test = model_frame.iloc[split:].copy()
    if len(train) < 8 or len(test) < 4:
        payload = {
            "available": False,
            "reason": "Time split produced too little train or test data.",
            "n_pairs": int(len(model_frame)),
            "train_n": int(len(train)),
            "test_n": int(len(test)),
        }
        return _write_metrics(analysis_dir, payload)

    beta, center, scale = _fit_ridge(train[feature_names].to_numpy(float), train["target_next_glucose_mgdl"].to_numpy(float))
    predictions = _predict_ridge(test[feature_names].to_numpy(float), beta, center, scale)
    observed = test["target_next_glucose_mgdl"].to_numpy(float)
    naive = test["current_glucose_mgdl"].to_numpy(float)
    residual = observed - predictions

    pred_frame = pd.DataFrame(
        {
            "observed_next_glucose_mgdl": observed,
            "predicted_next_glucose_mgdl": predictions,
            "naive_current_glucose_mgdl": naive,
            "residual_mgdl": residual,
        }
    )
    if has_time and time_col:
        pred_frame.insert(0, str(time_col), df.loc[test.index, time_col].astype(str).to_numpy())
    pred_path = analysis_dir / "ml_next_glucose_predictions.csv"
    pred_frame.to_csv(pred_path, index=False)

    figure_path: Path | None = None
    if plot:
        figure_path = analysis_dir / "ml_next_glucose_prediction.png"
        _plot_predictions(observed, predictions, naive, figure_path)

    payload = {
        "available": True,
        "method": "ridge_regression_time_split",
        "target": "next observed glucose value",
        "glucose_column": str(glucose_col),
        "timestamp_column": str(time_col) if has_time else None,
        "features": feature_names,
        "n_pairs": int(len(model_frame)),
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "ridge_alpha": 1.0,
        "horizon_minutes_median": _median_horizon_minutes(df, time_col) if has_time and time_col else None,
        "mae_mgdl": _mae(observed, predictions),
        "rmse_mgdl": _rmse(observed, predictions),
        "r2": _r2(observed, predictions),
        "naive_persistence_mae_mgdl": _mae(observed, naive),
        "naive_persistence_rmse_mgdl": _rmse(observed, naive),
        "residual_mean_mgdl": _safe_float(np.mean(residual)),
        "residual_median_mgdl": _safe_float(np.median(residual)),
        "predictions_path": str(pred_path),
        "figure_path": str(figure_path) if figure_path else None,
        "interpretation_guardrail": (
            "Exploratory single-patient predictive baseline only; it is not a validated clinical forecasting model."
        ),
    }
    return _write_metrics(analysis_dir, payload)


def _feature_frame(
    df: pd.DataFrame,
    roles: dict[str, str | None],
    glucose_col: str,
    time_col: str | None,
) -> pd.DataFrame:
    features = pd.DataFrame(index=df.index)
    features["current_glucose_mgdl"] = pd.to_numeric(df[glucose_col], errors="coerce")
    if time_col:
        hour = df[time_col].dt.hour + df[time_col].dt.minute / 60.0
        features["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        features["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        elapsed = (df[time_col] - df[time_col].min()).dt.total_seconds() / 60.0
        scale = elapsed.max() or 1.0
        features["elapsed_fraction"] = elapsed / scale
    else:
        denom = max(len(df) - 1, 1)
        features["row_fraction"] = np.arange(len(df), dtype=float) / denom

    for role in ("carbs", "steps", "exercise", "medication"):
        column = roles.get(role)
        if column and column in df:
            values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
            if values.abs().sum() > 0:
                features[f"{role}_{column}"] = values.astype(float)

    return features.fillna(0.0)


def _fit_ridge(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0] = 1.0
    z = (x - center) / scale
    design = np.column_stack([np.ones(len(z)), z])
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return beta, center, scale


def _predict_ridge(x: np.ndarray, beta: np.ndarray, center: np.ndarray, scale: np.ndarray) -> np.ndarray:
    z = (x - center) / scale
    design = np.column_stack([np.ones(len(z)), z])
    return design @ beta


def _plot_predictions(observed: np.ndarray, predicted: np.ndarray, naive: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lower = float(np.nanmin([observed.min(), predicted.min(), naive.min()]))
    upper = float(np.nanmax([observed.max(), predicted.max(), naive.max()]))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(observed, predicted, color="#1f77b4", label="Ridge prediction", s=38)
    ax.scatter(observed, naive, color="#ff7f0e", label="Persistence baseline", s=30, alpha=0.75)
    ax.plot([lower, upper], [lower, upper], color="#333333", linewidth=1.0, linestyle="--")
    ax.set_title("Next Glucose Prediction")
    ax.set_xlabel("Observed next glucose (mg/dL)")
    ax.set_ylabel("Predicted next glucose (mg/dL)")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _median_horizon_minutes(df: pd.DataFrame, time_col: str | None) -> float | None:
    if not time_col or time_col not in df:
        return None
    deltas = df[time_col].diff().dropna().dt.total_seconds() / 60.0
    if deltas.empty:
        return None
    return _safe_float(deltas.median())


def _mae(y: np.ndarray, pred: np.ndarray) -> float:
    return _safe_float(np.mean(np.abs(y - pred))) or 0.0


def _rmse(y: np.ndarray, pred: np.ndarray) -> float:
    return _safe_float(np.sqrt(np.mean((y - pred) ** 2))) or 0.0


def _r2(y: np.ndarray, pred: np.ndarray) -> float | None:
    total = float(np.sum((y - y.mean()) ** 2))
    if total == 0:
        return None
    return _safe_float(1.0 - float(np.sum((y - pred) ** 2)) / total)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_metrics(analysis_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    write_json(analysis_dir / "ml_prediction_metrics.json", payload)
    return payload
