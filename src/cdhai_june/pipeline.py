from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cdhai_june.analysis.basic import BasicAnalyzer
from cdhai_june.analysis.hypotheses import HypothesisPlanner, HypothesisTester, write_cycle_payload
from cdhai_june.config import AppConfig
from cdhai_june.data_loader import load_patient_dataset
from cdhai_june.external.database import database_runtime_hint
from cdhai_june.external.foundations import foundational_dependency_statuses
from cdhai_june.external.haipipe_toolkit import haipipe_toolkit_status
from cdhai_june.knowledge_base import PersonalKnowledgeBase
from cdhai_june.llm import build_llm_client
from cdhai_june.models import RunPaths
from cdhai_june.reporting import ReportWriter
from cdhai_june.research import build_cycle_research_review, build_research_context
from cdhai_june.task_cycle import TaskCycleRunner
from cdhai_june.utils import write_json


class PatientAnalysisPipeline:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm_client = build_llm_client(config.llm)
        self.report_writer = ReportWriter(self.llm_client)
        self.basic_analyzer = BasicAnalyzer(config.analysis)
        self.hypothesis_planner = HypothesisPlanner(config.analysis)
        self.hypothesis_tester = HypothesisTester(config.analysis)
        self.task_cycle_runner = TaskCycleRunner(config.analysis)

    def run(self, input_path: str | Path, patient_id: str | None = None) -> dict[str, Any]:
        dataset = load_patient_dataset(input_path, patient_id=patient_id)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        paths = self._build_paths(dataset.patient_id, run_id)
        paths.ensure()

        kb = PersonalKnowledgeBase(paths.kb_dir)
        basic_profile = self.basic_analyzer.run(dataset, paths.analysis_dir)
        research_context = build_research_context(
            dataset=dataset,
            basic_profile=basic_profile,
            analysis_dir=paths.analysis_dir,
            external_config=self.config.external,
            analysis_config=self.config.analysis,
        )
        baseline_path, baseline_summary = self.report_writer.write_basic_report(
            dataset.patient_id,
            basic_profile,
            research_context,
            paths.reports_dir,
        )
        kb.add_report(
            run_id=run_id,
            cycle=0,
            title="Baseline Data Report",
            report_path=baseline_path,
            summary=baseline_summary,
        )

        manifest: dict[str, Any] = {
            "run_id": run_id,
            "patient_id": dataset.patient_id,
            "input_path": str(dataset.source_path),
            "llm_provider": self.llm_client.provider_name,
            "llm_model": self.config.llm.model,
            "cycles_requested": self.config.analysis.max_narrative_cycles,
            "paths": {
                "run_dir": str(paths.run_dir),
                "analysis_dir": str(paths.analysis_dir),
                "reports_dir": str(paths.reports_dir),
                "kb_dir": str(paths.kb_dir),
            },
            "baseline_report": str(baseline_path),
            "research_artifacts": {
                "research_context": str(paths.analysis_dir / "research_context.json"),
                "research_protocol": str(paths.analysis_dir / "research_protocol.json"),
                "literature_matrix": str(paths.analysis_dir / "literature_matrix.json"),
                "reference_manifest": str(paths.analysis_dir / "reference_manifest.json"),
                "figure_index": str(paths.analysis_dir / "figure_index.json"),
                "ml_prediction_metrics": str(paths.analysis_dir / "ml_prediction_metrics.json"),
            },
            "cycle_reports": [],
            "external": {
                "foundational_dependencies": foundational_dependency_statuses(self.config.external),
                "haipipe_toolkit": haipipe_toolkit_status(self.config.external).to_json(),
                "welldoc_space_path": str(self.config.external.welldoc_space_path),
                "tools_path": str(self.config.external.tools_path),
                "codex_oauth_package_path": str(self.config.external.codex_oauth_package_path),
                "database": database_runtime_hint(self.config.database),
            },
        }

        for cycle in range(1, self.config.analysis.max_narrative_cycles + 1):
            cycle_dir = paths.cycles_dir / f"cycle_{cycle:02d}"
            kb_context = kb.recent_context()
            hypotheses = self.hypothesis_planner.plan(
                cycle=cycle,
                dataset=dataset,
                basic_profile=basic_profile,
                kb_context=kb_context,
                llm_client=self.llm_client,
            )
            results = [self.hypothesis_tester.test(dataset, hypothesis, cycle_dir) for hypothesis in hypotheses]
            write_cycle_payload(cycle_dir, hypotheses, results)
            task_chain = self.task_cycle_runner.run(
                cycle=cycle,
                dataset=dataset,
                hypotheses=hypotheses,
                statistical_results=results,
                basic_profile=basic_profile,
                research_context=research_context,
                cycle_dir=cycle_dir,
            )
            cycle_research_review = build_cycle_research_review(
                cycle=cycle,
                hypotheses=hypotheses,
                results=results,
                research_context=research_context,
                cycle_dir=cycle_dir,
                analysis_config=self.config.analysis,
                task_chain=task_chain,
            )
            kb.add_hypotheses(run_id=run_id, cycle=cycle, hypotheses=[hypothesis.to_json() for hypothesis in hypotheses])

            report_path, report_summary, insights = self.report_writer.write_cycle_report(
                patient_id=dataset.patient_id,
                cycle=cycle,
                hypotheses=[hypothesis.to_json() for hypothesis in hypotheses],
                results=results,
                kb_context=kb_context,
                cross_report_links=kb.cross_report_links(),
                research_context=research_context,
                cycle_research_review=cycle_research_review,
                reports_dir=paths.reports_dir,
            )
            kb.add_report(
                run_id=run_id,
                cycle=cycle,
                title=f"Cycle {cycle:02d} Probe Report",
                report_path=report_path,
                summary=report_summary,
            )
            persisted_insights = insights if task_chain.get("insight_stage_allowed") else []
            if persisted_insights:
                kb.add_insights(run_id=run_id, insights=persisted_insights)
            manifest["cycle_reports"].append(
                {
                    "cycle": cycle,
                    "report_path": str(report_path),
                    "cycle_dir": str(cycle_dir),
                    "research_cycle_review": str(cycle_dir / "research_cycle_review.json"),
                    "task_chain": str(cycle_dir / "task_chain" / "task_chain_summary.json"),
                    "gate_decision": str(cycle_dir / "task_chain" / "gate_decision.json"),
                    "insight_stage_allowed": bool(task_chain.get("insight_stage_allowed")),
                    "insights_persisted": len(persisted_insights),
                    "hypotheses": [hypothesis.to_json() for hypothesis in hypotheses],
                    "results": [result.to_json() for result in results],
                }
            )

        final_path, final_summary = self.report_writer.write_final_report(
            patient_id=dataset.patient_id,
            manifest=manifest,
            kb_context=kb.recent_context(limit=30),
            cross_report_links=kb.cross_report_links(limit=30),
            research_context=research_context,
            reports_dir=paths.reports_dir,
        )
        kb.add_report(
            run_id=run_id,
            cycle=self.config.analysis.max_narrative_cycles + 1,
            title="Final Cross-Cycle Synthesis",
            report_path=final_path,
            summary=final_summary,
        )
        manifest["final_report"] = str(final_path)
        write_json(paths.run_dir / "manifest.json", manifest)
        return manifest

    def _build_paths(self, patient_id: str, run_id: str) -> RunPaths:
        output_root = self.config.analysis.output_dir.resolve()
        run_dir = output_root / patient_id / run_id
        return RunPaths(
            output_root=output_root,
            run_dir=run_dir,
            analysis_dir=run_dir / "analysis",
            cycles_dir=run_dir / "cycles",
            reports_dir=run_dir / "reports",
            kb_dir=output_root / "personal_knowledge_base" / patient_id,
        )


def manifest_as_text(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False)
