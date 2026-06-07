from pathlib import Path

from cdhai_june.analysis.basic import BasicAnalyzer
from cdhai_june.config import AnalysisConfig
from cdhai_june.data_loader import load_patient_dataset


def test_basic_analysis_detects_cgm_and_events(tmp_path: Path) -> None:
    dataset = load_patient_dataset(Path(__file__).parents[1] / "examples" / "sample_patient.csv")
    profile = BasicAnalyzer(AnalysisConfig(plot=False)).run(dataset, tmp_path)

    assert profile["patient_id"] == "demo"
    assert profile["cgm"]["available"] is True
    assert profile["cgm"]["n_readings"] == 36
    assert profile["events"]["available"] is True
    assert profile["events"]["meal_response"]["available"] is True

