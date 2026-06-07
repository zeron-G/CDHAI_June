from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cdhai_june.config import AnalysisConfig
from cdhai_june.models import PatientDataset
from cdhai_june.utils import write_json


def analyze_cgm(dataset: PatientDataset, config: AnalysisConfig, analysis_dir: Path) -> dict[str, Any]:
    df = dataset.primary.copy()
    glucose_col = dataset.column_roles.get("glucose")
    time_col = dataset.column_roles.get("timestamp")
    if not glucose_col or glucose_col not in df:
        return {"available": False, "reason": "No glucose/CGM column detected."}

    glucose = pd.to_numeric(df[glucose_col], errors="coerce")
    valid = df.loc[glucose.notna()].copy()
    valid[glucose_col] = glucose.dropna()
    if valid.empty:
        return {"available": False, "reason": "Glucose column has no numeric values."}

    thresholds = config.cgm
    values = valid[glucose_col].astype(float)
    metrics: dict[str, Any] = {
        "available": True,
        "glucose_column": glucose_col,
        "timestamp_column": time_col,
        "n_readings": int(values.count()),
        "mean_mgdl": float(values.mean()),
        "median_mgdl": float(values.median()),
        "std_mgdl": float(values.std()) if len(values) > 1 else 0.0,
        "min_mgdl": float(values.min()),
        "max_mgdl": float(values.max()),
        "cv_pct": float(values.std() / values.mean() * 100) if values.mean() else None,
        "gmi_pct": float(3.31 + 0.02392 * values.mean()),
        "time_below_range_pct": _pct(values < thresholds.low_mgdl),
        "time_very_low_pct": _pct(values < thresholds.very_low_mgdl),
        "time_in_range_pct": _pct((values >= thresholds.target_low_mgdl) & (values <= thresholds.target_high_mgdl)),
        "time_above_range_pct": _pct(values > thresholds.target_high_mgdl),
        "time_very_high_pct": _pct(values > thresholds.very_high_mgdl),
    }

    if time_col and time_col in valid and pd.api.types.is_datetime64_any_dtype(valid[time_col]):
        timed = valid[[time_col, glucose_col]].dropna().sort_values(time_col)
        metrics.update(_time_metrics(timed, time_col, glucose_col))
        daily = _daily_metrics(timed, time_col, glucose_col, thresholds.target_low_mgdl, thresholds.target_high_mgdl)
        hourly = _hourly_metrics(timed, time_col, glucose_col)
        metrics["daily"] = daily
        metrics["hourly_mean_mgdl"] = hourly
        if config.plot:
            _plot_cgm_trace(timed, time_col, glucose_col, analysis_dir / "cgm_trace.png")
            _plot_hourly_profile(hourly, analysis_dir / "cgm_hourly_profile.png")

    write_json(analysis_dir / "cgm_metrics.json", metrics)
    return metrics


def _pct(mask: pd.Series) -> float:
    if len(mask) == 0:
        return 0.0
    return float(mask.mean() * 100)


def _time_metrics(df: pd.DataFrame, time_col: str, glucose_col: str) -> dict[str, Any]:
    if len(df) < 2:
        return {}
    deltas = df[time_col].diff().dropna().dt.total_seconds() / 60
    median_interval = float(deltas.median()) if not deltas.empty else None
    gap_threshold = max(30.0, (median_interval or 5.0) * 3)
    gaps = deltas[deltas > gap_threshold]
    return {
        "start": df[time_col].min().isoformat(),
        "end": df[time_col].max().isoformat(),
        "median_sampling_minutes": median_interval,
        "large_gap_count": int(len(gaps)),
        "large_gap_minutes_max": float(gaps.max()) if not gaps.empty else 0.0,
        "glucose_autocorr_lag1": _autocorr(df[glucose_col].astype(float), lag=1),
    }


def _daily_metrics(
    df: pd.DataFrame,
    time_col: str,
    glucose_col: str,
    target_low: float,
    target_high: float,
) -> list[dict[str, Any]]:
    temp = df.copy()
    temp["date"] = temp[time_col].dt.date.astype(str)
    rows = []
    for date, group in temp.groupby("date"):
        values = group[glucose_col].astype(float)
        rows.append(
            {
                "date": date,
                "n": int(len(values)),
                "mean_mgdl": float(values.mean()),
                "time_in_range_pct": _pct((values >= target_low) & (values <= target_high)),
            }
        )
    return rows


def _hourly_metrics(df: pd.DataFrame, time_col: str, glucose_col: str) -> list[dict[str, Any]]:
    temp = df.copy()
    temp["hour"] = temp[time_col].dt.hour
    rows = []
    for hour, group in temp.groupby("hour"):
        rows.append(
            {
                "hour": int(hour),
                "mean_mgdl": float(group[glucose_col].astype(float).mean()),
                "n": int(len(group)),
            }
        )
    return rows


def _autocorr(series: pd.Series, lag: int) -> float | None:
    if len(series) <= lag + 2:
        return None
    value = series.autocorr(lag=lag)
    if value is None or np.isnan(value):
        return None
    return float(value)


def _plot_cgm_trace(df: pd.DataFrame, time_col: str, glucose_col: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df[time_col], df[glucose_col], linewidth=1.6, color="#1f77b4")
    ax.axhspan(70, 180, color="#2ca02c", alpha=0.10)
    ax.axhline(70, color="#d62728", linewidth=0.8, linestyle="--")
    ax.axhline(180, color="#d62728", linewidth=0.8, linestyle="--")
    ax.set_title("CGM Trace")
    ax.set_ylabel("Glucose (mg/dL)")
    ax.set_xlabel("Time")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_hourly_profile(hourly: list[dict[str, Any]], path: Path) -> None:
    if not hourly:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(hourly)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(frame["hour"], frame["mean_mgdl"], color="#4c78a8")
    ax.axhspan(70, 180, color="#2ca02c", alpha=0.10)
    ax.set_title("Mean Glucose by Hour")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Mean mg/dL")
    ax.set_xticks(range(0, 24, 3))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)

