from __future__ import annotations

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
from cdhai_june.utils import compact_text


class ReportWriter:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def write_basic_report(self, patient_id: str, basic_profile: dict[str, Any], reports_dir: Path) -> tuple[Path, str]:
        text = self.llm_client.generate(
            system=BASIC_REPORT_SYSTEM,
            prompt=basic_report_prompt(patient_id, basic_profile),
        )
        report = "# Baseline Data Report\n\n" + text.strip() + "\n"
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
        reports_dir: Path,
    ) -> tuple[Path, str, list[Insight]]:
        text = self.llm_client.generate(
            system=CYCLE_REPORT_SYSTEM,
            prompt=cycle_report_prompt(
                patient_id=patient_id,
                cycle=cycle,
                hypotheses=hypotheses,
                results=results,
                kb_context=kb_context,
                cross_report_links=cross_report_links,
            ),
        )
        evidence = [result.summary for result in results]
        report = f"# Cycle {cycle:02d} Probe Report\n\n" + _results_markdown(results) + "\n\n" + text.strip() + "\n"
        path = reports_dir / f"{cycle:02d}_cycle_report.md"
        path.write_text(report, encoding="utf-8")
        insights = _insights_from_results(cycle, results)
        return path, _summary_from_text(report), insights

    def write_final_report(
        self,
        *,
        patient_id: str,
        manifest: dict[str, Any],
        kb_context: dict[str, Any],
        cross_report_links: list[dict[str, Any]],
        reports_dir: Path,
    ) -> tuple[Path, str]:
        text = self.llm_client.generate(
            system=FINAL_REPORT_SYSTEM,
            prompt=final_report_prompt(
                patient_id=patient_id,
                manifest=manifest,
                kb_context=kb_context,
                cross_report_links=cross_report_links,
            ),
        )
        report = "# Final Cross-Cycle Synthesis\n\n" + text.strip() + "\n"
        path = reports_dir / "99_final_report.md"
        path.write_text(report, encoding="utf-8")
        return path, _summary_from_text(report)


def _results_markdown(results: list[TestResult]) -> str:
    lines = ["## Executed Statistical Probes", ""]
    for result in results:
        lines.append(f"- `{result.hypothesis_id}` `{result.method}` `{result.status}`: {result.summary}")
    return "\n".join(lines)


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

