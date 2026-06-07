from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from cdhai_june.models import PatientDataset


SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls"}


def _snake_case(name: str) -> str:
    name = name.strip().replace("%", "pct")
    name = re.sub(r"[^0-9A-Za-z]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name.lower() or "column"


def _dedupe_columns(columns: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for column in columns:
        base = _snake_case(str(column))
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append(base if count == 0 else f"{base}_{count + 1}")
    return out


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported input extension: {path.suffix}")


def _maybe_parse_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column in result.columns:
        name = str(column).lower()
        if any(token in name for token in ("time", "date", "datetime", "timestamp", "_dt", "dt_")):
            parsed = pd.to_datetime(result[column], errors="coerce")
            if parsed.notna().sum() >= max(1, int(len(result) * 0.4)):
                result[column] = parsed
    return result


def _normalize_table(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.columns = _dedupe_columns([str(column) for column in result.columns])
    return _maybe_parse_datetimes(result)


def _detect_column_roles(df: pd.DataFrame) -> dict[str, str | None]:
    roles = {
        "patient_id": None,
        "timestamp": None,
        "glucose": None,
        "carbs": None,
        "meal": None,
        "exercise": None,
        "steps": None,
        "medication": None,
    }
    for column in df.columns:
        name = str(column).lower()
        if roles["patient_id"] is None and any(token in name for token in ("patient_id", "pid", "subject_id", "user_id")):
            roles["patient_id"] = column
        if roles["timestamp"] is None and pd.api.types.is_datetime64_any_dtype(df[column]):
            roles["timestamp"] = column
        if roles["glucose"] is None and (
            "glucose" in name or "mgdl" in name or name in {"cgm", "sgv", "sensor_value"}
        ):
            roles["glucose"] = column
        if roles["carbs"] is None and any(token in name for token in ("carb", "cho", "carbohydrate")):
            roles["carbs"] = column
        if roles["meal"] is None and any(token in name for token in ("meal", "food", "diet")):
            roles["meal"] = column
        if roles["exercise"] is None and any(token in name for token in ("exercise", "activity", "workout", "active_min")):
            roles["exercise"] = column
        if roles["steps"] is None and "step" in name:
            roles["steps"] = column
        if roles["medication"] is None and any(token in name for token in ("med", "insulin", "dose")):
            roles["medication"] = column
    return roles


def _discover_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = [item for item in sorted(path.iterdir()) if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        raise FileNotFoundError(f"No supported data files found in {path}")
    return files


def _infer_patient_id(primary: pd.DataFrame, roles: dict[str, str | None], fallback: str) -> str:
    patient_column = roles.get("patient_id")
    if patient_column and patient_column in primary:
        values = primary[patient_column].dropna().astype(str).unique()
        if len(values) == 1:
            return values[0]
        if len(values) > 1:
            return "multi_patient_input"
    return fallback


def load_patient_dataset(input_path: str | Path, patient_id: str | None = None) -> PatientDataset:
    path = Path(input_path).expanduser().resolve()
    files = _discover_files(path)
    tables: dict[str, pd.DataFrame] = {}
    for file_path in files:
        table_name = _snake_case(file_path.stem)
        tables[table_name] = _normalize_table(_read_table(file_path))

    primary_table = max(tables, key=lambda key: len(tables[key]))
    roles = _detect_column_roles(tables[primary_table])
    resolved_patient_id = patient_id or _infer_patient_id(tables[primary_table], roles, path.stem)
    return PatientDataset(
        patient_id=str(resolved_patient_id),
        tables=tables,
        source_path=path,
        primary_table=primary_table,
        column_roles=roles,
    )

