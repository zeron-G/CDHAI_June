from pathlib import Path

from cdhai_june.analysis.basic import BasicAnalyzer
from cdhai_june.config import AnalysisConfig, ExternalConfig
from cdhai_june.data_loader import load_patient_dataset
from cdhai_june.research import build_research_context


def test_research_context_emits_protocol_references_and_figures(tmp_path: Path) -> None:
    dataset = load_patient_dataset(Path(__file__).parents[1] / "examples" / "sample_patient.csv")
    profile = BasicAnalyzer(AnalysisConfig(plot=True)).run(dataset, tmp_path)

    context = build_research_context(
        dataset=dataset,
        basic_profile=profile,
        analysis_dir=tmp_path,
        external_config=ExternalConfig(),
        analysis_config=AnalysisConfig(plot=True),
    )

    assert context["research_protocol"]["hypotheses"]
    assert len(context["reference_manifest"]["references"]) >= 5
    assert context["figure_index"]["count"] >= 3
    assert (tmp_path / "research_context.json").exists()
