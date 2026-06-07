from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cdhai_june.models import Insight


class PersonalKnowledgeBase:
    def __init__(self, kb_dir: Path) -> None:
        self.kb_dir = kb_dir
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.insights_path = self.kb_dir / "insights.jsonl"
        self.reports_path = self.kb_dir / "reports.jsonl"
        self.hypotheses_path = self.kb_dir / "hypotheses.jsonl"

    @staticmethod
    def _stamp(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            **record,
        }

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    @staticmethod
    def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        if limit is None:
            return rows
        return rows[-limit:]

    def add_report(self, *, run_id: str, cycle: int, title: str, report_path: Path, summary: str) -> None:
        self._append_jsonl(
            self.reports_path,
            self._stamp(
                {
                    "run_id": run_id,
                    "cycle": cycle,
                    "title": title,
                    "report_path": str(report_path),
                    "summary": summary,
                }
            ),
        )

    def add_hypotheses(self, *, run_id: str, cycle: int, hypotheses: list[dict[str, Any]]) -> None:
        for hypothesis in hypotheses:
            self._append_jsonl(
                self.hypotheses_path,
                self._stamp({"run_id": run_id, "cycle": cycle, **hypothesis}),
            )

    def add_insights(self, *, run_id: str, insights: list[Insight]) -> None:
        for insight in insights:
            self._append_jsonl(
                self.insights_path,
                self._stamp({"run_id": run_id, **insight.to_json()}),
            )

    def recent_context(self, limit: int = 12) -> dict[str, Any]:
        return {
            "reports": self._read_jsonl(self.reports_path, limit=limit),
            "insights": self._read_jsonl(self.insights_path, limit=limit),
            "hypotheses": self._read_jsonl(self.hypotheses_path, limit=limit),
        }

    def cross_report_links(self, limit: int = 20) -> list[dict[str, Any]]:
        reports = self._read_jsonl(self.reports_path, limit=limit)
        links: list[dict[str, Any]] = []
        for i, left in enumerate(reports):
            left_words = _keywords(str(left.get("summary", "")))
            for right in reports[i + 1 :]:
                right_words = _keywords(str(right.get("summary", "")))
                overlap = sorted(left_words & right_words)
                if len(overlap) >= 2:
                    links.append(
                        {
                            "left": left.get("title"),
                            "right": right.get("title"),
                            "shared_terms": overlap[:8],
                        }
                    )
        return links[-limit:]


def _keywords(text: str) -> set[str]:
    stop = {
        "with",
        "from",
        "that",
        "this",
        "have",
        "were",
        "their",
        "cycle",
        "report",
        "analysis",
        "patient",
    }
    words = {
        word.lower()
        for word in __import__("re").findall(r"[A-Za-z][A-Za-z0-9_]{3,}", text)
        if word.lower() not in stop
    }
    return words

