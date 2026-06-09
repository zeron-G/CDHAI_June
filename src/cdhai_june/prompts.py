from __future__ import annotations

import json
from typing import Any

from cdhai_june.models import TestResult
from cdhai_june.utils import compact_text

BASIC_REPORT_SYSTEM = (
    "You are a careful biomedical research analyst writing a paper-grade baseline "
    "report from deterministic patient-data outputs. Do not give medical advice. "
    "Distinguish observed facts, exploratory hypotheses, statistical evidence, "
    "machine-learning triangulation, and limitations. Cite only supplied reference ids."
)

CYCLE_REPORT_SYSTEM = (
    "You are a patient-data research agent. Write a concise but rigorous cycle "
    "report from hypotheses, deterministic test results, and the research audit. "
    "Include literature context, hypothesis, mechanism, mathematical/statistical "
    "formulation, ML relevance, falsification, figures, limitations, and next probes. "
    "Do not disclose hidden chain-of-thought or make clinical recommendations. "
    "Cite only supplied reference ids."
)

FINAL_REPORT_SYSTEM = (
    "You synthesize multiple patient-data research reports. Connect evidence "
    "across cycles, identify robust and weak relationships, audit citation/data "
    "integrity, and state what remains exploratory. Do not provide medical advice."
)


def basic_report_prompt(patient_id: str, basic_profile: dict[str, Any], research_context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "patient_id": patient_id,
            "task": "Write the initial baseline data report as a research-grade opening analysis.",
            "basic_profile": compact_text(json.dumps(basic_profile, default=str), 9000),
            "research_context": compact_text(json.dumps(research_context, default=str), 9000),
            "requested_sections": [
                "Structured abstract",
                "Literature context using supplied reference ids",
                "Data and methods",
                "Baseline descriptive results",
                "Mathematical definitions and statistical plan",
                "Machine-learning baseline",
                "Figures and tables",
                "Limitations and missingness",
                "Next research hypotheses",
                "References",
            ],
        },
        default=str,
    )


def cycle_report_prompt(
    *,
    patient_id: str,
    cycle: int,
    hypotheses: list[dict[str, Any]],
    results: list[TestResult],
    kb_context: dict[str, Any],
    cross_report_links: list[dict[str, Any]],
    research_context: dict[str, Any],
    cycle_research_review: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "patient_id": patient_id,
            "cycle": cycle,
            "task": "Write a paper-grade cycle report from the hypotheses, test results, and research audit.",
            "hypotheses": hypotheses,
            "test_results": [result.to_json() for result in results],
            "recent_context": kb_context,
            "cross_report_links": cross_report_links,
            "research_context": compact_text(json.dumps(research_context, default=str), 8000),
            "cycle_research_review": cycle_research_review,
            "requested_sections": [
                "Cycle research question",
                "Literature review and reference hooks",
                "Hypothesis and falsification criterion",
                "Mechanistic reasoning",
                "Mathematical/statistical formulation",
                "Statistical evidence with effect size and correction",
                "Machine-learning triangulation",
                "Visualization results",
                "Cross-report relationships",
                "Limitations and data-quality threats",
                "Next cycle suggestions",
                "References",
            ],
        },
        default=str,
    )


def final_report_prompt(
    *,
    patient_id: str,
    manifest: dict[str, Any],
    kb_context: dict[str, Any],
    cross_report_links: list[dict[str, Any]],
    research_context: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "patient_id": patient_id,
            "task": "Write final paper-grade synthesis across all cycles.",
            "manifest": manifest,
            "recent_context": kb_context,
            "cross_report_links": cross_report_links,
            "research_context": compact_text(json.dumps(research_context, default=str), 12000),
            "requested_sections": [
                "Structured abstract",
                "Background and literature map",
                "Methods and reproducibility",
                "Cross-cycle results",
                "Mathematical and statistical evidence",
                "Machine-learning prediction evidence",
                "Figures",
                "Citation and claim-integrity audit",
                "Weak or conflicting evidence",
                "Recommended next analyses",
                "Application handoff notes",
                "References",
            ],
        },
        default=str,
    )
