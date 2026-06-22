from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from cdhai_june.config import ExternalConfig, HAPFConfig
from cdhai_june.external.haipipe_toolkit import resolve_project_path
from cdhai_june.models import Hypothesis, PatientDataset
from cdhai_june.utils import write_json

_REQUIRED_COHORT_COLUMNS = ("subject_key", "DT_s", "BGValue")


@dataclass(slots=True)
class HAPFStatus:
    repository_url: str
    repository_path: str
    repository_present: bool
    pyproject_present: bool
    installed: bool
    module_origin: str | None
    model_config_present: bool
    install_hint: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def hapf_status(external_config: ExternalConfig, hapf_config: HAPFConfig | None = None) -> HAPFStatus:
    repository_path = resolve_project_path(external_config.hapf_path)
    model_config = resolve_project_path(
        Path((hapf_config or HAPFConfig()).model_config_path)
    )
    try:
        spec = find_spec("hapf")
    except (ImportError, ValueError):
        spec = None
    source_package = repository_path / "src" / "hapf" / "__init__.py"
    return HAPFStatus(
        repository_url=external_config.hapf_url,
        repository_path=str(repository_path),
        repository_present=repository_path.exists(),
        pyproject_present=(repository_path / "pyproject.toml").exists(),
        installed=spec is not None,
        module_origin=spec.origin if spec else (str(source_package) if source_package.exists() else None),
        model_config_present=model_config.exists(),
        install_hint="python -m pip install -e external/cdhai-hapf",
    )


def run_hapf_cycle(
    *,
    dataset: PatientDataset,
    config: HAPFConfig,
    external_config: ExternalConfig,
    cycle: int,
    output_paths: dict[str, Path],
    cache_dir: Path,
    hypotheses: list[Hypothesis],
    runner: Callable[..., dict[str, Any]] | None = None,
    config_loader: Callable[[str | Path], Any] | None = None,
) -> dict[str, Any]:
    readiness_path = output_paths["results"] / "hapf_readiness.json"
    interpretation_path = output_paths["results"] / "hapf_cycle_interpretation.json"
    status = hapf_status(external_config, config)
    readiness: dict[str, Any] = {
        "cycle": cycle,
        "enabled": config.enabled,
        "repository": status.to_json(),
        "required_columns": list(_REQUIRED_COHORT_COLUMNS),
        "cohort_ready": False,
        "target_resolution": "not_resolved",
        "execution_status": "not_started",
    }

    if not config.enabled:
        return _skip(readiness, readiness_path, "HAPF integration is disabled by configuration.")

    cohort_path = _resolve_cohort_path(config, dataset)
    readiness["cohort_source"] = str(cohort_path) if cohort_path else None
    if cohort_path is None or not cohort_path.exists():
        return _skip(
            readiness,
            readiness_path,
            "No HAPF cohort Parquet is configured; set CDHAI_HAPF_CGM_PATH.",
        )

    try:
        cohort = pd.read_parquet(cohort_path, columns=list(_REQUIRED_COHORT_COLUMNS))
    except (ImportError, OSError, ValueError, KeyError) as exc:
        readiness["validation_error_type"] = type(exc).__name__
        return _skip(
            readiness,
            readiness_path,
            "The configured cohort could not be read with the HAPF data contract.",
        )

    missing = [column for column in _REQUIRED_COHORT_COLUMNS if column not in cohort.columns]
    if missing:
        readiness["missing_columns"] = missing
        return _skip(readiness, readiness_path, "The configured cohort is missing required HAPF columns.")

    subject_keys = {str(value) for value in cohort["subject_key"].dropna().unique()}
    readiness.update(
        {
            "cohort_ready": True,
            "cohort_rows": int(len(cohort)),
            "cohort_subject_count": len(subject_keys),
        }
    )
    target, target_resolution = _resolve_target(config, dataset, subject_keys)
    readiness["target_resolution"] = target_resolution
    if target is None:
        return _skip(
            readiness,
            readiness_path,
            "No stable held-out subject could be matched to the cohort; configure CDHAI_HAPF_HELDOUT_SUBJECT.",
        )

    model_config_path = resolve_project_path(Path(config.model_config_path))
    readiness["model_config_present"] = model_config_path.exists()
    if not model_config_path.exists():
        return _skip(readiness, readiness_path, "The configured HAPF model configuration does not exist.")

    fingerprint = _cache_fingerprint(cohort_path, model_config_path, target, external_config)
    experiment_dir = cache_dir / fingerprint
    cached_result_path = experiment_dir / "results.json"
    cached_report_path = experiment_dir / "report.md"
    reused = bool(config.reuse_across_cycles and cached_result_path.exists())
    readiness.update(
        {
            "cache_fingerprint": fingerprint,
            "cache_reused": reused,
            "execution_status": "cached" if reused else "running",
        }
    )
    write_json(readiness_path, readiness)

    try:
        if reused:
            result = json.loads(cached_result_path.read_text(encoding="utf-8"))
        else:
            if runner is None or config_loader is None:
                imported_loader, imported_runner = _load_hapf_api(external_config)
                config_loader = config_loader or imported_loader
                runner = runner or imported_runner
            experiment_config = config_loader(model_config_path)
            result = runner(
                data_path=cohort_path,
                output_dir=experiment_dir,
                config=experiment_config,
                heldout_subject=target,
                device_name=config.device or None,
            )
    except (ImportError, ModuleNotFoundError) as exc:
        readiness["execution_status"] = "dependency_unavailable"
        readiness["error_type"] = type(exc).__name__
        return _skip(
            readiness,
            readiness_path,
            "HAPF runtime dependencies are unavailable; install the optional `hapf` extra.",
        )
    except Exception as exc:  # HAPF owns runtime/model exceptions; CDHAI records a bounded failure.
        readiness["execution_status"] = "failed"
        readiness["error_type"] = type(exc).__name__
        readiness["error_detail"] = _redact_text(str(exc), target)
        write_json(readiness_path, readiness)
        return {
            "status": "failed",
            "summary": "HAPF execution failed; the task record contains a redacted diagnostic.",
            "artifacts": {"hapf_readiness": str(readiness_path)},
            "evidence": {"error_type": type(exc).__name__, "cache_reused": reused},
        }

    sanitized = _sanitize_result(result)
    write_json(cached_result_path, sanitized)
    interpretation = _interpret_result(
        sanitized,
        cycle=cycle,
        hypotheses=hypotheses,
        reused=reused,
        fingerprint=fingerprint,
    )
    readiness["execution_status"] = "completed"
    write_json(readiness_path, readiness)
    write_json(interpretation_path, interpretation)
    plot_path = output_paths["images"] / "hapf_rmse_by_horizon.png"
    _plot_rmse_by_horizon(sanitized, plot_path)
    artifacts = {
        "hapf_readiness": str(readiness_path),
        "hapf_cycle_interpretation": str(interpretation_path),
        "hapf_results": str(cached_result_path),
        "hapf_rmse_by_horizon": str(plot_path),
    }
    if cached_report_path.exists():
        artifacts["hapf_report"] = str(cached_report_path)
    return {
        "status": "completed",
        "summary": interpretation["summary"],
        "artifacts": artifacts,
        "evidence": interpretation["evidence"],
    }


def _resolve_cohort_path(config: HAPFConfig, dataset: PatientDataset) -> Path | None:
    if config.cohort_data_path:
        return resolve_project_path(Path(config.cohort_data_path))
    if dataset.source_path.suffix.lower() == ".parquet":
        return dataset.source_path.resolve()
    return None


def _resolve_target(
    config: HAPFConfig,
    dataset: PatientDataset,
    subject_keys: set[str],
) -> tuple[str | None, str]:
    if config.heldout_subject:
        if config.heldout_subject in subject_keys:
            return config.heldout_subject, "configured_subject_match"
        return None, "configured_subject_not_found"
    if str(dataset.patient_id) in subject_keys:
        return str(dataset.patient_id), "dataset_patient_match"
    if config.allow_auto_holdout and subject_keys:
        return sorted(subject_keys)[0], "deterministic_auto_holdout"
    return None, "no_subject_match"


def _cache_fingerprint(
    cohort_path: Path,
    model_config_path: Path,
    target: str,
    external_config: ExternalConfig,
) -> str:
    cohort_stat = cohort_path.stat()
    config_stat = model_config_path.stat()
    repository_path = resolve_project_path(external_config.hapf_path)
    payload = {
        "cohort": str(cohort_path.resolve()),
        "cohort_size": cohort_stat.st_size,
        "cohort_mtime_ns": cohort_stat.st_mtime_ns,
        "model_config": str(model_config_path.resolve()),
        "model_config_size": config_stat.st_size,
        "model_config_mtime_ns": config_stat.st_mtime_ns,
        "target_digest": sha256(target.encode("utf-8")).hexdigest(),
        "repository_url": external_config.hapf_url,
        "repository_head": _gitlink_head(repository_path),
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()[:20]


def _gitlink_head(repository_path: Path) -> str:
    git_file = repository_path / ".git"
    if not git_file.exists():
        return "unknown"
    try:
        if git_file.is_file():
            git_dir_line = git_file.read_text(encoding="utf-8").strip()
            git_dir = (repository_path / git_dir_line.split(":", 1)[1].strip()).resolve()
        else:
            git_dir = git_file
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            return (git_dir / head.split(" ", 1)[1]).read_text(encoding="utf-8").strip()
        return head
    except (IndexError, OSError):
        return "unknown"


def _load_hapf_api(external_config: ExternalConfig) -> tuple[Callable[..., Any], Callable[..., Any]]:
    repository_path = resolve_project_path(external_config.hapf_path)
    with _temporary_sys_path(repository_path / "src"):
        config_module = import_module("hapf.config")
        experiment_module = import_module("hapf.training.experiment")
    return config_module.load_config, experiment_module.run_sample_experiment


@contextmanager
def _temporary_sys_path(path: Path) -> Iterator[None]:
    value = str(path)
    inserted = path.exists() and value not in sys.path
    if inserted:
        sys.path.insert(0, value)
    try:
        yield
    finally:
        if inserted and value in sys.path:
            sys.path.remove(value)


def _interpret_result(
    result: dict[str, Any],
    *,
    cycle: int,
    hypotheses: list[Hypothesis],
    reused: bool,
    fingerprint: str,
) -> dict[str, Any]:
    metrics = result.get("metrics", {})
    gate = result.get("personalization_gate", {})
    population_rmse = metrics.get("population", {}).get("rmse", [])
    personalized_rmse = metrics.get("personalized", {}).get("rmse", [])
    deployed_rmse = metrics.get("deployed", {}).get("rmse", [])
    gate_status = str(gate.get("status", "not_reported"))
    accepted = bool(gate.get("accepted", False))
    summary = (
        f"HAPF personalization gate was {gate_status}; deployed model="
        f"{gate.get('deployed_model', 'not_reported')} with {len(deployed_rmse)} forecast horizon(s)."
    )
    evidence = {
        "hapf_status": result.get("status"),
        "gate_status": gate_status,
        "gate_accepted": accepted,
        "deployed_model": gate.get("deployed_model"),
        "relative_improvement": gate.get("relative_improvement"),
        "population_rmse": population_rmse,
        "personalized_rmse": personalized_rmse,
        "deployed_rmse": deployed_rmse,
        "interval_coverage": metrics.get("deployed_interval", {}).get("coverage", []),
        "interval_mean_width": metrics.get("deployed_interval", {}).get("mean_width", []),
        "horizon_minutes": result.get("model", {}).get("horizon_minutes", []),
        "cache_reused": reused,
        "cache_fingerprint": fingerprint,
    }
    return {
        "cycle": cycle,
        "hypothesis_ids": [hypothesis.hypothesis_id for hypothesis in hypotheses],
        "summary": summary,
        "evidence": evidence,
        "limitations": result.get("limitations", []),
    }


def _sanitize_result(value: Any) -> Any:
    blocked_keys = {"patient_id", "subject_key", "heldout_subject"}
    if isinstance(value, dict):
        return {
            str(key): _sanitize_result(item)
            for key, item in value.items()
            if str(key).lower() not in blocked_keys
        }
    if isinstance(value, list):
        return [_sanitize_result(item) for item in value]
    return value


def _plot_rmse_by_horizon(result: dict[str, Any], path: Path) -> None:
    metrics = result.get("metrics", {})
    horizons = result.get("model", {}).get("horizon_minutes", [])
    series = {
        "Population": metrics.get("population", {}).get("rmse", []),
        "Personalized": metrics.get("personalized", {}).get("rmse", []),
        "Deployed": metrics.get("deployed", {}).get("rmse", []),
    }
    count = max((len(values) for values in series.values()), default=0)
    if not count:
        return
    labels = [str(value) for value in horizons[:count]]
    if len(labels) < count:
        labels.extend(str(index + 1) for index in range(len(labels), count))
    positions = list(range(count))
    width = 0.24
    fig, axis = plt.subplots(figsize=(7.2, 4.2))
    for offset, (name, values) in enumerate(series.items(), start=-1):
        axis.bar(
            [position + offset * width for position in positions],
            [float(value) for value in values[:count]],
            width=width,
            label=name,
        )
    axis.set_xticks(positions, labels)
    axis.set_xlabel("Forecast horizon (minutes)")
    axis.set_ylabel("RMSE (mg/dL)")
    axis.set_title("HAPF population and personalized forecast error")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _redact_text(value: str, target: str) -> str:
    return value.replace(target, "[REDACTED_SUBJECT]")[:1000]


def _skip(readiness: dict[str, Any], readiness_path: Path, reason: str) -> dict[str, Any]:
    readiness["execution_status"] = "skipped"
    readiness["reason"] = reason
    write_json(readiness_path, readiness)
    return {
        "status": "skipped",
        "summary": reason,
        "artifacts": {"hapf_readiness": str(readiness_path)},
        "evidence": {
            "cohort_ready": readiness.get("cohort_ready", False),
            "target_resolution": readiness.get("target_resolution"),
            "execution_status": readiness.get("execution_status"),
        },
    }
