from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from cdhai_june.config import AnalysisConfig
from cdhai_june.models import PatientDataset
from cdhai_june.utils import write_json


def analyze_events(dataset: PatientDataset, config: AnalysisConfig, analysis_dir: Path) -> dict[str, Any]:
    del config
    df = dataset.primary.copy()
    roles = dataset.column_roles
    time_col = roles.get("timestamp")
    glucose_col = roles.get("glucose")
    if not time_col or not glucose_col or time_col not in df or glucose_col not in df:
        return {"available": False, "reason": "Need timestamp and glucose columns for event analysis."}

    if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
        return {"available": False, "reason": "Timestamp column is not parsed as datetime."}

    timed = df.dropna(subset=[time_col]).sort_values(time_col).copy()
    timed[glucose_col] = pd.to_numeric(timed[glucose_col], errors="coerce")
    payload: dict[str, Any] = {"available": True}

    meal = _meal_response(timed, time_col, glucose_col, roles.get("meal"), roles.get("carbs"))
    exercise = _exercise_response(timed, time_col, glucose_col, roles.get("exercise"), roles.get("steps"))
    payload["meal_response"] = meal
    payload["exercise_response"] = exercise
    write_json(analysis_dir / "event_metrics.json", payload)
    return payload


def _meal_response(
    df: pd.DataFrame,
    time_col: str,
    glucose_col: str,
    meal_col: str | None,
    carbs_col: str | None,
) -> dict[str, Any]:
    if not meal_col and not carbs_col:
        return {"available": False, "reason": "No meal or carbohydrate column detected."}
    event_mask = pd.Series(False, index=df.index)
    if meal_col and meal_col in df:
        meal_values = df[meal_col]
        event_mask |= meal_values.notna() & (meal_values.astype(str).str.strip() != "") & (meal_values.astype(str) != "0")
    if carbs_col and carbs_col in df:
        carbs = pd.to_numeric(df[carbs_col], errors="coerce").fillna(0)
        event_mask |= carbs > 0

    events = df.loc[event_mask].copy()
    rows = []
    for _, event in events.iterrows():
        event_time = event[time_col]
        before = _window_mean(df, time_col, glucose_col, event_time, -30, 0)
        after = _window_mean(df, time_col, glucose_col, event_time, 0, 120)
        peak = _window_peak(df, time_col, glucose_col, event_time, 0, 180)
        if before is None or after is None:
            continue
        rows.append(
            {
                "time": event_time.isoformat(),
                "carbs_g": _safe_float(event.get(carbs_col)) if carbs_col else None,
                "mean_delta_0_120": after - before,
                "peak_delta_0_180": (peak - before) if peak is not None else None,
            }
        )
    return _event_rows_summary(rows, "meal", x_key="carbs_g", y_key="peak_delta_0_180")


def _exercise_response(
    df: pd.DataFrame,
    time_col: str,
    glucose_col: str,
    exercise_col: str | None,
    steps_col: str | None,
) -> dict[str, Any]:
    if not exercise_col and not steps_col:
        return {"available": False, "reason": "No exercise/activity column detected."}
    event_mask = pd.Series(False, index=df.index)
    if exercise_col and exercise_col in df:
        values = df[exercise_col]
        if pd.api.types.is_numeric_dtype(values):
            event_mask |= pd.to_numeric(values, errors="coerce").fillna(0) > 0
        else:
            event_mask |= values.notna() & (values.astype(str).str.strip() != "") & (values.astype(str) != "0")
    if steps_col and steps_col in df:
        steps = pd.to_numeric(df[steps_col], errors="coerce").fillna(0)
        event_mask |= steps > max(250, steps.quantile(0.75))

    events = df.loc[event_mask].copy()
    rows = []
    for _, event in events.iterrows():
        event_time = event[time_col]
        before = _window_mean(df, time_col, glucose_col, event_time, -60, 0)
        after = _window_mean(df, time_col, glucose_col, event_time, 0, 180)
        if before is None or after is None:
            continue
        rows.append(
            {
                "time": event_time.isoformat(),
                "steps": _safe_float(event.get(steps_col)) if steps_col else None,
                "mean_delta_0_180": after - before,
            }
        )
    return _event_rows_summary(rows, "exercise", x_key="steps", y_key="mean_delta_0_180")


def _window_mean(
    df: pd.DataFrame,
    time_col: str,
    glucose_col: str,
    event_time: pd.Timestamp,
    start_minutes: int,
    end_minutes: int,
) -> float | None:
    start = event_time + pd.Timedelta(minutes=start_minutes)
    end = event_time + pd.Timedelta(minutes=end_minutes)
    values = df.loc[(df[time_col] >= start) & (df[time_col] <= end), glucose_col].dropna()
    if values.empty:
        return None
    return float(values.mean())


def _window_peak(
    df: pd.DataFrame,
    time_col: str,
    glucose_col: str,
    event_time: pd.Timestamp,
    start_minutes: int,
    end_minutes: int,
) -> float | None:
    start = event_time + pd.Timedelta(minutes=start_minutes)
    end = event_time + pd.Timedelta(minutes=end_minutes)
    values = df.loc[(df[time_col] >= start) & (df[time_col] <= end), glucose_col].dropna()
    if values.empty:
        return None
    return float(values.max())


def _event_rows_summary(rows: list[dict[str, Any]], label: str, x_key: str, y_key: str) -> dict[str, Any]:
    if not rows:
        return {"available": False, "reason": f"No analyzable {label} response windows.", "n_events": 0}
    frame = pd.DataFrame(rows)
    deltas = pd.to_numeric(frame[y_key], errors="coerce").dropna()
    payload: dict[str, Any] = {
        "available": True,
        "n_events": int(len(frame)),
        "mean_delta_mgdl": float(deltas.mean()) if not deltas.empty else None,
        "median_delta_mgdl": float(deltas.median()) if not deltas.empty else None,
        "rows": rows[:50],
    }
    if x_key in frame and frame[x_key].notna().sum() >= 3 and deltas.count() >= 3:
        joined = frame[[x_key, y_key]].dropna()
        if len(joined) >= 3 and joined[x_key].nunique() > 1 and joined[y_key].nunique() > 1:
            rho, p_value = stats.spearmanr(joined[x_key], joined[y_key])
            payload["spearman"] = {
                "x": x_key,
                "y": y_key,
                "rho": float(rho) if not np.isnan(rho) else None,
                "p_value": float(p_value) if not np.isnan(p_value) else None,
                "n": int(len(joined)),
            }
    return payload


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

