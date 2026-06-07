from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


JSONDict = dict[str, Any]


@dataclass(slots=True)
class PatientDataset:
    patient_id: str
    tables: dict[str, pd.DataFrame]
    source_path: Path
    primary_table: str
    column_roles: dict[str, str | None] = field(default_factory=dict)

    @property
    def primary(self) -> pd.DataFrame:
        return self.tables[self.primary_table]


@dataclass(slots=True)
class Artifact:
    name: str
    path: Path
    kind: str
    summary: str = ""

    def to_json(self) -> JSONDict:
        return {
            "name": self.name,
            "path": str(self.path),
            "kind": self.kind,
            "summary": self.summary,
        }


@dataclass(slots=True)
class Hypothesis:
    hypothesis_id: str
    statement: str
    rationale: str
    variables: list[str]
    test_family: str
    cycle: int
    priority: int = 3
    source: str = "deterministic"

    def to_json(self) -> JSONDict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "rationale": self.rationale,
            "variables": self.variables,
            "test_family": self.test_family,
            "cycle": self.cycle,
            "priority": self.priority,
            "source": self.source,
        }


@dataclass(slots=True)
class TestResult:
    hypothesis_id: str
    method: str
    status: str
    summary: str
    metrics: JSONDict = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)

    def to_json(self) -> JSONDict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "method": self.method,
            "status": self.status,
            "summary": self.summary,
            "metrics": self.metrics,
            "artifacts": [artifact.to_json() for artifact in self.artifacts],
        }


@dataclass(slots=True)
class Insight:
    cycle: int
    kind: str
    text: str
    evidence: list[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_json(self) -> JSONDict:
        return {
            "cycle": self.cycle,
            "kind": self.kind,
            "text": self.text,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class RunPaths:
    output_root: Path
    run_dir: Path
    analysis_dir: Path
    cycles_dir: Path
    reports_dir: Path
    kb_dir: Path

    def ensure(self) -> None:
        for path in (
            self.output_root,
            self.run_dir,
            self.analysis_dir,
            self.cycles_dir,
            self.reports_dir,
            self.kb_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

