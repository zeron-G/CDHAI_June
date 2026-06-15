#!/usr/bin/env python3
"""Metadata-only audit for a WellDoc-SPACE workspace.

The script intentionally reads manifests, paths, file sizes, and schema/column
names only. It does not export patient-level rows or categorical values.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DOMAIN_TERMS = {
    "cgm_glucose": ["cgm", "glucose", "bgvalue", "blood_glucose"],
    "diet_nutrition": ["diet", "meal", "carb", "food", "nutrition", "calorie", "protein", "fat", "fiber"],
    "exercise_activity": ["exercise", "activity", "steps", "distance", "caloriesburned", "heartrate"],
    "medication": ["med", "medication", "dose", "drug", "pharmacy", "prescription"],
    "demographics": ["gender", "birth", "age", "race", "ptt", "patient"],
    "vitals_labs": ["height", "weight", "bp", "heart", "lab", "vital", "hba1c", "cholesterol", "creatinine"],
    "ehr_admission": ["admission", "diagnosis", "procedure", "icu", "emar", "poe", "mimic", "chart"],
    "application_endpoint": ["endpoint", "inference", "deployment", "model_endpoint"],
}
COUNT_KEY_TERMS = ["count", "num", "size", "sample", "patient", "window", "case", "split", "horizon", "stride"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit WellDoc-SPACE manifests without exporting patient rows.")
    parser.add_argument(
        "--base",
        default="/nvme1/group_share/WellDoc-SPACE/_WorkSpace",
        help="WellDoc-SPACE _WorkSpace root.",
    )
    parser.add_argument("--output-json", default="welldoc_space_manifest_summary.json")
    parser.add_argument("--output-md", default="welldoc_space_database_report.md")
    parser.add_argument("--top-n", type=int, default=30, help="Rows to show per report section.")
    args = parser.parse_args()

    base = Path(args.base).expanduser().resolve()
    inventory = audit_workspace(base)
    json_path = Path(args.output_json).expanduser().resolve()
    md_path = Path(args.output_md).expanduser().resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(inventory, top_n=args.top_n), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False))
    return 0


def audit_workspace(base: Path) -> dict[str, Any]:
    records = []
    asset_counts: Counter[str] = Counter()
    store_counts: Counter[str] = Counter()
    keysets: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    examples: dict[str, dict[str, Any]] = {}

    for manifest_path in iter_manifest_paths(base):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive for corrupt remote manifests.
            records.append({"path": relpath(manifest_path, base), "error": f"{type(exc).__name__}: {exc}"})
            continue

        record = summarize_manifest(base, manifest_path, data)
        records.append(record)
        asset_type = record.get("asset_type", "unknown")
        asset_counts[asset_type] += 1
        store_counts[record.get("store", "")] += 1
        keysets[asset_type][tuple(sorted(data.keys()))] += 1
        examples.setdefault(asset_type, {"path": record["path"], "top_level": shallow_top_level(data)})

    domain_counts = classify_domains(records)
    stores = summarize_stores(base)
    sqlite_files = [
        {
            "path": relpath(path, base),
            "bytes": safe_size(path),
            "modified": timestamp(path),
        }
        for path in iter_files(base)
        if path.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".duckdb"}
    ]

    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "safety_policy": {
            "raw_patient_rows_exported": False,
            "categorical_values_exported": False,
            "contents_read": ["manifest.json", "file paths", "file sizes", "schema column names"],
        },
        "host": {
            "hostname": socket.gethostname(),
            "fqdn": socket.getfqdn(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME"),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "base": str(base),
        "base_exists": base.exists(),
        "manifest_count": len(records),
        "asset_counts": dict(asset_counts),
        "store_counts": dict(store_counts),
        "domain_counts": dict(domain_counts),
        "keysets": {
            asset: [{"count": count, "keys": list(keys)} for keys, count in counter.most_common(8)]
            for asset, counter in keysets.items()
        },
        "examples": examples,
        "stores": stores,
        "sqlite_files": sqlite_files,
        "records": records,
        "training_plan": training_plan(),
    }


def iter_manifest_paths(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [name for name in dirnames if not (Path(dirpath) / name).is_symlink()]
        if "manifest.json" in filenames:
            yield Path(dirpath) / "manifest.json"


def iter_files(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [name for name in dirnames if not (Path(dirpath) / name).is_symlink()]
        for filename in filenames:
            yield Path(dirpath) / filename


def summarize_manifest(base: Path, manifest_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    path = relpath(manifest_path, base)
    parts = path.split("/")
    store = parts[0] if parts else ""
    dataset = parts[1] if len(parts) > 1 else ""
    asset_type = str(data.get("asset_type") or data.get("type") or "unknown")
    record: dict[str, Any] = {
        "path": path,
        "store": store,
        "dataset": dataset,
        "asset_type": asset_type,
        "set_name": data.get("set_name"),
        "created_at": data.get("created_at"),
    }

    if asset_type == "RecordSet":
        summarize_record_set(record, data)
    elif "Source" in asset_type or store == "1-SourceStore":
        summarize_source_set(record, data)
    elif "Case" in asset_type or store == "3-CaseStore":
        summarize_case_set(record, data)
    elif "AIData" in asset_type or store == "4-AIDataStore":
        summarize_aidata_set(record, data)
    elif "Model" in asset_type or store == "5-ModelInstanceStore":
        summarize_model_set(record, data)
    elif "endpoint" in asset_type.lower() or store == "6-EndpointStore":
        summarize_endpoint_set(record, data)
    else:
        record["scalar_counts"] = extract_scalar_counts(data)

    return record


def summarize_record_set(record: dict[str, Any], data: dict[str, Any]) -> None:
    structure = data.get("structure") or {}
    source_manifest = data.get("source_set_manifest") or {}
    record["record_set_name"] = data.get("record_set_name")
    record["humans"] = structure.get("humans")
    record["records"] = structure.get("records")
    record["human_columns"] = length_map(structure.get("Human_to_columns"))
    record["record_columns"] = length_map(structure.get("Record_to_columns"))
    record["human_column_names"] = structure.get("Human_to_columns")
    record["record_column_names"] = structure.get("Record_to_columns")
    record["source_set_name"] = source_manifest.get("source_set_name")
    record["source_proc_names"] = source_manifest.get("ProcName_List")
    record["partition_args"] = data.get("Partition_Args")


def summarize_source_set(record: dict[str, Any], data: dict[str, Any]) -> None:
    record["source_set_name"] = data.get("source_set_name") or data.get("set_name")
    proc_to_columns = data.get("ProcName_to_columns") or {}
    record["proc_names"] = data.get("ProcName_List")
    record["proc_columns"] = length_map(proc_to_columns)
    record["proc_column_names"] = proc_to_columns
    record["source_fn"] = data.get("source_fn") or data.get("SourceFn")
    record["processed_at"] = data.get("processed_at")


def summarize_case_set(record: dict[str, Any], data: dict[str, Any]) -> None:
    for key in ["case_set_name", "source_case_set_name", "record_set_name", "case_fn", "CaseFn", "case_type", "task_name"]:
        if key in data:
            record[key] = data[key]
    record["scalar_counts"] = extract_scalar_counts(data)
    record["manifest_shape"] = shallow_top_level(data)


def summarize_aidata_set(record: dict[str, Any], data: dict[str, Any]) -> None:
    record["scalar_counts"] = extract_scalar_counts(data)
    record["manifest_refs"] = {
        key: shallow_top_level(value) if isinstance(value, dict) else value
        for key, value in data.items()
        if any(term in key.lower() for term in ["manifest", "source", "case", "record"])
    }


def summarize_model_set(record: dict[str, Any], data: dict[str, Any]) -> None:
    for key in ["modelinstance_set_name", "model_type", "model_endpoint", "set_name"]:
        if key in data:
            record[key] = data[key]
    record["scalar_counts"] = extract_scalar_counts(data)
    record["manifest_refs"] = {
        key: shallow_top_level(value) if isinstance(value, dict) else value
        for key, value in data.items()
        if any(term in key.lower() for term in ["manifest", "aidata", "model"])
    }


def summarize_endpoint_set(record: dict[str, Any], data: dict[str, Any]) -> None:
    for key in ["endpoint_name", "endpoint_version", "deployment", "example_generation"]:
        if key in data:
            record[key] = data[key]
    model_manifest = data.get("modelinstance_manifest") or {}
    record["model_type"] = model_manifest.get("model_type")
    aidata_manifest = model_manifest.get("aidata_set_manifest") or {}
    record["aidata_set_name"] = aidata_manifest.get("set_name")
    record["scalar_counts"] = extract_scalar_counts(data)


def summarize_stores(base: Path) -> list[dict[str, Any]]:
    stores = []
    if not base.exists():
        return stores
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if not (child.is_dir() or child.is_symlink()):
            continue
        stat = count_files(child)
        datasets = []
        if child.is_dir() and not child.is_symlink():
            for dataset_dir in sorted(child.iterdir(), key=lambda item: item.name):
                if dataset_dir.is_dir() or dataset_dir.is_symlink():
                    ds_stat = count_files(dataset_dir)
                    datasets.append({"name": dataset_dir.name, **ds_stat})
        stores.append({"store": child.name, **stat, "datasets": datasets})
    return stores


def count_files(root: Path) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    ext_counts: Counter[str] = Counter()
    ext_bytes: Counter[str] = Counter()
    if root.is_symlink():
        return {
            "files": 0,
            "bytes": 0,
            "ext_counts": {},
            "ext_bytes": {},
            "symlink_target": os.readlink(root),
        }
    for file_path in iter_files(root):
        size = safe_size(file_path)
        ext = file_path.suffix.lower().lstrip(".") or "[no_ext]"
        file_count += 1
        total_bytes += size
        ext_counts[ext] += 1
        ext_bytes[ext] += size
    return {
        "files": file_count,
        "bytes": total_bytes,
        "ext_counts": dict(ext_counts),
        "ext_bytes": dict(ext_bytes),
    }


def classify_domains(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        text = json.dumps(record, ensure_ascii=False).lower()
        for domain, terms in DOMAIN_TERMS.items():
            if any(term in text for term in terms):
                counts[domain] += 1
    return dict(counts)


def extract_scalar_counts(value: Any, prefix: str = "", depth: int = 0) -> dict[str, Any]:
    if depth > 5 or not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, child in value.items():
        lower_key = str(key).lower()
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if any(term in lower_key for term in COUNT_KEY_TERMS):
            if isinstance(child, str | int | float | bool) or child is None:
                out[full_key] = child
            elif isinstance(child, list | dict):
                out[full_key] = f"{type(child).__name__}[{len(child)}]"
        if isinstance(child, dict):
            out.update(extract_scalar_counts(child, full_key, depth + 1))
    return out


def shallow_top_level(data: Any) -> Any:
    if not isinstance(data, dict):
        return data if isinstance(data, str | int | float | bool) or data is None else type(data).__name__
    out = {}
    for key, value in data.items():
        if isinstance(value, str | int | float | bool) or value is None:
            out[key] = value
        elif isinstance(value, list | dict | tuple):
            out[key] = f"{type(value).__name__}[{len(value)}]"
        else:
            out[key] = type(value).__name__
    return out


def length_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): len(child) if hasattr(child, "__len__") else 0 for key, child in value.items()}


def safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def timestamp(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(microsecond=0).isoformat()
    except OSError:
        return None


def relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def training_plan() -> list[dict[str, str]]:
    return [
        {
            "stage": "Data catalog",
            "action": "Use SourceStore and RecStore manifests as the authoritative schema registry; do not infer schema from raw files.",
        },
        {
            "stage": "Patient event graph",
            "action": "Normalize CGM, diet, exercise, medication, vitals, labs, and application events into patient-time indexed event windows.",
        },
        {
            "stage": "Pretraining",
            "action": "Train sequence models on public/multi-cohort CGM-like assets first, then fine-tune on governed WellDoc cohorts.",
        },
        {
            "stage": "Single-patient agent",
            "action": "Materialize one de-identified patient bundle per run and keep raw identifiers server-side.",
        },
        {
            "stage": "Research loop",
            "action": "For every insight, persist literature review, hypothesis, statistical test, ML model, visualization, gate decision, and report.",
        },
    ]


def render_markdown(inventory: dict[str, Any], top_n: int = 30) -> str:
    lines = [
        "# CDHAI Server Data Report",
        "",
        f"- Generated at: `{inventory['generated_at']}`",
        f"- Host: `{inventory['host'].get('hostname')}`",
        f"- Base: `{inventory['base']}`",
        f"- Raw patient rows exported: `{str(inventory['safety_policy']['raw_patient_rows_exported']).lower()}`",
        "",
        "## Executive Summary",
        "",
        "- The accessible production data is a WellDoc-SPACE workspace, not a conventional SQL server database.",
        "- The workspace is organized as SourceStore, RecStore, CaseStore, AIDataStore, ModelInstanceStore, and EndpointStore.",
        "- Manifests provide the safest immediate integration surface for CDHAI_June because they expose lineage, schemas, and model/data versions without row export.",
        "",
        "## Store Inventory",
        "",
        "| Store | Files | Size | Top extensions | Immediate datasets |",
        "|---|---:|---:|---|---:|",
    ]
    for store in inventory.get("stores", []):
        lines.append(
            "| {store} | {files:,} | {size} | {exts} | {datasets} |".format(
                store=store["store"],
                files=store.get("files", 0),
                size=human_bytes(store.get("bytes", 0)),
                exts=format_counter(store.get("ext_counts", {}), limit=5),
                datasets=len(store.get("datasets", [])),
            )
        )

    lines.extend(
        [
            "",
            "## Manifest Coverage",
            "",
            f"- Total manifests parsed: `{inventory.get('manifest_count', 0)}`",
            f"- Asset types: {format_counter(inventory.get('asset_counts', {}), limit=12)}",
            f"- Domain signals: {format_counter(inventory.get('domain_counts', {}), limit=12)}",
            "",
            "## Dataset Families",
            "",
        ]
    )
    lines.extend(render_family_section(inventory, "1-SourceStore", "SourceStore", top_n))
    lines.extend(render_family_section(inventory, "2-RecStore", "RecStore", top_n))
    lines.extend(render_family_section(inventory, "3-CaseStore", "CaseStore", top_n))
    lines.extend(render_family_section(inventory, "4-AIDataStore", "AIDataStore", top_n))
    lines.extend(render_family_section(inventory, "5-ModelInstanceStore", "ModelInstanceStore", top_n))
    lines.extend(render_family_section(inventory, "6-EndpointStore", "EndpointStore", top_n))

    sqlite_files = inventory.get("sqlite_files", [])
    lines.extend(["", "## SQLite Assets", ""])
    if sqlite_files:
        for item in sqlite_files[:top_n]:
            lines.append(f"- `{item['path']}` ({human_bytes(item['bytes'])})")
    else:
        lines.append("- No SQLite/DuckDB files found under the workspace root.")

    lines.extend(
        [
            "",
            "## Research And Training Use",
            "",
            "- Primary near-term target: single-patient CGM/diet/exercise/medication hypothesis cycles using RecStore patient-event records.",
            "- Pretraining target: use AIDataStore PretrainGlucose, PretrainCGM_Stride4H, FairGlucose, EventGlucose, and OhioT1DM assets for sequence modeling.",
            "- Cross-domain target: use AIREADI and MIMIC-IV derived stores for transfer learning, baseline physiological priors, and robustness checks.",
            "- Endpoint target: reuse EndpointStore OhioT1DM forecast/LTS manifests as concrete examples for model packaging and application handoff.",
            "",
            "## Recommended CDHAI_June Integration",
            "",
            "1. Add a `WellDocWorkspaceLoader` that reads manifest lineage and exposes de-identified patient bundles by `record_set_name` plus patient split.",
            "2. Keep raw tables on the server; write local reports from aggregate statistics, figures, model metrics, and hashed patient run ids.",
            "3. Use haipipe-toolkit source functions as schema contracts for WellDoc, OhioT1DM, CGMacros, Dubosson, AIREADI, Shanghai, and MIMIC-IV mappings.",
            "4. Train/evaluate with patient-level splits first, then time-block splits inside each patient to avoid leakage.",
            "5. For each agent cycle, persist literature review, hypothesis, statistical test, ML model, figure, and gate decision before insight generation.",
            "",
            "## Caveats",
            "",
            "- This report does not claim row-level sample counts unless a manifest explicitly exposes them.",
            "- `/home/cdhai` was not accessible to the current account in the broader server probe.",
            "- `/share/welldocdata` was visible but empty in the broader server probe.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_family_section(inventory: dict[str, Any], store_name: str, title: str, top_n: int) -> list[str]:
    records = [record for record in inventory.get("records", []) if record.get("store") == store_name]
    lines = [f"### {title}", ""]
    if not records:
        return lines + ["- No manifests found.", ""]
    by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_dataset[record.get("dataset") or "[root]"].append(record)
    lines.append("| Dataset | Manifests | Asset types | Key records/counts |")
    lines.append("|---|---:|---|---|")
    for dataset, items in sorted(by_dataset.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:top_n]:
        asset_counts = Counter(str(item.get("asset_type")) for item in items)
        key_records = summarize_key_records(items)
        lines.append(f"| `{dataset}` | {len(items):,} | {format_counter(asset_counts, 5)} | {key_records} |")
    lines.append("")
    return lines


def summarize_key_records(items: list[dict[str, Any]]) -> str:
    names: list[str] = []
    for item in items:
        for key in ["records", "proc_names"]:
            value = item.get(key)
            if isinstance(value, list):
                names.extend(str(part) for part in value[:12])
        counts = item.get("scalar_counts")
        if isinstance(counts, dict):
            names.extend(f"{key}={value}" for key, value in list(counts.items())[:4])
    deduped = []
    for name in names:
        if name and name not in deduped:
            deduped.append(name)
    return ", ".join(deduped[:12]) if deduped else "-"


def format_counter(counter: dict[str, int] | Counter[str], limit: int = 5) -> str:
    if not counter:
        return "-"
    items = counter.items() if isinstance(counter, dict) else counter.most_common()
    sorted_items = sorted(items, key=lambda pair: (-pair[1], pair[0]))[:limit]
    return ", ".join(f"{key}: {value:,}" for key, value in sorted_items)


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


if __name__ == "__main__":
    raise SystemExit(main())
