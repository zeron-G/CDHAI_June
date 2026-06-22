from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cdhai_june.llm import LLMClient
from cdhai_june.models import Insight, TestResult
from cdhai_june.prompts import (
    BASIC_REPORT_SYSTEM,
    CYCLE_REPORT_SYSTEM,
    FINAL_REPORT_SYSTEM,
    basic_report_prompt,
    cycle_report_prompt,
    final_report_prompt,
)
from cdhai_june.utils import compact_text, stable_subject_alias


class ReportWriter:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def write_basic_report(
        self,
        patient_id: str,
        basic_profile: dict[str, Any],
        research_context: dict[str, Any],
        reports_dir: Path,
    ) -> tuple[Path, str]:
        patient_alias = stable_subject_alias(patient_id)
        text = self.llm_client.generate(
            system=BASIC_REPORT_SYSTEM,
            prompt=basic_report_prompt(
                patient_alias,
                _redact_identifier(basic_profile, patient_id, patient_alias),
                _redact_identifier(research_context, patient_id, patient_alias),
            ),
        )
        text = text.replace(patient_id, patient_alias)
        report = (
            "# Baseline Data Report\n\n"
            + text.strip()
            + "\n\n"
            + _baseline_research_markdown(basic_profile, research_context, reports_dir)
            + "\n"
        )
        path = reports_dir / "00_baseline_report.md"
        path.write_text(report, encoding="utf-8")
        return path, _summary_from_text(report)

    def write_cycle_report(
        self,
        *,
        patient_id: str,
        cycle: int,
        hypotheses: list[dict[str, Any]],
        results: list[TestResult],
        kb_context: dict[str, Any],
        cross_report_links: list[dict[str, Any]],
        research_context: dict[str, Any],
        cycle_research_review: dict[str, Any],
        reports_dir: Path,
    ) -> tuple[Path, str, list[Insight]]:
        patient_alias = stable_subject_alias(patient_id)
        text = self.llm_client.generate(
            system=CYCLE_REPORT_SYSTEM,
            prompt=cycle_report_prompt(
                patient_id=patient_alias,
                cycle=cycle,
                hypotheses=hypotheses,
                results=results,
                kb_context=_redact_identifier(kb_context, patient_id, patient_alias),
                cross_report_links=_redact_identifier(cross_report_links, patient_id, patient_alias),
                research_context=_redact_identifier(research_context, patient_id, patient_alias),
                cycle_research_review=_redact_identifier(
                    cycle_research_review, patient_id, patient_alias
                ),
            ),
        )
        text = text.replace(patient_id, patient_alias)
        report = (
            f"# Cycle {cycle:02d} Probe Report\n\n"
            + _results_markdown(results)
            + "\n\n"
            + text.strip()
            + "\n\n"
            + _cycle_research_markdown(cycle_research_review, research_context, reports_dir)
            + "\n"
        )
        path = reports_dir / f"{cycle:02d}_cycle_report.md"
        path.write_text(report, encoding="utf-8")
        insights = _insights_from_results(cycle, results)
        insights.extend(_insights_from_task_cycle(cycle, cycle_research_review.get("task_cycle", {})))
        return path, _summary_from_text(report), insights

    def write_final_report(
        self,
        *,
        patient_id: str,
        manifest: dict[str, Any],
        kb_context: dict[str, Any],
        cross_report_links: list[dict[str, Any]],
        research_context: dict[str, Any],
        reports_dir: Path,
    ) -> tuple[Path, str]:
        patient_alias = stable_subject_alias(patient_id)
        text = self.llm_client.generate(
            system=FINAL_REPORT_SYSTEM,
            prompt=final_report_prompt(
                patient_id=patient_alias,
                manifest=_redact_identifier(manifest, patient_id, patient_alias),
                kb_context=_redact_identifier(kb_context, patient_id, patient_alias),
                cross_report_links=_redact_identifier(cross_report_links, patient_id, patient_alias),
                research_context=_redact_identifier(research_context, patient_id, patient_alias),
            ),
        )
        text = text.replace(patient_id, patient_alias)
        report = (
            "# Final Cross-Cycle Synthesis\n\n"
            + text.strip()
            + "\n\n"
            + _final_research_markdown(manifest, research_context, reports_dir)
            + "\n"
        )
        path = reports_dir / "99_final_report.md"
        path.write_text(report, encoding="utf-8")
        return path, _summary_from_text(report)


def _results_markdown(results: list[TestResult]) -> str:
    lines = ["## Executed Statistical Probes", ""]
    for result in results:
        lines.append(f"- `{result.hypothesis_id}` `{result.method}` `{result.status}`: {result.summary}")
    return "\n".join(lines)


def _redact_identifier(value: Any, identifier: str, alias: str) -> Any:
    if isinstance(value, dict):
        return {key: _redact_identifier(item, identifier, alias) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_identifier(item, identifier, alias) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_identifier(item, identifier, alias) for item in value)
    if isinstance(value, str):
        return value.replace(identifier, alias)
    return value


def _baseline_research_markdown(
    basic_profile: dict[str, Any],
    research_context: dict[str, Any],
    reports_dir: Path,
) -> str:
    protocol = research_context.get("research_protocol", {})
    questions = protocol.get("research_questions", [])
    ml = basic_profile.get("ml_prediction", {})
    lines = ["## Research-Grade Scaffold", ""]
    lines.append("### Research Questions")
    for item in questions:
        lines.append(f"- `{item.get('id')}` {item.get('question')} References: {', '.join(item.get('reference_ids', []))}.")
    lines.extend(["", "### Mathematical Definitions"])
    for key, value in protocol.get("mathematical_formalization", {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "### Machine-Learning Baseline"])
    if ml.get("available"):
        lines.append(
            "- Next-glucose ridge baseline: "
            f"train n={ml.get('train_n')}, test n={ml.get('test_n')}, "
            f"MAE={_fmt(ml.get('mae_mgdl'))} mg/dL, "
            f"persistence MAE={_fmt(ml.get('naive_persistence_mae_mgdl'))} mg/dL."
        )
    else:
        lines.append(f"- Not available: {ml.get('reason', 'No ML baseline was produced.')}")
    lines.extend(["", _figure_markdown(research_context, reports_dir), "", _references_markdown(research_context)])
    return "\n".join(lines)


def _cycle_research_markdown(
    cycle_research_review: dict[str, Any],
    research_context: dict[str, Any],
    reports_dir: Path,
) -> str:
    lines = ["## Research Cycle Audit", ""]
    lines.append("### Hypothesis Chain")
    for item in cycle_research_review.get("hypothesis_chain", []):
        lines.append(
            f"- `{item.get('hypothesis_id')}` {item.get('statement')} "
            f"Refs: {', '.join(item.get('reference_hooks', []))}."
        )
    lines.extend(["", "### Statistical Reporting Gate"])
    for row in cycle_research_review.get("statistical_audit", {}).get("rows", []):
        effect = row.get("effect_size") or {}
        effect_text = f"{effect.get('metric')}={_fmt(effect.get('value'))}" if effect else "effect size not available"
        lines.append(
            f"- `{row.get('hypothesis_id')}` `{row.get('method')}` n={row.get('n')} "
            f"p={_fmt(row.get('p_value'))}; {effect_text}; status={row.get('status')}."
        )
    holm = cycle_research_review.get("statistical_audit", {}).get("holm_correction", [])
    if holm:
        lines.extend(["", "### Multiple-Testing Audit"])
        for row in holm:
            decision = "reject" if row.get("reject_after_holm") else "do not reject"
            lines.append(
                f"- `{row.get('hypothesis_id')}` p={_fmt(row.get('p_value'))}, "
                f"Holm threshold={_fmt(row.get('holm_threshold'))}: {decision}."
            )
    task_cycle = cycle_research_review.get("task_cycle", {})
    if task_cycle:
        gate = task_cycle.get("gate_decision", {})
        lines.extend(["", "### Exploration Task Chain and Evidence Gate"])
        lines.append(
            f"- Task chain: {task_cycle.get('task_count', 0)} tasks across "
            f"{task_cycle.get('rounds_executed', 0)} round(s)."
        )
        lines.append(f"- Evidence gate: `{gate.get('status')}` — {gate.get('reason')}")
        for task in task_cycle.get("tasks", [])[:8]:
            lines.append(f"  - `{task.get('task_id')}` `{task.get('type')}` `{task.get('status')}`: {task.get('summary')}")
        for row in gate.get("hypothesis_decisions", [])[:8]:
            lines.append(
                f"  - `{row.get('hypothesis_id')}` decision=`{row.get('decision')}`; {row.get('reason')}"
            )
        artifact_lines = _task_artifacts_markdown(task_cycle, reports_dir)
        if artifact_lines:
            lines.extend(["", "### Task-Cycle Artifacts", *artifact_lines])
        hapf_task = next(
            (task for task in task_cycle.get("tasks", []) if task.get("type") == "personalized_forecasting"),
            None,
        )
        if hapf_task:
            evidence = hapf_task.get("evidence", {})
            lines.extend(["", "### HAPF Personalized Forecasting"])
            lines.append(f"- Status: `{hapf_task.get('status')}`. {hapf_task.get('summary')}")
            if hapf_task.get("status") == "completed":
                lines.append(
                    "- Forecast RMSE by horizon: "
                    f"population={evidence.get('population_rmse', [])}; "
                    f"personalized={evidence.get('personalized_rmse', [])}; "
                    f"deployed={evidence.get('deployed_rmse', [])}."
                )
                lines.append(
                    f"- Personalization gate: `{evidence.get('gate_status')}`; "
                    f"deployed model=`{evidence.get('deployed_model')}`; "
                    f"relative calibration improvement={_fmt(evidence.get('relative_improvement'))}; "
                    f"cache reused={evidence.get('cache_reused')}."
                )
    lines.extend(["", _figure_markdown(research_context, reports_dir), "", _references_markdown(research_context)])
    return "\n".join(lines)


def _final_research_markdown(
    manifest: dict[str, Any],
    research_context: dict[str, Any],
    reports_dir: Path,
) -> str:
    lines = ["## Research Integrity Summary", ""]
    lines.append(f"- Cycles requested: {manifest.get('cycles_requested')}; cycle reports produced: {len(manifest.get('cycle_reports', []))}.")
    gated = [item for item in manifest.get("cycle_reports", []) if item.get("gate_decision")]
    lines.append(f"- Evidence-gated task chains recorded: {len(gated)}.")
    hapf_cycles = [
        item.get("hapf", {})
        for item in manifest.get("cycle_reports", [])
        if item.get("hapf", {}).get("status") == "completed"
    ]
    accepted = sum(1 for item in hapf_cycles if item.get("evidence", {}).get("gate_accepted"))
    lines.append(f"- HAPF completed cycles: {len(hapf_cycles)}; personalization gates accepted: {accepted}.")
    lines.append("- Claim boundary: all findings are exploratory N-of-1 evidence unless externally replicated.")
    lines.append("- Citation boundary: final text should cite only the manifest below until external discovery verifies new sources.")
    lines.extend(["", _figure_markdown(research_context, reports_dir), "", _references_markdown(research_context)])
    return "\n".join(lines)


def _figure_markdown(research_context: dict[str, Any], reports_dir: Path) -> str:
    figures = research_context.get("figure_index", {}).get("figures", [])
    lines = ["### Figures"]
    if not figures:
        lines.append("- No figures were generated for this run.")
        return "\n".join(lines)
    for item in figures:
        path = Path(str(item.get("absolute_path", "")))
        rel_path = _relative_link(path, reports_dir)
        title = str(item.get("title", path.stem))
        lines.append(f"- `{item.get('figure_id')}` {title}: ![{title}]({rel_path})")
    return "\n".join(lines)


def _task_artifacts_markdown(task_cycle: dict[str, Any], reports_dir: Path) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for task in task_cycle.get("tasks", []):
        artifacts = task.get("artifacts", {})
        if not isinstance(artifacts, dict):
            continue
        for label, raw_path in artifacts.items():
            if not raw_path:
                continue
            path = Path(str(raw_path))
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            rel_path = _relative_link(path, reports_dir)
            title = str(label).replace("_", " ").title()
            suffix = path.suffix.lower()
            if suffix == ".png":
                lines.append(f"- `{task.get('task_id')}` {title}: ![{title}]({rel_path})")
            elif suffix in {".json", ".csv", ".md"}:
                lines.append(f"- `{task.get('task_id')}` {title}: [{path.name}]({rel_path})")
    return lines[:16]


def _references_markdown(research_context: dict[str, Any]) -> str:
    references = research_context.get("reference_manifest", {}).get("references", [])
    lines = ["### References"]
    if not references:
        lines.append("- No verified reference manifest is available.")
        return "\n".join(lines)
    for item in references:
        lines.append(
            f"- `{item.get('id')}` {item.get('authors')} ({item.get('year')}). "
            f"{item.get('title')}. {item.get('venue')}. "
            f"DOI: {item.get('doi')}. {item.get('url')}"
        )
    return "\n".join(lines)


def _relative_link(path: Path, reports_dir: Path) -> str:
    try:
        return Path(os.path.relpath(path.resolve(), reports_dir.resolve())).as_posix()
    except ValueError:
        return path.as_posix()


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return str(value)


def _summary_from_text(text: str) -> str:
    body = "\n".join(line for line in text.splitlines() if line and not line.startswith("#"))
    return compact_text(body, 700)


def _insights_from_results(cycle: int, results: list[TestResult]) -> list[Insight]:
    insights: list[Insight] = []
    for result in results:
        if result.status in {"supported", "descriptive"}:
            insights.append(
                Insight(
                    cycle=cycle,
                    kind=result.method,
                    text=result.summary,
                    evidence=[result.hypothesis_id],
                    confidence="high" if result.status == "supported" else "medium",
                )
            )
    return insights


def _insights_from_task_cycle(cycle: int, task_cycle: dict[str, Any]) -> list[Insight]:
    task = next(
        (item for item in task_cycle.get("tasks", []) if item.get("type") == "personalized_forecasting"),
        None,
    )
    if not task or task.get("status") != "completed":
        return []
    evidence = task.get("evidence", {})
    return [
        Insight(
            cycle=cycle,
            kind="personalized_forecasting",
            text=str(task.get("summary", "HAPF personalized forecasting completed.")),
            evidence=[
                f"gate_status={evidence.get('gate_status')}",
                f"deployed_model={evidence.get('deployed_model')}",
                f"relative_improvement={evidence.get('relative_improvement')}",
            ],
            confidence="medium" if evidence.get("gate_accepted") else "low",
        )
    ]
