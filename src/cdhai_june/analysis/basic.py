from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from cdhai_june.analysis.cgm import analyze_cgm
from cdhai_june.analysis.events import analyze_events
from cdhai_june.config import AnalysisConfig
from cdhai_june.models import Artifact, PatientDataset
from cdhai_june.utils import write_json


class BasicAnalyzer:
    def __init__(self, config: AnalysisConfig) -> None:
        self.config = config

    def run(self, dataset: PatientDataset, analysis_dir: Path) -> dict[str, Any]:
        analysis_dir.mkdir(parents=True, exist_ok=True)
        tables = {
            name: _profile_table(df, self.config.min_numeric_non_null)
            for name, df in dataset.tables.items()
        }
        cgm = analyze_cgm(dataset, self.config, analysis_dir)
        events = analyze_events(dataset, self.config, analysis_dir)
        payload: dict[str, Any] = {
            "patient_id": dataset.patient_id,
            "source_path": str(dataset.source_path),
            "primary_table": dataset.primary_table,
            "column_roles": dataset.column_roles,
            "tables": tables,
            "cgm": cgm,
            "events": events,
        }
        write_json(analysis_dir / "basic_profile.json", payload)
        return payload


def _profile_table(df: pd.DataFrame, min_numeric_non_null: int) -> dict[str, Any]:
    numeric = df.select_dtypes(include="number")
    datetimes = [column for column in df.columns if pd.api.types.is_datetime64_any_dtype(df[column])]
    categorical = [
        column
        for column in df.columns
        if column not in numeric.columns and column not in datetimes
    ]

    profile: dict[str, Any] = {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(map(str, df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "dtypes": {str(column): str(dtype) for column, dtype in df.dtypes.items()},
        "missing": _missingness(df),
        "numeric": {},
        "categorical": {},
        "datetime": {},
    }

    for column in numeric.columns:
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(series) < min_numeric_non_null:
            continue
        profile["numeric"][str(column)] = {
            "count": int(series.count()),
            "mean": float(series.mean()),
            "std": float(series.std()) if len(series) > 1 else 0.0,
            "min": float(series.min()),
            "p25": float(series.quantile(0.25)),
            "median": float(series.median()),
            "p75": float(series.quantile(0.75)),
            "max": float(series.max()),
        }

    for column in categorical[:20]:
        counts = df[column].dropna().astype(str).value_counts().head(10)
        profile["categorical"][str(column)] = {
            "unique": int(df[column].nunique(dropna=True)),
            "top_values": counts.to_dict(),
        }

    for column in datetimes:
        values = df[column].dropna()
        if values.empty:
            continue
        profile["datetime"][str(column)] = {
            "min": values.min().isoformat(),
            "max": values.max().isoformat(),
            "non_null": int(values.count()),
        }

    return profile


def _missingness(df: pd.DataFrame) -> dict[str, Any]:
    rows = max(len(df), 1)
    missing = {}
    for column in df.columns:
        count = int(df[column].isna().sum())
        missing[str(column)] = {
            "count": count,
            "pct": round(count / rows, 4),
        }
    return missing


def artifact_from_path(path: Path, kind: str, summary: str = "") -> Artifact:
    return Artifact(name=path.stem, path=path, kind=kind, summary=summary)

