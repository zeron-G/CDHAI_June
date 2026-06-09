from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cdhai_june.config import AnalysisConfig
from cdhai_june.models import Hypothesis, PatientDataset, TestResult
from cdhai_june.utils import write_json


@dataclass(slots=True)
class TaskCycleRunner:
    config: AnalysisConfig

    def run(
        self,
        *,
        cycle: int,
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
        cycle_dir: Path,
    ) -> dict[str, Any]:
        task_root = cycle_dir / "task_chain"
        task_root.mkdir(parents=True, exist_ok=True)
        if not self.config.task_cycle.enabled:
            payload = _disabled_payload(cycle, task_root)
            _write_task_chain(task_root, payload)
            return payload

        completed: list[dict[str, Any]] = []
        evidence_ledger: list[dict[str, Any]] = []
        gate_decision: dict[str, Any] = {
            "status": "not_started",
            "reason": "Task cycle has not evaluated evidence yet.",
        }

        for round_index in range(1, self.config.task_cycle.max_rounds + 1):
            planned_tasks = self._plan_round(round_index, hypotheses, statistical_results, completed, gate_decision)
            if not planned_tasks:
                break
            for planned in planned_tasks:
                record = self._execute_task(
                    task_root=task_root,
                    task_index=len(completed) + 1,
                    round_index=round_index,
                    planned=planned,
                    dataset=dataset,
                    hypotheses=hypotheses,
                    statistical_results=statistical_results,
                    basic_profile=basic_profile,
                    research_context=research_context,
                )
                completed.append(record)
                evidence_ledger.append(_evidence_from_task(record))

            gate_decision = self._judge_gate(
                hypotheses=hypotheses,
                statistical_results=statistical_results,
                completed_tasks=completed,
                evidence_ledger=evidence_ledger,
                round_index=round_index,
            )
            if gate_decision["status"] == "ready_for_insight":
                break

        payload = {
            "cycle": cycle,
            "task_root": str(task_root),
            "rounds_executed": max([task["round"] for task in completed], default=0),
            "task_count": len(completed),
            "tasks": completed,
            "evidence_ledger": evidence_ledger,
            "gate_decision": gate_decision,
            "insight_stage_allowed": gate_decision["status"] == "ready_for_insight",
        }
        _write_task_chain(task_root, payload)
        return payload

    def _plan_round(
        self,
        round_index: int,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        completed: list[dict[str, Any]],
        gate_decision: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if round_index == 1:
            return [
                _task_plan("literature_search", "Map hypotheses to the verified reference manifest.", []),
                _task_plan("feature_engineering", "Build analysis-ready feature matrix and feature summary.", ["literature_search"]),
                _task_plan("statistical_analysis", "Package statistical tests, effect sizes, and p-values.", ["feature_engineering"]),
                _task_plan(
                    "neural_network_train_predict",
                    "Develop, train, predict, and evaluate a small neural network baseline.",
                    ["feature_engineering"],
                ),
                _task_plan("visualization", "Create task-level figures for statistical and ML evidence.", ["statistical_analysis"]),
                _task_plan("result_analysis", "Synthesize task evidence into support/not-significant/gap decisions.", ["visualization"]),
            ]

        if gate_decision.get("status") == "ready_for_insight":
            return []
        completed_types = {task["type"] for task in completed}
        planned: list[dict[str, Any]] = []
        if "sensitivity_analysis" not in completed_types:
            planned.append(
                _task_plan(
                    "sensitivity_analysis",
                    "Stress-test evidence against missingness, sample size, and multiple testing.",
                    ["statistical_analysis"],
                )
            )
        if _has_skipped_result(statistical_results) and "evidence_gap_analysis" not in completed_types:
            planned.append(
                _task_plan(
                    "evidence_gap_analysis",
                    "Document why skipped or underpowered analyses cannot prove or disprove the hypothesis.",
                    ["sensitivity_analysis"],
                )
            )
        return planned

    def _execute_task(
        self,
        *,
        task_root: Path,
        task_index: int,
        round_index: int,
        planned: dict[str, Any],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        task_id = f"task_{task_index:03d}_{planned['type']}"
        task_dir = task_root / task_id
        paths = _ensure_task_dirs(task_dir)
        config_payload = {
            "task_id": task_id,
            "type": planned["type"],
            "round": round_index,
            "objective": planned["objective"],
            "dependencies": planned["dependencies"],
            "patient_id": dataset.patient_id,
            "hypotheses": [hypothesis.to_json() for hypothesis in hypotheses],
        }
        write_json(paths["config"] / "task_config.json", config_payload)
        _write_task_script(paths["scripts"] / "run_task.py", planned["type"])
        _write_notebook_stub(paths["notebooks"] / "task_notes.ipynb", config_payload)

        executor = {
            "literature_search": self._run_literature_search,
            "feature_engineering": self._run_feature_engineering,
            "statistical_analysis": self._run_statistical_analysis,
            "neural_network_train_predict": self._run_neural_network,
            "visualization": self._run_visualization,
            "result_analysis": self._run_result_analysis,
            "sensitivity_analysis": self._run_sensitivity_analysis,
            "evidence_gap_analysis": self._run_evidence_gap_analysis,
        }.get(planned["type"])
        if executor is None:
            result = {"status": "skipped", "reason": f"Unknown task type {planned['type']}."}
        else:
            result = executor(
                paths=paths,
                dataset=dataset,
                hypotheses=hypotheses,
                statistical_results=statistical_results,
                basic_profile=basic_profile,
                research_context=research_context,
            )

        record = {
            "task_id": task_id,
            "type": planned["type"],
            "round": round_index,
            "status": result.get("status", "completed"),
            "objective": planned["objective"],
            "dependencies": planned["dependencies"],
            "path": str(task_dir),
            "artifacts": result.get("artifacts", {}),
            "summary": result.get("summary", ""),
            "evidence": result.get("evidence", {}),
        }
        write_json(paths["results"] / "task_record.json", record)
        return record

    def _run_literature_search(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del dataset, statistical_results, basic_profile
        references = research_context.get("reference_manifest", {}).get("references", [])
        hooks = _reference_hooks_by_family()
        rows = []
        for hypothesis in hypotheses:
            ref_ids = hooks.get(hypothesis.test_family, [])
            rows.append(
                {
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "test_family": hypothesis.test_family,
                    "reference_ids": ref_ids,
                    "references": [ref for ref in references if ref.get("id") in ref_ids],
                }
            )
        result_path = paths["results"] / "literature_findings.json"
        matrix_path = paths["results"] / "literature_matrix.md"
        write_json(result_path, {"hypothesis_reference_map": rows})
        matrix_path.write_text(_literature_matrix_markdown(rows), encoding="utf-8")
        return {
            "status": "completed",
            "summary": f"Mapped {len(hypotheses)} hypotheses to verified reference hooks.",
            "artifacts": {"literature_findings": str(result_path), "literature_matrix": str(matrix_path)},
            "evidence": {"reference_hook_count": sum(len(row["reference_ids"]) for row in rows)},
        }

    def _run_feature_engineering(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del hypotheses, statistical_results, basic_profile, research_context
        frame = _feature_frame(dataset)
        matrix_path = paths["results"] / "feature_matrix.csv"
        summary_path = paths["results"] / "feature_summary.json"
        frame.to_csv(matrix_path, index=False)
        numeric = frame.select_dtypes(include="number")
        summary = {
            "rows": int(len(frame)),
            "columns": list(frame.columns),
            "numeric_columns": list(numeric.columns),
            "missing_by_column": {column: int(frame[column].isna().sum()) for column in frame.columns},
        }
        write_json(summary_path, summary)
        return {
            "status": "completed",
            "summary": f"Built feature matrix with {len(frame)} rows and {len(frame.columns)} columns.",
            "artifacts": {"feature_matrix": str(matrix_path), "feature_summary": str(summary_path)},
            "evidence": {"rows": int(len(frame)), "numeric_columns": len(numeric.columns)},
        }

    def _run_statistical_analysis(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del dataset, hypotheses, basic_profile, research_context
        rows = [_stat_evidence_row(result, self.config.hypothesis.alpha) for result in statistical_results]
        result_path = paths["results"] / "statistical_evidence.json"
        write_json(result_path, {"alpha": self.config.hypothesis.alpha, "rows": rows})
        return {
            "status": "completed",
            "summary": f"Packaged {len(rows)} statistical evidence rows.",
            "artifacts": {"statistical_evidence": str(result_path)},
            "evidence": {"decidable_results": sum(1 for row in rows if row["decision"] != "evidence_gap")},
        }

    def _run_neural_network(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del hypotheses, statistical_results, basic_profile, research_context
        payload = _train_small_neural_network(
            dataset=dataset,
            hidden_units=self.config.task_cycle.neural_network_hidden_units,
            epochs=self.config.task_cycle.neural_network_epochs,
        )
        metrics_path = paths["runs"] / "nn_metrics.json"
        state_path = paths["runs"] / "nn_model_state.json"
        predictions_path = paths["results"] / "nn_predictions.csv"
        plot_path = paths["images"] / "nn_observed_vs_predicted.png"
        loss_path = paths["images"] / "nn_training_loss.png"

        write_json(metrics_path, payload["metrics"])
        write_json(state_path, payload.get("state", {}))
        if payload["predictions"] is not None:
            payload["predictions"].to_csv(predictions_path, index=False)
            _plot_prediction_frame(payload["predictions"], plot_path)
            _plot_loss(payload["loss_curve"], loss_path)
        else:
            write_json(predictions_path.with_suffix(".json"), {"reason": payload["metrics"].get("reason")})

        artifacts = {
            "nn_metrics": str(metrics_path),
            "nn_model_state": str(state_path),
            "nn_predictions": str(predictions_path if payload["predictions"] is not None else predictions_path.with_suffix(".json")),
            "observed_vs_predicted": str(plot_path) if payload["predictions"] is not None else None,
            "training_loss": str(loss_path) if payload["predictions"] is not None else None,
        }
        status = "completed" if payload["metrics"].get("available") else "skipped"
        return {
            "status": status,
            "summary": payload["metrics"].get("summary", "Neural network baseline completed."),
            "artifacts": artifacts,
            "evidence": {
                "available": payload["metrics"].get("available", False),
                "mae_mgdl": payload["metrics"].get("mae_mgdl"),
                "persistence_mae_mgdl": payload["metrics"].get("persistence_mae_mgdl"),
            },
        }

    def _run_visualization(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del dataset, hypotheses, basic_profile, research_context
        figure_path = paths["images"] / "statistical_evidence_overview.png"
        _plot_statistical_evidence(statistical_results, figure_path)
        index_path = paths["results"] / "visualization_index.json"
        write_json(index_path, {"figures": [{"path": str(figure_path), "role": "statistical_evidence_overview"}]})
        return {
            "status": "completed",
            "summary": "Created task-level visualization index and statistical overview figure.",
            "artifacts": {"visualization_index": str(index_path), "statistical_evidence_overview": str(figure_path)},
            "evidence": {"figure_count": 1},
        }

    def _run_result_analysis(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del dataset, basic_profile, research_context
        rows = []
        result_by_id = {result.hypothesis_id: result for result in statistical_results}
        for hypothesis in hypotheses:
            result = result_by_id.get(hypothesis.hypothesis_id)
            rows.append(_hypothesis_decision(hypothesis, result, self.config.hypothesis.alpha))
        result_path = paths["results"] / "result_analysis.json"
        write_json(result_path, {"hypothesis_decisions": rows})
        return {
            "status": "completed",
            "summary": f"Interpreted {len(rows)} hypothesis decisions for evidence gate.",
            "artifacts": {"result_analysis": str(result_path)},
            "evidence": {"decision_count": len(rows), "evidence_gaps": sum(1 for row in rows if row["decision"] == "evidence_gap")},
        }

    def _run_sensitivity_analysis(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del dataset, hypotheses, research_context
        missing = basic_profile.get("tables", {}).get(basic_profile.get("primary_table", ""), {}).get("missing", {})
        rows = [_stat_evidence_row(result, self.config.hypothesis.alpha) for result in statistical_results]
        payload = {
            "missingness": missing,
            "small_sample_warnings": [row for row in rows if row.get("n") is not None and row["n"] < 10],
            "multiple_testing_note": "Primary cycle audit applies Holm correction before insight-stage claims.",
        }
        result_path = paths["results"] / "sensitivity_analysis.json"
        write_json(result_path, payload)
        return {
            "status": "completed",
            "summary": "Documented missingness, small-sample warnings, and multiple-testing sensitivity.",
            "artifacts": {"sensitivity_analysis": str(result_path)},
            "evidence": {"small_sample_warning_count": len(payload["small_sample_warnings"])},
        }

    def _run_evidence_gap_analysis(
        self,
        *,
        paths: dict[str, Path],
        dataset: PatientDataset,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
    ) -> dict[str, Any]:
        del dataset, hypotheses, basic_profile, research_context
        gaps = [
            {"hypothesis_id": result.hypothesis_id, "method": result.method, "reason": result.summary}
            for result in statistical_results
            if result.status == "skipped"
        ]
        result_path = paths["results"] / "evidence_gap_analysis.json"
        write_json(result_path, {"gaps": gaps})
        return {
            "status": "completed",
            "summary": f"Documented {len(gaps)} evidence gaps.",
            "artifacts": {"evidence_gap_analysis": str(result_path)},
            "evidence": {"gap_count": len(gaps)},
        }

    def _judge_gate(
        self,
        *,
        hypotheses: list[Hypothesis],
        statistical_results: list[TestResult],
        completed_tasks: list[dict[str, Any]],
        evidence_ledger: list[dict[str, Any]],
        round_index: int,
    ) -> dict[str, Any]:
        completed_types = {task["type"] for task in completed_tasks if task["status"] in {"completed", "skipped"}}
        required = {
            "literature_search",
            "feature_engineering",
            "statistical_analysis",
            "visualization",
            "result_analysis",
        }
        if self.config.task_cycle.require_neural_network:
            required.add("neural_network_train_predict")
        missing_required = sorted(required - completed_types)
        result_by_id = {result.hypothesis_id: result for result in statistical_results}
        decisions = [_hypothesis_decision(hypothesis, result_by_id.get(hypothesis.hypothesis_id), self.config.hypothesis.alpha) for hypothesis in hypotheses]
        unresolved = [row for row in decisions if row["decision"] == "evidence_gap"]
        completed_count = len([task for task in completed_tasks if task["status"] in {"completed", "skipped"}])
        enough_tasks = completed_count >= self.config.task_cycle.min_completed_tasks
        ready = not missing_required and enough_tasks and not unresolved
        if ready:
            status = "ready_for_insight"
            reason = "Required exploration tasks completed and every hypothesis has a support/not-significant/descriptive decision."
        elif round_index >= self.config.task_cycle.max_rounds:
            status = "max_rounds_reached"
            reason = "Task cycle reached max rounds before all evidence gaps were closed."
        else:
            status = "needs_more_tasks"
            reason = "Evidence gate requires additional exploration tasks before insight."
        return {
            "status": status,
            "reason": reason,
            "round": round_index,
            "completed_task_count": completed_count,
            "missing_required_tasks": missing_required,
            "hypothesis_decisions": decisions,
            "unresolved_hypotheses": unresolved,
            "evidence_ledger_count": len(evidence_ledger),
        }


def _disabled_payload(cycle: int, task_root: Path) -> dict[str, Any]:
    return {
        "cycle": cycle,
        "task_root": str(task_root),
        "rounds_executed": 0,
        "task_count": 0,
        "tasks": [],
        "evidence_ledger": [],
        "gate_decision": {"status": "disabled", "reason": "Task cycle disabled by config."},
        "insight_stage_allowed": True,
    }


def _task_plan(task_type: str, objective: str, dependencies: list[str]) -> dict[str, Any]:
    return {"type": task_type, "objective": objective, "dependencies": dependencies}


def _ensure_task_dirs(task_dir: Path) -> dict[str, Path]:
    paths = {
        "config": task_dir / "config",
        "scripts": task_dir / "scripts",
        "runs": task_dir / "runs",
        "results": task_dir / "results",
        "images": task_dir / "images",
        "notebooks": task_dir / "notebooks",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _write_task_chain(task_root: Path, payload: dict[str, Any]) -> None:
    write_json(task_root / "task_graph.json", {"tasks": payload["tasks"]})
    write_json(task_root / "evidence_ledger.json", payload["evidence_ledger"])
    write_json(task_root / "gate_decision.json", payload["gate_decision"])
    write_json(task_root / "task_chain_summary.json", payload)


def _write_task_script(path: Path, task_type: str) -> None:
    script = f'''"""Generated task runner stub for {task_type}.

The package executes task-cycle logic through cdhai_june.task_cycle. This file
records the reproducible command shape for rerunning or porting this task into
a notebook/script workflow.
"""

from cdhai_june.task_cycle import TaskCycleRunner  # noqa: F401

TASK_TYPE = "{task_type}"
'''
    path.write_text(script, encoding="utf-8")


def _write_notebook_stub(path: Path, config_payload: dict[str, Any]) -> None:
    payload = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Task Notes\\n",
                    f"Task `{config_payload['task_id']}` records reproducible artifacts for `{config_payload['type']}`.\\n",
                ],
            }
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    write_json(path, payload)


def _evidence_from_task(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": record["task_id"],
        "type": record["type"],
        "status": record["status"],
        "summary": record["summary"],
        "evidence": record.get("evidence", {}),
        "artifacts": record.get("artifacts", {}),
    }


def _reference_hooks_by_family() -> dict[str, list[str]]:
    return {
        "circadian_pattern": ["battelino_2019_tir", "rodbard_2009_cgm_interpretation"],
        "meal_response": ["battelino_2019_tir", "ada_2026_glycemic_goals"],
        "exercise_response": ["battelino_2019_tir", "ada_2026_glycemic_goals"],
        "daily_trend": ["rodbard_2009_cgm_interpretation"],
        "numeric_correlation": ["rodbard_2009_cgm_interpretation"],
        "missingness_pattern": ["danne_2017_cgm_consensus"],
        "ml_prediction": ["rodbard_2009_cgm_interpretation"],
    }


def _literature_matrix_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Literature Findings", "", "| Hypothesis | Test family | Reference hooks |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| `{row['hypothesis_id']}` | `{row['test_family']}` | {', '.join(row['reference_ids'])} |")
    lines.append("")
    lines.append("All reference ids must exist in `analysis/reference_manifest.json` before publication use.")
    return "\n".join(lines)


def _feature_frame(dataset: PatientDataset) -> pd.DataFrame:
    df = dataset.primary.copy()
    roles = dataset.column_roles
    time_col = roles.get("timestamp")
    if time_col and time_col in df and pd.api.types.is_datetime64_any_dtype(df[time_col]):
        df = df.sort_values(time_col).copy()
        hour = df[time_col].dt.hour + df[time_col].dt.minute / 60.0
        df["feature_hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        df["feature_hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    for role in ("glucose", "carbs", "steps", "exercise", "medication"):
        column = roles.get(role)
        if column and column in df:
            df[f"feature_{role}"] = pd.to_numeric(df[column], errors="coerce")
    return df


def _stat_evidence_row(result: TestResult, alpha: float) -> dict[str, Any]:
    p_value = _extract_p_value(result.metrics)
    effect = _extract_effect_size(result)
    if result.status == "supported":
        decision = "supported"
    elif result.status == "not_supported":
        decision = "not_significant"
    elif result.status == "descriptive":
        decision = "descriptive_evidence"
    else:
        decision = "evidence_gap"
    return {
        "hypothesis_id": result.hypothesis_id,
        "method": result.method,
        "status": result.status,
        "decision": decision,
        "summary": result.summary,
        "n": _extract_n(result.metrics),
        "p_value": p_value,
        "alpha": alpha,
        "effect_size": effect,
    }


def _hypothesis_decision(hypothesis: Hypothesis, result: TestResult | None, alpha: float) -> dict[str, Any]:
    if result is None:
        return {
            "hypothesis_id": hypothesis.hypothesis_id,
            "decision": "evidence_gap",
            "reason": "No statistical result was produced for this hypothesis.",
        }
    row = _stat_evidence_row(result, alpha)
    reason = {
        "supported": "Evidence supports the exploratory hypothesis under the configured alpha.",
        "not_significant": "Evidence is sufficient to report a non-significant result in this dataset.",
        "descriptive_evidence": "Evidence is descriptive and sufficient for a data-quality or context insight.",
        "evidence_gap": "The task chain must document this as an evidence gap.",
    }[row["decision"]]
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "statement": hypothesis.statement,
        "test_family": hypothesis.test_family,
        "decision": row["decision"],
        "reason": reason,
        "statistical_row": row,
    }


def _train_small_neural_network(
    *,
    dataset: PatientDataset,
    hidden_units: int,
    epochs: int,
) -> dict[str, Any]:
    roles = dataset.column_roles
    glucose_col = roles.get("glucose")
    if not glucose_col or glucose_col not in dataset.primary:
        return _nn_unavailable("No glucose column detected.")
    frame = _next_glucose_frame(dataset)
    if len(frame) < 16:
        return _nn_unavailable("Need at least 16 next-glucose pairs for neural network task.")
    feature_cols = [col for col in frame.columns if col.startswith("feature_")]
    split = max(10, int(len(frame) * 0.8))
    split = min(split, len(frame) - 4)
    train = frame.iloc[:split].copy()
    test = frame.iloc[split:].copy()
    if len(train) < 10 or len(test) < 4:
        return _nn_unavailable("Time split produced too little train/test data for neural network task.")

    x_train = train[feature_cols].to_numpy(float)
    x_test = test[feature_cols].to_numpy(float)
    y_train = train["target_next_glucose_mgdl"].to_numpy(float)
    y_test = test["target_next_glucose_mgdl"].to_numpy(float)
    center = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale == 0] = 1.0
    x_train = (x_train - center) / scale
    x_test = (x_test - center) / scale
    y_center = y_train.mean()
    y_scale = y_train.std() or 1.0
    y_train_scaled = (y_train - y_center) / y_scale

    rng = np.random.default_rng(42)
    w1 = rng.normal(0, 0.12, size=(x_train.shape[1], hidden_units))
    b1 = np.zeros(hidden_units)
    w2 = rng.normal(0, 0.12, size=(hidden_units, 1))
    b2 = np.zeros(1)
    loss_curve: list[float] = []
    learning_rate = 0.03
    for _ in range(epochs):
        hidden = np.tanh(x_train @ w1 + b1)
        pred = (hidden @ w2 + b2).ravel()
        error = pred - y_train_scaled
        loss_curve.append(float(np.mean(error**2)))
        grad_pred = 2 * error[:, None] / len(x_train)
        grad_w2 = hidden.T @ grad_pred
        grad_b2 = grad_pred.sum(axis=0)
        grad_hidden = grad_pred @ w2.T * (1 - hidden**2)
        grad_w1 = x_train.T @ grad_hidden
        grad_b1 = grad_hidden.sum(axis=0)
        w1 -= learning_rate * grad_w1
        b1 -= learning_rate * grad_b1
        w2 -= learning_rate * grad_w2
        b2 -= learning_rate * grad_b2

    pred_scaled = (np.tanh(x_test @ w1 + b1) @ w2 + b2).ravel()
    pred = pred_scaled * y_scale + y_center
    persistence = test["current_glucose_mgdl"].to_numpy(float)
    predictions = test[["current_glucose_mgdl", "target_next_glucose_mgdl"]].copy()
    predictions["nn_predicted_next_glucose_mgdl"] = pred
    predictions["persistence_predicted_next_glucose_mgdl"] = persistence
    metrics = {
        "available": True,
        "summary": (
            f"Neural network baseline completed with test MAE={_mae(y_test, pred):.3f} mg/dL "
            f"versus persistence MAE={_mae(y_test, persistence):.3f} mg/dL."
        ),
        "method": "one_hidden_layer_tanh_mlp",
        "feature_columns": feature_cols,
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "hidden_units": hidden_units,
        "epochs": epochs,
        "mae_mgdl": _mae(y_test, pred),
        "rmse_mgdl": _rmse(y_test, pred),
        "r2": _r2(y_test, pred),
        "persistence_mae_mgdl": _mae(y_test, persistence),
        "persistence_rmse_mgdl": _rmse(y_test, persistence),
        "guardrail": "Exploratory task-cycle neural network only; not a validated clinical model.",
    }
    state = {
        "x_center": center.tolist(),
        "x_scale": scale.tolist(),
        "y_center": float(y_center),
        "y_scale": float(y_scale),
        "w1": w1.tolist(),
        "b1": b1.tolist(),
        "w2": w2.ravel().tolist(),
        "b2": b2.tolist(),
    }
    return {"metrics": metrics, "state": state, "predictions": predictions, "loss_curve": loss_curve}


def _next_glucose_frame(dataset: PatientDataset) -> pd.DataFrame:
    roles = dataset.column_roles
    glucose_col = roles.get("glucose")
    if not glucose_col:
        return pd.DataFrame()
    df = dataset.primary.copy()
    time_col = roles.get("timestamp")
    if time_col and time_col in df and pd.api.types.is_datetime64_any_dtype(df[time_col]):
        df = df.dropna(subset=[time_col]).sort_values(time_col).copy()
        hour = df[time_col].dt.hour + df[time_col].dt.minute / 60.0
        df["feature_hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        df["feature_hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    df["current_glucose_mgdl"] = pd.to_numeric(df[glucose_col], errors="coerce")
    df["target_next_glucose_mgdl"] = df["current_glucose_mgdl"].shift(-1)
    df["feature_current_glucose"] = df["current_glucose_mgdl"]
    for role in ("carbs", "steps", "exercise", "medication"):
        column = roles.get(role)
        if column and column in df:
            df[f"feature_{role}"] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return df.dropna(subset=["current_glucose_mgdl", "target_next_glucose_mgdl"]).fillna(0.0)


def _nn_unavailable(reason: str) -> dict[str, Any]:
    return {
        "metrics": {"available": False, "reason": reason, "summary": f"Neural network task skipped: {reason}"},
        "state": {},
        "predictions": None,
        "loss_curve": [],
    }


def _plot_prediction_frame(frame: pd.DataFrame, path: Path) -> None:
    observed = frame["target_next_glucose_mgdl"].to_numpy(float)
    predicted = frame["nn_predicted_next_glucose_mgdl"].to_numpy(float)
    lower = float(np.nanmin([observed.min(), predicted.min()]))
    upper = float(np.nanmax([observed.max(), predicted.max()]))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(observed, predicted, color="#2f6f9f", s=38)
    ax.plot([lower, upper], [lower, upper], color="#333333", linestyle="--", linewidth=1.0)
    ax.set_title("Task-Cycle Neural Network Prediction")
    ax.set_xlabel("Observed next glucose (mg/dL)")
    ax.set_ylabel("Predicted next glucose (mg/dL)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_loss(loss_curve: list[float], path: Path) -> None:
    if not loss_curve:
        return
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(range(1, len(loss_curve) + 1), loss_curve, color="#6b4c9a", linewidth=1.5)
    ax.set_title("Neural Network Training Loss")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("MSE")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_statistical_evidence(results: list[TestResult], path: Path) -> None:
    labels = [result.hypothesis_id for result in results]
    values = []
    for result in results:
        effect = _extract_effect_size(result)
        values.append(abs(float(effect["value"])) if effect else 0.0)
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 3.8))
    ax.bar(labels, values, color="#4c78a8")
    ax.set_title("Effect Size Magnitude by Hypothesis")
    ax.set_ylabel("Absolute effect size")
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _extract_p_value(metrics: dict[str, Any]) -> float | None:
    if isinstance(metrics.get("p_value"), (int, float)):
        return float(metrics["p_value"])
    spearman = metrics.get("spearman")
    if isinstance(spearman, dict) and isinstance(spearman.get("p_value"), (int, float)):
        return float(spearman["p_value"])
    top_pairs = metrics.get("top_pairs")
    if isinstance(top_pairs, list) and top_pairs and isinstance(top_pairs[0].get("p_value"), (int, float)):
        return float(top_pairs[0]["p_value"])
    return None


def _extract_n(metrics: dict[str, Any]) -> int | None:
    for key in ("n", "n_events", "total_n"):
        if isinstance(metrics.get(key), int):
            return int(metrics[key])
    spearman = metrics.get("spearman")
    if isinstance(spearman, dict) and isinstance(spearman.get("n"), int):
        return int(spearman["n"])
    top_pairs = metrics.get("top_pairs")
    if isinstance(top_pairs, list) and top_pairs and isinstance(top_pairs[0].get("n"), int):
        return int(top_pairs[0]["n"])
    return None


def _extract_effect_size(result: TestResult) -> dict[str, Any] | None:
    metrics = result.metrics
    spearman = metrics.get("spearman")
    if isinstance(spearman, dict) and isinstance(spearman.get("rho"), (int, float)):
        return {"metric": "spearman_rho", "value": float(spearman["rho"])}
    if result.method == "numeric_correlation":
        pairs = metrics.get("top_pairs")
        if isinstance(pairs, list) and pairs and isinstance(pairs[0].get("rho"), (int, float)):
            return {"metric": "spearman_rho", "value": float(pairs[0]["rho"])}
    if isinstance(metrics.get("epsilon_squared"), (int, float)):
        return {"metric": "epsilon_squared", "value": float(metrics["epsilon_squared"])}
    if isinstance(metrics.get("r_squared"), (int, float)):
        return {"metric": "r_squared", "value": float(metrics["r_squared"])}
    return None


def _has_skipped_result(results: list[TestResult]) -> bool:
    return any(result.status == "skipped" for result in results)


def _mae(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y - pred)))


def _rmse(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - pred) ** 2)))


def _r2(y: np.ndarray, pred: np.ndarray) -> float | None:
    total = float(np.sum((y - y.mean()) ** 2))
    if total == 0:
        return None
    return float(1.0 - float(np.sum((y - pred) ** 2)) / total)
