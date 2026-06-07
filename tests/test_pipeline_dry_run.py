from pathlib import Path

from cdhai_june.config import AppConfig, AnalysisConfig, LLMConfig
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
    assert len(manifest["cycle_reports"]) == 2

