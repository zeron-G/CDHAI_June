#!/usr/bin/env python3
"""Build a local composite dataset from an A-User-Store zip archive.

The builder uses the aligned RecStore layer:
`A-User-Store/UserGroup-*/Subject-*/2-RecStore/Record-HmPtt.*/RecAttr.parquet`.
Agent snapshot copies are inventoried but excluded from the canonical outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an aligned multi-patient composite from A-User-Store.zip.")
    parser.add_argument("--zip", required=True, help="Path to A-User-Store.zip.")
    parser.add_argument("--output-dir", default="reports/a_user_store_composite/latest")
    args = parser.parse_args()

    zip_path = Path(args.zip).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = build_composite(zip_path, output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_composite(zip_path: Path, output_dir: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as archive:
        inventory = inventory_archive(archive)
        rec_frames: dict[str, list[pd.DataFrame]] = defaultdict(list)
        patients: list[pd.DataFrame] = []
        human_summaries: list[pd.DataFrame] = []

        for name in inventory["canonical_recattr_files"]:
            frame = read_parquet_from_zip(archive, name)
            meta = parse_store_path(name)
            record_type = meta["record_type"]
            frame = normalize_frame(frame, meta, zip_path)
            if record_type == "Ptt":
                patients.append(frame)
            else:
                rec_frames[record_type].append(frame)

        for name in inventory["canonical_human_files"]:
            frame = read_parquet_from_zip(archive, name)
            meta = parse_store_path(name)
            human_summaries.append(normalize_frame(frame, meta, zip_path))

    outputs: dict[str, str] = {}
    record_summary_rows: list[dict[str, Any]] = []
    subject_summary_rows: list[dict[str, Any]] = []

    patient_df = concat_or_empty(patients)
    if not patient_df.empty:
        patient_df = sort_patient_frame(patient_df)
    outputs["patients"] = write_parquet(patient_df, output_dir / "patients.parquet")

    human_df = concat_or_empty(human_summaries)
    outputs["human_summary"] = write_parquet(human_df, output_dir / "human_summary.parquet")

    event_frames: list[pd.DataFrame] = []
    for record_type, frames in sorted(rec_frames.items()):
        record_df = concat_or_empty(frames)
        record_df = sort_event_frame(record_df)
        outputs[f"record_{record_type}"] = write_parquet(record_df, output_dir / f"record_{record_type}.parquet")
        event_frames.append(record_df)
        record_summary_rows.append(summarize_record_frame(record_type, record_df))

    events_df = concat_or_empty(event_frames)
    events_df = sort_event_frame(events_df)
    outputs["events"] = write_parquet(events_df, output_dir / "events.parquet")

    subject_summary_rows = summarize_subjects(patient_df, events_df)
    record_summary_df = pd.DataFrame(record_summary_rows).sort_values(["record_type"]).reset_index(drop=True)
    subject_summary_df = pd.DataFrame(subject_summary_rows).sort_values(["user_group", "subject_id"]).reset_index(drop=True)
    outputs["record_summary"] = write_csv(record_summary_df, output_dir / "record_summary.csv")
    outputs["subject_summary"] = write_csv(subject_summary_df, output_dir / "subject_summary.csv")

    manifest = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_zip": str(zip_path),
        "output_dir": str(output_dir),
        "canonical_key": ["PatientID", "DT_s"],
        "deidentified_key": "patient_key",
        "snapshots_excluded_from_canonical": True,
        "inventory": inventory,
        "outputs": outputs,
        "row_counts": {
            "patients": int(len(patient_df)),
            "events": int(len(events_df)),
            "human_summary": int(len(human_df)),
            **{row["record_type"]: int(row["rows"]) for row in record_summary_rows},
        },
        "record_summary": record_summary_rows,
        "subject_count": int(subject_summary_df["subject_key"].nunique()) if not subject_summary_df.empty else 0,
        "patient_count": int(patient_df["patient_key"].nunique()) if not patient_df.empty else 0,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    outputs["manifest"] = str(output_dir / "manifest.json")
    (output_dir / "README.md").write_text(render_report(manifest, subject_summary_df, record_summary_df), encoding="utf-8")
    outputs["report"] = str(output_dir / "README.md")
    return {"output_dir": str(output_dir), "outputs": outputs, "row_counts": manifest["row_counts"]}


def inventory_archive(archive: zipfile.ZipFile) -> dict[str, Any]:
    files = [info.filename for info in archive.infolist() if not info.is_dir()]
    recattr_files = [
        name
        for name in files
        if "/2-RecStore/Record-HmPtt." in name and name.endswith("/RecAttr.parquet")
    ]
    human_files = [
        name
        for name in files
        if "/2-RecStore/Human-HmPtt/Human2RawNum.parquet" in name
    ]
    canonical_recattr = [name for name in recattr_files if "/_agent_dikw_space/" not in name]
    snapshot_recattr = [name for name in recattr_files if "/_agent_dikw_space/" in name]
    canonical_human = [name for name in human_files if "/_agent_dikw_space/" not in name]

    groups: dict[str, set[str]] = defaultdict(set)
    record_types: Counter[str] = Counter()
    for name in canonical_recattr:
        meta = parse_store_path(name)
        groups[meta["user_group"]].add(meta["subject_id"])
        record_types[meta["record_type"]] += 1

    return {
        "zip_file_count": len(files),
        "zip_uncompressed_bytes": sum(info.file_size for info in archive.infolist()),
        "canonical_recattr_count": len(canonical_recattr),
        "snapshot_recattr_count": len(snapshot_recattr),
        "canonical_human_count": len(canonical_human),
        "user_groups": {group: sorted(subjects) for group, subjects in sorted(groups.items())},
        "record_file_counts": dict(record_types),
        "canonical_recattr_files": canonical_recattr,
        "canonical_human_files": canonical_human,
        "snapshot_recattr_examples": snapshot_recattr[:20],
    }


def parse_store_path(name: str) -> dict[str, str]:
    parts = name.split("/")
    recstore_idx = parts.index("2-RecStore")
    subject = parts[recstore_idx - 1].replace("Subject-", "")
    group = parts[recstore_idx - 2].replace("UserGroup-", "")
    record_dir = parts[recstore_idx + 1]
    record_type = record_dir.replace("Record-HmPtt.", "").replace("Human-HmPtt", "Human-HmPtt")
    return {
        "user_group": group,
        "subject_id": subject,
        "subject_key": stable_key(f"{group}:{subject}")[:16],
        "record_type": record_type,
        "source_member": name,
    }


def read_parquet_from_zip(archive: zipfile.ZipFile, name: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(archive.read(name)))


def normalize_frame(frame: pd.DataFrame, meta: dict[str, str], zip_path: Path) -> pd.DataFrame:
    result = frame.copy()
    for column in ["DT_s", "DT_r", "ActivationDate", "MRSegmentModifiedDateTime"]:
        if column in result:
            result[column] = pd.to_datetime(result[column], errors="coerce")
    if "PatientID" in result:
        result.insert(0, "patient_key", result["PatientID"].astype(str).map(lambda value: stable_key(f"{meta['user_group']}:{value}")[:20]))
    else:
        result.insert(0, "patient_key", stable_key(f"{meta['user_group']}:{meta['subject_id']}")[:20])
    result.insert(0, "subject_key", meta["subject_key"])
    result.insert(0, "subject_id", meta["subject_id"])
    result.insert(0, "user_group", meta["user_group"])
    result.insert(0, "record_type", meta["record_type"])
    result["source_member"] = meta["source_member"]
    result["source_archive"] = str(zip_path)
    if "DT_s" in result:
        result["event_time"] = result["DT_s"]
    if "DT_r" in result:
        result["recorded_time"] = result["DT_r"]
    if "DT_tz" in result:
        result["timezone_offset_minutes"] = result["DT_tz"]
    return result


def stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def concat_or_empty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def sort_event_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    sort_cols = [column for column in ["user_group", "PatientID", "DT_s", "record_type"] if column in frame]
    return frame.sort_values(sort_cols, kind="stable").reset_index(drop=True) if sort_cols else frame.reset_index(drop=True)


def sort_patient_frame(frame: pd.DataFrame) -> pd.DataFrame:
    sort_cols = [column for column in ["user_group", "PatientID", "PID"] if column in frame]
    return frame.sort_values(sort_cols, kind="stable").reset_index(drop=True) if sort_cols else frame.reset_index(drop=True)


def summarize_record_frame(record_type: str, frame: pd.DataFrame) -> dict[str, Any]:
    row: dict[str, Any] = {
        "record_type": record_type,
        "rows": int(len(frame)),
        "patients": int(frame["patient_key"].nunique()) if "patient_key" in frame else 0,
        "subjects": int(frame["subject_key"].nunique()) if "subject_key" in frame else 0,
        "columns": ";".join(map(str, frame.columns)),
    }
    if "DT_s" in frame and not frame.empty:
        row["min_DT_s"] = str(frame["DT_s"].min())
        row["max_DT_s"] = str(frame["DT_s"].max())
    if record_type == "CGM5Min" and "BGValue" in frame:
        row["BGValue_non_null"] = int(frame["BGValue"].notna().sum())
        row["BGValue_mean"] = float(frame["BGValue"].mean())
    return row


def summarize_subjects(patient_df: pd.DataFrame, events_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    keys = set()
    for frame in [patient_df, events_df]:
        if not frame.empty:
            keys.update(zip(frame["user_group"], frame["subject_id"], frame["subject_key"], strict=False))
    for user_group, subject_id, subject_key in keys:
        ev = events_df[(events_df["user_group"] == user_group) & (events_df["subject_id"] == subject_id)] if not events_df.empty else pd.DataFrame()
        pt = patient_df[(patient_df["user_group"] == user_group) & (patient_df["subject_id"] == subject_id)] if not patient_df.empty else pd.DataFrame()
        counts = ev["record_type"].value_counts().to_dict() if not ev.empty else {}
        row = {
            "user_group": user_group,
            "subject_id": subject_id,
            "subject_key": subject_key,
            "patient_rows": int(len(pt)),
            "event_rows": int(len(ev)),
            "record_counts": json.dumps(counts, sort_keys=True),
        }
        if not ev.empty and "DT_s" in ev:
            row["min_DT_s"] = str(ev["DT_s"].min())
            row["max_DT_s"] = str(ev["DT_s"].max())
        rows.append(row)
    return rows


def write_parquet(frame: pd.DataFrame, path: Path) -> str:
    frame.to_parquet(path, index=False)
    return str(path)


def write_csv(frame: pd.DataFrame, path: Path) -> str:
    frame.to_csv(path, index=False)
    return str(path)


def render_report(manifest: dict[str, Any], subject_summary: pd.DataFrame, record_summary: pd.DataFrame) -> str:
    lines = [
        "# A-User-Store Composite Dataset",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        f"- Canonical key: `{manifest['canonical_key']}`",
        f"- Patient rows: `{manifest['row_counts']['patients']}`",
        f"- Event rows: `{manifest['row_counts']['events']}`",
        f"- Subjects: `{manifest['subject_count']}`",
        f"- Patients: `{manifest['patient_count']}`",
        f"- Agent snapshots excluded from canonical outputs: `{str(manifest['snapshots_excluded_from_canonical']).lower()}`",
        "",
        "## Outputs",
        "",
    ]
    for key, path in manifest["outputs"].items():
        lines.append(f"- `{key}`: `{path}`")
    lines.extend(["", "## Record Summary", "", record_summary.to_markdown(index=False), "", "## Subject Summary", ""])
    safe_subject = subject_summary.copy()
    if not safe_subject.empty:
        lines.append(safe_subject.to_markdown(index=False))
    else:
        lines.append("- No subjects found.")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `patient_key` and `subject_key` are stable SHA-256 derived keys for local joins.",
            "- Original `PatientID` is preserved in the gitignored local artifact because it is the alignment key in the supplied data.",
            "- `_agent_dikw_space/snapshot-*` RecStore copies are excluded to prevent duplicate historical agent-state records.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
