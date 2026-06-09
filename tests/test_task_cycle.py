from pathlib import Path

from cdhai_june.analysis.basic import BasicAnalyzer
from cdhai_june.analysis.hypotheses import HypothesisPlanner, HypothesisTester
from cdhai_june.config import AnalysisConfig, ExternalConfig
from cdhai_june.data_loader import load_patient_dataset
from cdhai_june.llm import MockLLMClient
from cdhai_june.research import build_research_context
from cdhai_june.task_cycle import TaskCycleRunner


def test_task_cycle_creates_task_graph_and_gate(tmp_path: Path) -> None:
    dataset = load_patient_dataset(Path(__file__).parents[1] / "examples" / "sample_patient.csv")
    config = AnalysisConfig(max_narrative_cycles=1, output_dir=tmp_path, plot=False)
    basic_profile = BasicAnalyzer(config).run(dataset, tmp_path / "analysis")
    research_context = build_research_context(
        dataset=dataset,
        basic_profile=basic_profile,
        analysis_dir=tmp_path / "analysis",
        external_config=ExternalConfig(),
        analysis_config=config,
    )
    hypotheses = HypothesisPlanner(config).plan(
        cycle=1,
        dataset=dataset,
        basic_profile=basic_profile,
        kb_context={},
        llm_client=MockLLMClient(),
    )
    cycle_dir = tmp_path / "cycle_01"
    results = [HypothesisTester(config).test(dataset, hypothesis, cycle_dir) for hypothesis in hypotheses]

    payload = TaskCycleRunner(config).run(
        cycle=1,
        dataset=dataset,
        hypotheses=hypotheses,
        statistical_results=results,
        basic_profile=basic_profile,
        research_context=research_context,
        cycle_dir=cycle_dir,
    )

    assert payload["task_count"] >= 6
    assert payload["gate_decision"]["status"] == "ready_for_insight"
    assert {task["type"] for task in payload["tasks"]} >= {
        "literature_search",
        "feature_engineering",
        "statistical_analysis",
        "neural_network_train_predict",
        "visualization",
        "result_analysis",
    }
    assert (cycle_dir / "task_chain" / "task_graph.json").exists()
    assert (cycle_dir / "task_chain" / "gate_decision.json").exists()
    nn_task = next(task for task in payload["tasks"] if task["type"] == "neural_network_train_predict")
    assert Path(nn_task["artifacts"]["nn_metrics"]).exists()
