from pathlib import Path

from cdhai_june.config import AnalysisConfig, AppConfig, LLMConfig
from cdhai_june.pipeline import PatientAnalysisPipeline


def test_pipeline_dry_run_creates_reports(tmp_path: Path) -> None:
    sample = Path(__file__).parents[1] / "examples" / "sample_patient.csv"
    config = AppConfig(
        analysis=AnalysisConfig(max_narrative_cycles=2, output_dir=tmp_path, plot=False),
        llm=LLMConfig(provider="mock"),
    )

    manifest = PatientAnalysisPipeline(config).run(sample, patient_id="demo-test")

    run_dir = Path(manifest["paths"]["run_dir"])
    assert (run_dir / "manifest.json").exists()
    assert Path(manifest["baseline_report"]).exists()
    assert Path(manifest["final_report"]).exists()
    assert Path(manifest["research_artifacts"]["research_protocol"]).exists()
    assert Path(manifest["research_artifacts"]["reference_manifest"]).exists()
    assert len(manifest["cycle_reports"]) == 2
    assert Path(manifest["cycle_reports"][0]["research_cycle_review"]).exists()
    assert Path(manifest["cycle_reports"][0]["task_chain"]).exists()
    assert Path(manifest["cycle_reports"][0]["gate_decision"]).exists()
    assert manifest["cycle_reports"][0]["insight_stage_allowed"] is True
    assert manifest["cycle_reports"][0]["insights_persisted"] >= 1
    cycle_report_text = Path(manifest["cycle_reports"][0]["report_path"]).read_text(encoding="utf-8")
    assert "Task-Cycle Artifacts" in cycle_report_text
    assert "statistical_evidence_overview.png" in cycle_report_text
    assert "nn_observed_vs_predicted.png" in cycle_report_text


def test_pipeline_sanitizes_patient_id_for_output_paths(tmp_path: Path) -> None:
    sample = Path(__file__).parents[1] / "examples" / "sample_patient.csv"
    config = AppConfig(
        analysis=AnalysisConfig(max_narrative_cycles=1, output_dir=tmp_path, plot=False),
        llm=LLMConfig(provider="mock"),
    )

    manifest = PatientAnalysisPipeline(config).run(sample, patient_id="..\\escape/patient")

    run_dir = Path(manifest["paths"]["run_dir"]).resolve()
    assert run_dir.is_relative_to(tmp_path.resolve())
    assert manifest["patient_id"] == "..\\escape/patient"
    assert manifest["patient_path_segment"] != manifest["patient_id"]
    assert "\\" not in manifest["patient_path_segment"]
    assert "/" not in manifest["patient_path_segment"]
