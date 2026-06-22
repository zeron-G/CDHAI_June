import json
from pathlib import Path
from typing import Any

import pandas as pd

from cdhai_june.config import AnalysisConfig, ExternalConfig, HAPFConfig, load_config
from cdhai_june.external.hapf import run_hapf_cycle
from cdhai_june.models import Hypothesis, PatientDataset
from cdhai_june.models import TestResult as AnalysisTestResult
from cdhai_june.task_cycle import TaskCycleRunner


def test_hapf_skips_with_auditable_readiness_when_cohort_is_absent(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path, "patient-a")
    paths = _output_paths(tmp_path / "task")

    result = run_hapf_cycle(
        dataset=dataset,
        config=HAPFConfig(cohort_data_path=str(tmp_path / "missing.parquet")),
        external_config=ExternalConfig(),
        cycle=1,
        output_paths=paths,
        cache_dir=tmp_path / "cache",
        hypotheses=[],
    )

    assert result["status"] == "skipped"
    readiness = Path(result["artifacts"]["hapf_readiness"])
    assert readiness.exists()
    assert json.loads(readiness.read_text(encoding="utf-8"))["execution_status"] == "skipped"


def test_hapf_runs_once_reuses_cache_and_redacts_subject(tmp_path: Path) -> None:
    subject = "private-subject-001"
    cohort_path = tmp_path / "cohort.parquet"
    pd.DataFrame(
        {
            "subject_key": [subject, subject, "population-subject"],
            "DT_s": pd.to_datetime(
                ["2026-01-01 00:00", "2026-01-01 00:05", "2026-01-01 00:00"]
            ),
            "BGValue": [110.0, 112.0, 120.0],
        }
    ).to_parquet(cohort_path, index=False)
    model_config_path = tmp_path / "hapf.yaml"
    model_config_path.write_text("seed: 41\n", encoding="utf-8")
    dataset = _dataset(tmp_path, subject)
    config = HAPFConfig(
        cohort_data_path=str(cohort_path),
        model_config_path=str(model_config_path),
        heldout_subject=subject,
    )
    calls = {"count": 0}

    def fake_runner(**kwargs: Any) -> dict[str, Any]:
        calls["count"] += 1
        assert kwargs["heldout_subject"] == subject
        return _fake_hapf_result(subject)

    hypothesis = Hypothesis(
        hypothesis_id="H5",
        statement="Personalization improves forecasting.",
        rationale="Patient distributions differ.",
        variables=["BGValue"],
        test_family="personalized_forecasting",
        cycle=1,
    )
    first = run_hapf_cycle(
        dataset=dataset,
        config=config,
        external_config=ExternalConfig(),
        cycle=1,
        output_paths=_output_paths(tmp_path / "cycle_01"),
        cache_dir=tmp_path / "cache",
        hypotheses=[hypothesis],
        runner=fake_runner,
        config_loader=lambda _: object(),
    )
    second = run_hapf_cycle(
        dataset=dataset,
        config=config,
        external_config=ExternalConfig(),
        cycle=2,
        output_paths=_output_paths(tmp_path / "cycle_02"),
        cache_dir=tmp_path / "cache",
        hypotheses=[hypothesis],
        runner=fake_runner,
        config_loader=lambda _: object(),
    )

    assert calls["count"] == 1
    assert first["status"] == second["status"] == "completed"
    assert first["evidence"]["cache_reused"] is False
    assert second["evidence"]["cache_reused"] is True
    assert Path(first["artifacts"]["hapf_rmse_by_horizon"]).exists()
    serialized = json.dumps({"first": first, "second": second})
    serialized += Path(first["artifacts"]["hapf_cycle_interpretation"]).read_text(encoding="utf-8")
    serialized += Path(first["artifacts"]["hapf_results"]).read_text(encoding="utf-8")
    assert subject not in serialized


def test_hapf_required_gate_does_not_treat_skip_as_completion() -> None:
    config = AnalysisConfig(hapf=HAPFConfig(enabled=True, require_for_gate=True))
    hypothesis = Hypothesis(
        hypothesis_id="H5",
        statement="Personalization improves forecasting.",
        rationale="Patient distributions differ.",
        variables=["BGValue"],
        test_family="personalized_forecasting",
        cycle=1,
    )
    tasks = [
        {"type": task_type, "status": "completed"}
        for task_type in (
            "literature_search",
            "feature_engineering",
            "statistical_analysis",
            "neural_network_train_predict",
            "visualization",
            "result_analysis",
        )
    ]
    tasks.append({"type": "personalized_forecasting", "status": "skipped"})
    decision = TaskCycleRunner(config)._judge_gate(
        hypotheses=[hypothesis],
        statistical_results=[
            AnalysisTestResult(
                hypothesis_id="H5",
                method="personalized_forecasting",
                status="descriptive",
                summary="Exploratory gate result.",
            )
        ],
        completed_tasks=tasks,
        evidence_ledger=[],
        round_index=1,
    )

    assert decision["status"] == "needs_more_tasks"
    assert "personalized_forecasting" in decision["missing_required_tasks"]


def test_default_config_exposes_hapf_external_contract() -> None:
    config = load_config(Path(__file__).parents[1] / "configs" / "default.yaml")

    assert config.analysis.hapf.enabled is True
    assert config.analysis.hapf.reuse_across_cycles is True
    assert config.external.hapf_url == "https://github.com/zeron-G/CDHAI-HAPF.git"


def _dataset(tmp_path: Path, patient_id: str) -> PatientDataset:
    source = tmp_path / "patient.csv"
    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01"]), "glucose": [110.0]})
    return PatientDataset(
        patient_id=patient_id,
        tables={"patient": frame},
        source_path=source,
        primary_table="patient",
        column_roles={"timestamp": "timestamp", "glucose": "glucose"},
    )


def _output_paths(root: Path) -> dict[str, Path]:
    paths = {name: root / name for name in ("config", "scripts", "runs", "results", "images", "notebooks")}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _fake_hapf_result(subject: str) -> dict[str, Any]:
    return {
        "status": "exploratory_single_holdout",
        "heldout_alias": "heldout_subject_001",
        "heldout_subject": subject,
        "data": {"subjects_total": 2, "population_subjects": 1},
        "model": {"horizon_minutes": [30, 60]},
        "metrics": {
            "population": {"rmse": [20.0, 30.0]},
            "personalized": {"rmse": [18.0, 28.0]},
            "deployed": {"rmse": [18.0, 28.0]},
            "deployed_interval": {"coverage": [0.9, 0.91], "mean_width": [50.0, 70.0]},
        },
        "personalization_gate": {
            "status": "accepted",
            "accepted": True,
            "deployed_model": "personalized",
            "relative_improvement": 0.08,
        },
        "limitations": ["Exploratory only."],
    }
