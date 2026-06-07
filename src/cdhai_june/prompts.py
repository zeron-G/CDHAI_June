from __future__ import annotations

import json
from typing import Any

from cdhai_june.models import TestResult
from cdhai_june.utils import compact_text


BASIC_REPORT_SYSTEM = (
    "You are a careful biomedical data analyst. Summarize patient data quality "
    "and descriptive statistics. Do not give medical advice. Distinguish facts "
    "from hypotheses."
)

CYCLE_REPORT_SYSTEM = (
    "You are a patient-data analysis agent. Write a concise research report "
    "from statistical test results. Mention limitations and next probes. Do "
    "not disclose hidden chain-of-thought or make clinical recommendations."
)

FINAL_REPORT_SYSTEM = (
    "You synthesize multiple patient-data reports. Connect evidence across "
    "cycles, identify robust relationships, and flag uncertain findings."
)


def basic_report_prompt(patient_id: str, basic_profile: dict[str, Any]) -> str:
    return json.dumps(
        {
            "patient_id": patient_id,
            "task": "Write the initial baseline data report.",
            "basic_profile": compact_text(json.dumps(basic_profile, default=str), 9000),
            "requested_sections": [
                "Data overview",
                "Data quality",
                "CGM summary if present",
                "Behavior/event summary if present",
                "Limitations",
                "Next analysis directions",
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
) -> str:
    return json.dumps(
        {
            "patient_id": patient_id,
            "cycle": cycle,
            "task": "Write a cycle report from the hypotheses and test results.",
            "hypotheses": hypotheses,
            "test_results": [result.to_json() for result in results],
            "recent_context": kb_context,
            "cross_report_links": cross_report_links,
            "requested_sections": [
                "Cycle question",
                "Hypotheses tested",
                "Statistical evidence",
                "Cross-report relationships",
                "Limitations",
                "Next cycle suggestions",
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
) -> str:
    return json.dumps(
        {
            "patient_id": patient_id,
            "task": "Write final synthesis across all cycles.",
            "manifest": manifest,
            "recent_context": kb_context,
            "cross_report_links": cross_report_links,
            "requested_sections": [
                "Most stable findings",
                "Data relationships worth follow-up",
                "Weak or conflicting evidence",
                "Recommended next analyses",
                "Application handoff notes",
            ],
        },
        default=str,
    )

