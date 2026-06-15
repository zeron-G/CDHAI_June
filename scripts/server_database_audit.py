#!/usr/bin/env python3
"""Server-side database inventory for CDHAI_June.

This script is designed to run on the database host. It collects schema,
aggregate table/column statistics, and training-readiness signals without
printing raw patient rows or categorical values.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SENSITIVE_NAME_RE = re.compile(
    r"(patient|subject|person|user|name|email|phone|address|street|city|state|zip|mrn|ssn|dob|birth|"
    r"token|secret|password|auth)",
    re.IGNORECASE,
)
DOMAIN_PATTERNS = {
    "patient_identity": re.compile(r"(patient|subject|person|user|mrn)", re.IGNORECASE),
    "timestamp": re.compile(r"(time|date|timestamp|datetime|created|updated)", re.IGNORECASE),
    "glucose_cgm": re.compile(r"(glucose|cgm|sgv|sensor|mgdl|blood.?sugar)", re.IGNORECASE),
    "meal_food": re.compile(r"(meal|food|diet|carb|cho|calorie)", re.IGNORECASE),
    "activity": re.compile(r"(exercise|activity|steps|workout|heart.?rate|hr)", re.IGNORECASE),
    "medication": re.compile(r"(med|insulin|dose|drug|rx)", re.IGNORECASE),
    "message_ui": re.compile(r"(message|sms|notification|ui|click|checklist|suggestion|engagement)", re.IGNORECASE),
    "outcome_label": re.compile(r"(label|outcome|target|response|event|class)", re.IGNORECASE),
}
NUMERIC_TYPES = {
    "smallint",
    "integer",
    "bigint",
    "decimal",
    "numeric",
    "real",
    "double precision",
    "smallserial",
    "serial",
    "bigserial",
}
TEMPORAL_TYPE_RE = re.compile(r"(timestamp|date|time)", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit server databases with aggregate-only outputs.")
    parser.add_argument("--output-dir", default="database_audit_output", help="Directory for JSON and Markdown reports.")
    parser.add_argument("--max-exact-rows", type=int, default=100_000, help="Only run exact column stats under this row estimate.")
    parser.add_argument("--max-columns-per-table", type=int, default=40, help="Limit exact stats columns per table.")
    parser.add_argument(
        "--sqlite-root",
        action="append",
        default=[],
        help="Root to search for SQLite files. Can be repeated. Defaults to current directory only.",
    )
    parser.add_argument("--sqlite-max-files", type=int, default=200, help="Maximum SQLite files to inspect.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory = {
        "generated_at": now(),
        "safety_policy": {
            "raw_rows_exported": False,
            "categorical_values_exported": False,
            "sensitive_columns_value_stats_skipped": True,
            "notes": [
                "This audit emits schema, counts, ranges, and missingness only.",
                "Columns with identifier/PHI-like names are flagged and excluded from min/max value stats.",
            ],
        },
        "host": host_context(),
        "executables": executable_context(),
        "listening_ports": listening_ports(),
        "postgresql": audit_postgresql(args.max_exact_rows, args.max_columns_per_table),
        "sqlite": audit_sqlite(args.sqlite_root, args.sqlite_max_files),
    }
    inventory["training_readiness"] = training_readiness(inventory)

    json_path = output_dir / "database_inventory.json"
    markdown_path = output_dir / "database_inventory_report.md"
    json_path.write_text(json.dumps(to_jsonable(inventory), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(inventory), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path)}, ensure_ascii=False))
    return 0


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def host_context() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "fqdn": socket.getfqdn(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cwd": str(Path.cwd()),
    }


def executable_context() -> dict[str, str | None]:
    names = ["psql", "sqlite3", "mysql", "mariadb", "mongosh", "redis-cli", "ss", "pg_lsclusters"]
    return {name: shutil.which(name) for name in names}


def listening_ports() -> list[dict[str, str]]:
    if not shutil.which("ss"):
        return []
    proc = run(["ss", "-ltn"], timeout=15)
    if proc.returncode != 0:
        return []
    rows = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            rows.append({"state": parts[0], "local_address": parts[3], "peer_address": parts[4] if len(parts) > 4 else ""})
    return rows


def audit_postgresql(max_exact_rows: int, max_columns_per_table: int) -> dict[str, Any]:
    if not shutil.which("psql"):
        return {"available": False, "reason": "psql executable not found on server PATH."}

    context: dict[str, Any] = {"available": True, "databases": [], "errors": []}
    dbs = []
    last_error = ""
    for candidate in unique(["postgres", os.environ.get("PGDATABASE", "")]):
        try:
            dbs = [
                row["datname"]
                for row in psql_csv(
                    candidate,
                    "SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate ORDER BY datname;",
                    timeout=30,
                )
            ]
            break
        except RuntimeError as exc:
            last_error = str(exc)
    if not dbs:
        return {
            "available": False,
            "reason": "Unable to enumerate PostgreSQL databases with current server-side credentials.",
            "error": last_error,
        }

    for dbname in dbs:
        try:
            context["databases"].append(audit_postgresql_database(dbname, max_exact_rows, max_columns_per_table))
        except Exception as exc:  # noqa: BLE001 - audit should continue across databases
            context["errors"].append({"database": dbname, "error": str(exc)})
    context["summary"] = summarize_postgresql(context["databases"])
    return context


def audit_postgresql_database(dbname: str, max_exact_rows: int, max_columns_per_table: int) -> dict[str, Any]:
    size_rows = psql_csv(dbname, "SELECT current_database() AS database_name, pg_database_size(current_database()) AS size_bytes;")
    tables = psql_csv(
        dbname,
        """
        SELECT
          n.nspname AS schema_name,
          c.relname AS table_name,
          c.relkind AS relation_kind,
          pg_total_relation_size(c.oid) AS total_bytes,
          GREATEST(COALESCE(s.n_live_tup, c.reltuples)::bigint, 0) AS estimated_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relkind IN ('r', 'p', 'm', 'v')
        ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname;
        """,
    )
    columns = psql_csv(
        dbname,
        """
        SELECT
          table_schema AS schema_name,
          table_name,
          column_name,
          ordinal_position,
          data_type,
          udt_name,
          is_nullable
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name, ordinal_position;
        """,
    )
    column_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for column in columns:
        column["sensitive_name"] = str(bool(is_sensitive_name(column["column_name"]))).lower()
        column["domain_tags"] = ",".join(domain_tags(column["column_name"]))
        column_groups[(column["schema_name"], column["table_name"])].append(column)

    table_records = []
    for table in tables:
        table_columns = column_groups.get((table["schema_name"], table["table_name"]), [])
        estimated_rows = int_or_zero(table["estimated_rows"])
        record = {
            **table,
            "estimated_rows": estimated_rows,
            "total_bytes": int_or_zero(table["total_bytes"]),
            "columns": table_columns,
            "column_stats": [],
            "exact_stats_attempted": False,
        }
        if table["relation_kind"] in {"r", "p", "m"} and estimated_rows <= max_exact_rows:
            record["exact_stats_attempted"] = True
            record["column_stats"] = safe_table_stats(dbname, table, table_columns[:max_columns_per_table])
        table_records.append(record)

    return {
        "database_name": dbname,
        "size_bytes": int_or_zero(size_rows[0]["size_bytes"]) if size_rows else None,
        "table_count": len(table_records),
        "column_count": len(columns),
        "tables": table_records,
        "domain_summary": summarize_domains(columns),
        "sensitive_column_count": sum(1 for column in columns if is_sensitive_name(column["column_name"])),
    }


def safe_table_stats(dbname: str, table: dict[str, str], columns: list[dict[str, str]]) -> list[dict[str, Any]]:
    schema = quote_ident(table["schema_name"])
    name = quote_ident(table["table_name"])
    out = []
    for column in columns:
        col_name = column["column_name"]
        qcol = quote_ident(col_name)
        sensitive = is_sensitive_name(col_name)
        data_type = column["data_type"]
        expressions = [
            "count(*)::bigint AS row_count",
            f"count({qcol})::bigint AS non_null_count",
            f"(count(*) - count({qcol}))::bigint AS null_count",
        ]
        include_value_stats = not sensitive
        if include_value_stats and is_numeric_type(data_type):
            expressions.extend(
                [
                    f"min({qcol})::text AS min_value",
                    f"max({qcol})::text AS max_value",
                    f"avg({qcol})::text AS mean_value",
                    f"stddev_samp({qcol})::text AS stddev_value",
                ]
            )
        elif include_value_stats and is_temporal_type(data_type):
            expressions.extend([f"min({qcol})::text AS min_value", f"max({qcol})::text AS max_value"])
        sql = f"SELECT {', '.join(expressions)} FROM {schema}.{name};"
        try:
            rows = psql_csv(dbname, sql, timeout=60)
            stats = rows[0] if rows else {}
            out.append(
                {
                    "column_name": col_name,
                    "data_type": data_type,
                    "sensitive_name": sensitive,
                    "domain_tags": domain_tags(col_name),
                    "row_count": int_or_none(stats.get("row_count")),
                    "non_null_count": int_or_none(stats.get("non_null_count")),
                    "null_count": int_or_none(stats.get("null_count")),
                    "null_pct": pct(int_or_none(stats.get("null_count")), int_or_none(stats.get("row_count"))),
                    "min_value": stats.get("min_value"),
                    "max_value": stats.get("max_value"),
                    "mean_value": stats.get("mean_value"),
                    "stddev_value": stats.get("stddev_value"),
                }
            )
        except RuntimeError as exc:
            out.append({"column_name": col_name, "data_type": data_type, "error": str(exc)})
    return out


def audit_sqlite(roots: list[str], max_files: int) -> dict[str, Any]:
    search_roots = [Path(root).expanduser() for root in roots] if roots else [Path.cwd()]
    files: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for pattern in ("*.sqlite", "*.sqlite3", "*.db"):
            files.extend(path for path in root.rglob(pattern) if path.is_file())
    files = sorted(set(files))[:max_files]
    databases = []
    for path in files:
        try:
            databases.append(audit_sqlite_file(path))
        except Exception as exc:  # noqa: BLE001 - keep auditing other files
            databases.append({"path": str(path), "available": False, "error": str(exc)})
    return {"available": bool(files), "searched_roots": [str(root) for root in search_roots], "file_count": len(files), "databases": databases}


def audit_sqlite_file(path: Path) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        tables = [
            dict(row)
            for row in con.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        table_records = []
        for table in tables:
            table_name = table["name"]
            columns = [dict(row) for row in con.execute(f"PRAGMA table_info({quote_sqlite_ident(table_name)})")]
            count = con.execute(f"SELECT count(*) FROM {quote_sqlite_ident(table_name)}").fetchone()[0]
            table_records.append(
                {
                    "table_name": table_name,
                    "relation_kind": table["type"],
                    "row_count": int(count),
                    "columns": [
                        {
                            "column_name": column["name"],
                            "data_type": column["type"],
                            "is_nullable": not bool(column["notnull"]),
                            "sensitive_name": is_sensitive_name(column["name"]),
                            "domain_tags": domain_tags(column["name"]),
                        }
                        for column in columns
                    ],
                }
            )
        return {"path": str(path), "available": True, "size_bytes": path.stat().st_size, "tables": table_records}
    finally:
        con.close()


def psql_csv(dbname: str, sql: str, timeout: int = 60) -> list[dict[str, str]]:
    args = ["psql", "-X", "--csv", "-v", "ON_ERROR_STOP=1", "-P", "pager=off", "-d", dbname, "-c", sql]
    env = dict(os.environ)
    env.setdefault("PGCONNECT_TIMEOUT", "5")
    proc = run(args, timeout=timeout, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"psql exited {proc.returncode}")
    return list(csv.DictReader(proc.stdout.splitlines()))


def run(args: list[str], timeout: int = 60, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, env=env, check=False)


def render_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# Server Database Inventory Report",
        "",
        f"- Generated at: `{inventory['generated_at']}`",
        f"- Host: `{inventory['host'].get('hostname')}`",
        f"- User: `{inventory['host'].get('user')}`",
        "- Raw patient rows exported: `false`",
        "",
        "## Database Services",
    ]
    ports = inventory.get("listening_ports", [])
    if ports:
        for row in ports[:30]:
            lines.append(f"- `{row.get('local_address')}`")
    else:
        lines.append("- No listening-port inventory available from current permissions.")

    pg = inventory.get("postgresql", {})
    lines.extend(["", "## PostgreSQL"])
    if not pg.get("available"):
        lines.append(f"- Not available: {pg.get('reason')}")
        if pg.get("error"):
            lines.append(f"- Error: `{str(pg.get('error'))[:300]}`")
    else:
        summary = pg.get("summary", {})
        lines.append(
            f"- Databases: {summary.get('database_count', 0)}; tables/views: {summary.get('table_count', 0)}; "
            f"columns: {summary.get('column_count', 0)}; estimated rows: {summary.get('estimated_rows', 0)}."
        )
        lines.append("- Largest tables:")
        for row in summary.get("largest_tables", [])[:15]:
            lines.append(
                f"  - `{row['database']}.{row['schema']}.{row['table']}` rows~{row['estimated_rows']} "
                f"size={bytes_human(row['total_bytes'])}"
            )
        lines.append("- Domain signal counts:")
        for domain, count in summary.get("domain_counts", {}).items():
            lines.append(f"  - `{domain}`: {count}")
        lines.append("- Sensitive-name columns are flagged for de-identification before modeling.")

    sqlite_payload = inventory.get("sqlite", {})
    lines.extend(["", "## SQLite"])
    if sqlite_payload.get("available"):
        lines.append(f"- SQLite-like files inspected: {sqlite_payload.get('file_count', 0)}")
    else:
        lines.append("- No SQLite files found under configured roots.")

    readiness = inventory.get("training_readiness", {})
    lines.extend(["", "## Training And Research Readiness"])
    for item in readiness.get("recommendations", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Safe Use Plan",
            "- Build a de-identified data catalog first; never train from directly identifiable columns.",
            "- Split train/validation/test by patient and time to prevent leakage.",
            "- Normalize all patient records into a time-series event schema: CGM observations, meals, activity, medication, messages, UI actions, and outcomes.",
            "- Use aggregate reports for exploration; require IRB/data-use approval before exporting row-level data from the server.",
            "- Track dataset version, extraction SQL, cohort rules, feature transforms, model config, and evaluation metrics for every experiment.",
        ]
    )
    return "\n".join(lines) + "\n"


def summarize_postgresql(databases: list[dict[str, Any]]) -> dict[str, Any]:
    largest = []
    domain_counts: Counter[str] = Counter()
    estimated_rows = 0
    table_count = 0
    column_count = 0
    for db in databases:
        table_count += int(db.get("table_count", 0))
        column_count += int(db.get("column_count", 0))
        for domain, count in db.get("domain_summary", {}).items():
            domain_counts[domain] += int(count)
        for table in db.get("tables", []):
            estimated_rows += int_or_zero(table.get("estimated_rows"))
            largest.append(
                {
                    "database": db.get("database_name"),
                    "schema": table.get("schema_name"),
                    "table": table.get("table_name"),
                    "estimated_rows": int_or_zero(table.get("estimated_rows")),
                    "total_bytes": int_or_zero(table.get("total_bytes")),
                }
            )
    largest.sort(key=lambda row: (row["total_bytes"], row["estimated_rows"]), reverse=True)
    return {
        "database_count": len(databases),
        "table_count": table_count,
        "column_count": column_count,
        "estimated_rows": estimated_rows,
        "largest_tables": largest[:50],
        "domain_counts": dict(domain_counts),
    }


def summarize_domains(columns: list[dict[str, str]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for column in columns:
        for tag in domain_tags(column.get("column_name", "")):
            counts[tag] += 1
    return dict(counts)


def training_readiness(inventory: dict[str, Any]) -> dict[str, Any]:
    domain_counts: Counter[str] = Counter()
    pg = inventory.get("postgresql", {})
    if pg.get("available"):
        for domain, count in pg.get("summary", {}).get("domain_counts", {}).items():
            domain_counts[domain] += int(count)
    for db in inventory.get("sqlite", {}).get("databases", []):
        for table in db.get("tables", []):
            for column in table.get("columns", []):
                for tag in column.get("domain_tags", []):
                    domain_counts[tag] += 1

    recommendations = []
    if domain_counts.get("glucose_cgm"):
        recommendations.append("CGM/glucose signals detected: prioritize next-glucose forecasting and time-in-range research cohorts.")
    else:
        recommendations.append("No obvious CGM/glucose columns detected yet: inspect table names and add domain aliases before modeling.")
    if domain_counts.get("meal_food") or domain_counts.get("activity") or domain_counts.get("medication"):
        recommendations.append("Behavior/event signals detected: build event-aligned windows for meal, activity, and medication response analyses.")
    if domain_counts.get("message_ui"):
        recommendations.append("Application/message/UI signals detected: model engagement and suggestion-response outcomes separately from glucose physiology.")
    if domain_counts.get("patient_identity"):
        recommendations.append("Patient identity columns detected: create a hashed subject map and enforce patient-level splits.")
    recommendations.append("Use haipipe-toolkit adapters to transform database tables into versioned PatientDataset/event-window datasets.")
    return {"domain_counts": dict(domain_counts), "recommendations": recommendations}


def is_sensitive_name(name: str) -> bool:
    return bool(SENSITIVE_NAME_RE.search(str(name)))


def domain_tags(name: str) -> list[str]:
    text = str(name)
    return [tag for tag, pattern in DOMAIN_PATTERNS.items() if pattern.search(text)]


def is_numeric_type(data_type: str) -> bool:
    return data_type.lower() in NUMERIC_TYPES


def is_temporal_type(data_type: str) -> bool:
    return bool(TEMPORAL_TYPE_RE.search(data_type))


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_sqlite_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def unique(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def int_or_zero(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def pct(part: int | None, total: int | None) -> float | None:
    if part is None or total in (None, 0):
        return None
    return round(part / total * 100, 4)


def bytes_human(value: int | str | None) -> str:
    number = float(int_or_zero(value))
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if number < 1024:
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} PB"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
