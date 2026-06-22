from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cdhai_june.config import AnalysisConfig, ExternalConfig
from cdhai_june.external.haipipe_toolkit import resolve_project_path
from cdhai_june.external.hapf import hapf_status
from cdhai_june.models import Hypothesis, PatientDataset, TestResult
from cdhai_june.utils import write_json


def build_research_context(
    *,
    dataset: PatientDataset,
    basic_profile: dict[str, Any],
    analysis_dir: Path,
    external_config: ExternalConfig,
    analysis_config: AnalysisConfig,
) -> dict[str, Any]:
    """Create paper-grade research scaffolding before narrative generation."""
    generated_at = _now()
    reference_manifest = _reference_manifest(generated_at)
    literature_matrix = _literature_matrix(reference_manifest)
    protocol = _research_protocol(dataset, basic_profile, analysis_config, reference_manifest)
    figure_index = build_figure_index(analysis_dir)
    skill_sources = _academic_skill_sources(external_config)
    integrity_checklist = _integrity_checklist()
    hapf_foundation = hapf_status(external_config, analysis_config.hapf).to_json()
    context = {
        "generated_at": generated_at,
        "academic_research_skills": skill_sources,
        "research_protocol": protocol,
        "literature_matrix": literature_matrix,
        "reference_manifest": reference_manifest,
        "figure_index": figure_index,
        "integrity_checklist": integrity_checklist,
        "cdhai_hapf": hapf_foundation,
    }
    write_json(analysis_dir / "research_protocol.json", protocol)
    write_json(analysis_dir / "literature_matrix.json", literature_matrix)
    write_json(analysis_dir / "reference_manifest.json", reference_manifest)
    write_json(analysis_dir / "figure_index.json", figure_index)
    write_json(analysis_dir / "research_integrity_checklist.json", integrity_checklist)
    write_json(analysis_dir / "research_context.json", context)
    return context


def build_figure_index(analysis_dir: Path) -> dict[str, Any]:
    figures = []
    for index, path in enumerate(sorted(analysis_dir.rglob("*.png")), start=1):
        figures.append(
            {
                "figure_id": f"fig{index:02d}",
                "title": _figure_title(path),
                "absolute_path": str(path.resolve()),
                "analysis_relative_path": path.relative_to(analysis_dir).as_posix(),
                "role": _figure_role(path),
            }
        )
    return {"count": len(figures), "figures": figures}


def build_cycle_research_review(
    *,
    cycle: int,
    hypotheses: list[Hypothesis],
    results: list[TestResult],
    research_context: dict[str, Any],
    cycle_dir: Path,
    analysis_config: AnalysisConfig,
    task_chain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cycle_dir.mkdir(parents=True, exist_ok=True)
    stats_rows = [_stat_row(result) for result in results]
    holm_rows = _holm_correction(stats_rows, analysis_config.hypothesis.alpha)
    references_by_family = _references_by_family(research_context)
    review = {
        "cycle": cycle,
        "generated_at": _now(),
        "alpha": analysis_config.hypothesis.alpha,
        "research_question_link": "RQ1/RQ2/RQ3/RQ4 depending on tested variables and model evidence.",
        "hypothesis_chain": [
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "statement": hypothesis.statement,
                "rationale": hypothesis.rationale,
                "variables": hypothesis.variables,
                "test_family": hypothesis.test_family,
                "reference_hooks": references_by_family.get(hypothesis.test_family, []),
            }
            for hypothesis in hypotheses
        ],
        "statistical_audit": {
            "rows": stats_rows,
            "holm_correction": holm_rows,
            "reporting_rules": [
                "Report n, method, exact p-value when available, and effect size for every supported/not-supported test.",
                "Treat skipped tests as evidence gaps, not negative evidence.",
                "Downgrade all single-patient findings to exploratory unless replicated on an external cohort.",
            ],
        },
        "ml_audit": {
            "baseline_source": "analysis/ml_prediction_metrics.json",
            "required_claim": "ML results are a triangulation baseline, not a validated clinical prediction model.",
            "personalization_task": "task_chain/personalized_forecasting",
            "personalization_claim": (
                "HAPF is exploratory cohort-to-patient adaptation evidence; deployment requires its calibration gate."
            ),
        },
        "task_cycle": task_chain or {},
        "visualization_audit": research_context.get("figure_index", {}),
        "claim_integrity_gate": {
            "allowed_references_only": [item["id"] for item in research_context.get("reference_manifest", {}).get("references", [])],
            "clinical_advice_disallowed": True,
            "unsupported_result_language": "Use 'not supported in this dataset' instead of 'no relationship exists'.",
            "minimum_cycle_sections": [
                "literature context",
                "hypothesis",
                "mechanistic reasoning",
                "mathematical/statistical formulation",
                "test result with effect size",
                "ML triangulation if relevant",
                "HAPF population-versus-personalized forecast evidence when configured",
                "limitations and next falsification step",
            ],
        },
    }
    write_json(cycle_dir / "research_cycle_review.json", review)
    return review


def _research_protocol(
    dataset: PatientDataset,
    basic_profile: dict[str, Any],
    analysis_config: AnalysisConfig,
    reference_manifest: dict[str, Any],
) -> dict[str, Any]:
    roles = dataset.column_roles
    cgm_available = bool(basic_profile.get("cgm", {}).get("available"))
    event_available = bool(basic_profile.get("events", {}).get("available"))
    ml_available = bool(basic_profile.get("ml_prediction", {}).get("available"))
    return {
        "title": "Single-patient CGM and behavior data research loop",
        "study_type": "Exploratory N-of-1 observational analysis with repeated computational probes.",
        "preregistration_note": (
            "Generated after data access for software testing; future real studies should preregister before outcome inspection."
        ),
        "data_status": {
            "patient_id": dataset.patient_id,
            "primary_table": dataset.primary_table,
            "row_count": int(len(dataset.primary)),
            "column_roles": roles,
            "cgm_available": cgm_available,
            "event_analysis_available": event_available,
            "ml_prediction_available": ml_available,
            "hapf_enabled": analysis_config.hapf.enabled,
            "hapf_cohort_configured": bool(analysis_config.hapf.cohort_data_path),
        },
        "research_questions": [
            {
                "id": "RQ1",
                "question": "What stable glucose distribution, time-in-range, variability, and daypart patterns are present?",
                "reference_ids": ["battelino_2019_tir", "danne_2017_cgm_consensus", "rodbard_2009_cgm_interpretation"],
            },
            {
                "id": "RQ2",
                "question": "Are recorded meals, carbohydrate amounts, activity, or medication proxies temporally associated with excursions?",
                "reference_ids": ["battelino_2019_tir", "ada_2026_glycemic_goals"],
            },
            {
                "id": "RQ3",
                "question": "Does a transparent time-aware model predict next glucose better than persistence?",
                "reference_ids": ["rodbard_2009_cgm_interpretation"],
            },
            {
                "id": "RQ4",
                "question": (
                    "Does subject-specific low-rank adaptation improve calibrated multi-horizon forecasting "
                    "over the population model without harming any configured horizon?"
                ),
                "reference_ids": [
                    "yang_2023_personalized_bg",
                    "daniels_2022_multitask_bg",
                    "li_2020_glunet",
                    "finn_2017_maml",
                    "hu_2022_lora",
                    "shamsian_2021_pfedhn",
                    "marquand_2016_normative",
                ],
            },
        ],
        "hypotheses": [
            {
                "id": "H1",
                "statement": "Mean/median glucose differs by daypart within this patient's observation window.",
                "test_family": "circadian_pattern",
                "falsification": "Kruskal-Wallis p >= alpha after correction or effect size near zero.",
            },
            {
                "id": "H2",
                "statement": "Higher recorded carbohydrate amount is associated with larger post-meal glucose peak delta.",
                "test_family": "meal_response",
                "falsification": "Spearman rho near zero, corrected p >= alpha, or insufficient aligned meal windows.",
            },
            {
                "id": "H3",
                "statement": "Activity-rich periods are associated with lower subsequent glucose delta.",
                "test_family": "exercise_response",
                "falsification": "Direction is nonnegative or corrected p >= alpha after windowed activity analysis.",
            },
            {
                "id": "H4",
                "statement": "A transparent next-glucose model improves MAE over a persistence baseline.",
                "test_family": "ml_prediction",
                "falsification": "Time-split MAE is not lower than persistence or the test split is too small.",
            },
            {
                "id": "H5",
                "statement": (
                    "HAPF patient adaptation reduces calibration RMSE relative to the population model "
                    "while remaining noninferior at every forecast horizon."
                ),
                "test_family": "personalized_forecasting",
                "falsification": (
                    "The preregistered relative-improvement threshold is not met, any horizon is inferior, "
                    "or subject-safe adaptation/calibration/test splits are insufficient."
                ),
            },
        ],
        "mathematical_formalization": {
            "glucose_series": "Let G_t be observed glucose in mg/dL at timestamp t.",
            "time_in_range": "TIR = 100 * mean(70 <= G_t <= 180).",
            "glycemic_variability": "CV = 100 * SD(G_t) / mean(G_t).",
            "meal_response": "Delta_meal = max(G_{t:t+180min}) - mean(G_{t-30min:t}).",
            "activity_response": "Delta_activity = mean(G_{t:t+180min}) - mean(G_{t-60min:t}).",
            "prediction_model": "G_{t+1} = beta_0 + beta_1 G_t + beta_2 sin(hour_t) + beta_3 cos(hour_t) + beta_k X_{k,t} + epsilon_t.",
            "hapf_adaptation": (
                "For population parameters theta and patient code z_i, use a low-rank update "
                "Delta W_i = A diag(z_i) B; accept personalization only when calibration RMSE "
                "improves by the configured margin and is noninferior at every horizon."
            ),
        },
        "statistical_analysis_plan": {
            "alpha": analysis_config.hypothesis.alpha,
            "multiple_testing": "Within-cycle Holm correction is emitted as an audit table; uncorrected p-values remain visible.",
            "effect_sizes": {
                "spearman": "rho",
                "kruskal_wallis": "epsilon-squared when group counts allow",
                "linear_trend": "r and R-squared",
                "prediction": "MAE/RMSE difference versus persistence baseline",
                "personalization": (
                    "Subject-held-out population/personalized/deployed RMSE by horizon, calibration relative "
                    "improvement, conformal interval coverage/width, and explicit fallback-gate decision"
                ),
            },
            "missing_data": "Report per-column missingness and treat missing event records as possible measurement bias.",
            "assumption_checks": [
                "Use non-parametric tests for small or non-normal within-patient windows.",
                "Report sample size for each test window.",
                "Do not infer causality from observational alignment.",
            ],
        },
        "visualization_plan": [
            "CGM trace with target range shading",
            "Mean glucose by hour",
            "Next-glucose observed-versus-predicted plot",
            "HAPF population-versus-personalized RMSE by forecast horizon",
            "Future cycle-specific event-response or residual plots",
        ],
        "reference_policy": {
            "citation_set": [item["id"] for item in reference_manifest.get("references", [])],
            "rule": "Reports may cite only reference ids in the manifest unless an external discovery step verifies a new source.",
        },
    }


def _reference_manifest(generated_at: str) -> dict[str, Any]:
    references = [
        {
            "id": "battelino_2019_tir",
            "authors": "Battelino et al.",
            "year": 2019,
            "title": "Clinical Targets for Continuous Glucose Monitoring Data Interpretation: Recommendations From the International Consensus on Time in Range",
            "venue": "Diabetes Care, 42(8), 1593-1603",
            "doi": "10.2337/dci19-0028",
            "url": "https://pubmed.ncbi.nlm.nih.gov/31177185/",
            "evidence_type": "international consensus report",
            "use_for": ["time-in-range thresholds", "CGM reporting metrics", "target-range terminology"],
            "verification_status": "web_verified_metadata",
        },
        {
            "id": "danne_2017_cgm_consensus",
            "authors": "Danne et al.",
            "year": 2017,
            "title": "International Consensus on Use of Continuous Glucose Monitoring",
            "venue": "Diabetes Care, 40(12), 1631-1640",
            "doi": "10.2337/dc17-1600",
            "url": "https://pubmed.ncbi.nlm.nih.gov/29162583/",
            "evidence_type": "international consensus report",
            "use_for": ["CGM use principles", "data sufficiency framing", "metric interpretation context"],
            "verification_status": "web_verified_metadata",
        },
        {
            "id": "ada_2026_glycemic_goals",
            "authors": "American Diabetes Association Professional Practice Committee for Diabetes",
            "year": 2026,
            "title": "Glycemic Goals, Hypoglycemia, and Hyperglycemic Crises: Standards of Care in Diabetes-2026",
            "venue": "Diabetes Care, 49(Supplement_1), S132-S149",
            "doi": "10.2337/dc26-S006",
            "url": "https://pubmed.ncbi.nlm.nih.gov/41358894/",
            "evidence_type": "clinical standards",
            "use_for": ["current guideline context", "individualized goals caution", "clinical boundary setting"],
            "verification_status": "web_verified_metadata",
        },
        {
            "id": "rodbard_2009_cgm_interpretation",
            "authors": "Rodbard",
            "year": 2009,
            "title": "Interpretation of Continuous Glucose Monitoring Data: Glycemic Variability and Quality of Glycemic Control",
            "venue": "Diabetes Technology & Therapeutics, 11(Suppl 1), S55-S67",
            "doi": "10.1089/dia.2008.0132",
            "url": "https://journals.sagepub.com/doi/10.1089/dia.2008.0132",
            "evidence_type": "methods review",
            "use_for": ["glycemic variability metrics", "CGM interpretation methods", "within-day and between-day framing"],
            "verification_status": "web_verified_metadata",
        },
        {
            "id": "clarke_1987_error_grid",
            "authors": "Clarke et al.",
            "year": 1987,
            "title": "Evaluating Clinical Accuracy of Systems for Self-Monitoring of Blood Glucose",
            "venue": "Diabetes Care, 10(5), 622-628",
            "doi": "10.2337/diacare.10.5.622",
            "url": "https://doi.org/10.2337/diacare.10.5.622",
            "evidence_type": "measurement evaluation method",
            "use_for": ["clinical accuracy framing when reference glucose is available"],
            "verification_status": "web_verified_metadata",
        },
        {
            "id": "parkes_2000_consensus_error_grid",
            "authors": "Parkes et al.",
            "year": 2000,
            "title": "A New Consensus Error Grid to Evaluate the Clinical Significance of Inaccuracies in the Measurement of Blood Glucose",
            "venue": "Diabetes Care, 23(8), 1143-1148",
            "doi": "10.2337/diacare.23.8.1143",
            "url": "https://pubmed.ncbi.nlm.nih.gov/10937512/",
            "evidence_type": "measurement evaluation method",
            "use_for": ["future sensor accuracy analyses with paired reference values"],
            "verification_status": "web_verified_metadata",
        },
        {
            "id": "yang_2023_personalized_bg",
            "authors": "Yang et al.",
            "year": 2023,
            "title": "Personalized Blood Glucose Prediction for Type 1 Diabetes Using Evidential Deep Learning and Meta-Learning",
            "venue": "IEEE Transactions on Biomedical Engineering, 70(1), 193-204",
            "doi": "10.1109/TBME.2022.3187703",
            "url": "https://pubmed.ncbi.nlm.nih.gov/35776825/",
            "evidence_type": "personalized forecasting method",
            "use_for": ["fast subject adaptation", "uncertainty-aware glucose prediction", "meta-learning comparator"],
            "verification_status": "hapf_primary_reference",
        },
        {
            "id": "daniels_2022_multitask_bg",
            "authors": "Daniels et al.",
            "year": 2022,
            "title": "A Multitask Learning Approach to Personalized Blood Glucose Prediction",
            "venue": "IEEE Journal of Biomedical and Health Informatics, 26(1), 436-445",
            "doi": "10.1109/JBHI.2021.3100558",
            "url": "https://pubmed.ncbi.nlm.nih.gov/34314367/",
            "evidence_type": "personalized forecasting method",
            "use_for": ["partial pooling", "multitask personalization", "limited patient-data adaptation"],
            "verification_status": "hapf_primary_reference",
        },
        {
            "id": "li_2020_glunet",
            "authors": "Li et al.",
            "year": 2020,
            "title": "GluNet: A Deep Learning Framework for Accurate Glucose Forecasting",
            "venue": "IEEE Journal of Biomedical and Health Informatics, 24(2), 414-423",
            "doi": "10.1109/JBHI.2019.2931842",
            "url": "https://pubmed.ncbi.nlm.nih.gov/31369390/",
            "evidence_type": "glucose forecasting architecture",
            "use_for": ["causal dilated convolution", "multi-horizon glucose forecasting", "backbone comparator"],
            "verification_status": "hapf_primary_reference",
        },
        {
            "id": "finn_2017_maml",
            "authors": "Finn, Abbeel, and Levine",
            "year": 2017,
            "title": "Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks",
            "venue": "Proceedings of the 34th International Conference on Machine Learning",
            "doi": None,
            "url": "https://proceedings.mlr.press/v70/finn17a.html",
            "evidence_type": "meta-learning method",
            "use_for": ["few-shot adaptation", "support-query evaluation", "personalization comparator"],
            "verification_status": "hapf_primary_reference",
        },
        {
            "id": "hu_2022_lora",
            "authors": "Hu et al.",
            "year": 2022,
            "title": "LoRA: Low-Rank Adaptation of Large Language Models",
            "venue": "International Conference on Learning Representations",
            "doi": None,
            "url": "https://openreview.net/forum?id=nZeVKeeFYf9",
            "evidence_type": "parameter-efficient adaptation method",
            "use_for": ["low-rank adaptation", "parameter-efficient patient state", "adapter design precedent"],
            "verification_status": "hapf_primary_reference",
        },
        {
            "id": "shamsian_2021_pfedhn",
            "authors": "Shamsian et al.",
            "year": 2021,
            "title": "Personalized Federated Learning using Hypernetworks",
            "venue": "Proceedings of the 38th International Conference on Machine Learning",
            "doi": None,
            "url": "https://proceedings.mlr.press/v139/shamsian21a.html",
            "evidence_type": "personalized learning method",
            "use_for": ["patient-conditioned parameters", "hypernetwork personalization", "cold-start comparator"],
            "verification_status": "hapf_primary_reference",
        },
        {
            "id": "marquand_2016_normative",
            "authors": "Marquand et al.",
            "year": 2016,
            "title": "Understanding Heterogeneity in Clinical Cohorts Using Normative Models: Beyond Case-Control Studies",
            "venue": "Biological Psychiatry, 80(7), 552-561",
            "doi": "10.1016/j.biopsych.2015.12.023",
            "url": "https://doi.org/10.1016/j.biopsych.2015.12.023",
            "evidence_type": "normative modeling framework",
            "use_for": ["individual deviation modeling", "cohort heterogeneity", "personalized reference distributions"],
            "verification_status": "hapf_primary_reference",
        },
    ]
    return {
        "generated_at": generated_at,
        "verification_note": (
            "CGM metadata was seeded from web-verified records on 2026-06-07; HAPF references "
            "were imported from its primary-source literature manifest on 2026-06-21. "
            "Publication-grade manuscripts should re-run citation verification before submission."
        ),
        "references": references,
    }


def _literature_matrix(reference_manifest: dict[str, Any]) -> dict[str, Any]:
    themes = [
        "CGM metrics and time-in-range",
        "Data sufficiency and missingness",
        "Glycemic variability",
        "Clinical accuracy and measurement risk",
        "Individualized clinical context",
        "Personalized forecasting and adaptation",
    ]
    rows = []
    theme_map = {
        "battelino_2019_tir": ["supports", "supports", "partial", "not_addressed", "supports", "partial"],
        "danne_2017_cgm_consensus": ["supports", "supports", "partial", "not_addressed", "supports", "partial"],
        "ada_2026_glycemic_goals": ["supports", "partial", "partial", "not_addressed", "supports", "partial"],
        "rodbard_2009_cgm_interpretation": ["supports", "partial", "supports", "not_addressed", "partial", "partial"],
        "clarke_1987_error_grid": ["not_addressed", "not_addressed", "not_addressed", "supports", "partial", "not_addressed"],
        "parkes_2000_consensus_error_grid": ["not_addressed", "not_addressed", "not_addressed", "supports", "partial", "not_addressed"],
        "yang_2023_personalized_bg": ["partial", "partial", "partial", "not_addressed", "supports", "supports"],
        "daniels_2022_multitask_bg": ["partial", "partial", "partial", "not_addressed", "supports", "supports"],
        "li_2020_glunet": ["partial", "partial", "partial", "not_addressed", "partial", "supports"],
        "finn_2017_maml": ["not_addressed", "not_addressed", "not_addressed", "not_addressed", "partial", "supports"],
        "hu_2022_lora": ["not_addressed", "not_addressed", "not_addressed", "not_addressed", "partial", "supports"],
        "shamsian_2021_pfedhn": ["not_addressed", "not_addressed", "not_addressed", "not_addressed", "supports", "supports"],
        "marquand_2016_normative": ["not_addressed", "partial", "partial", "not_addressed", "supports", "supports"],
    }
    for ref in reference_manifest.get("references", []):
        rows.append(
            {
                "source_id": ref["id"],
                "year": ref["year"],
                "evidence_type": ref["evidence_type"],
                "theme_alignment": dict(zip(themes, theme_map.get(ref["id"], []), strict=False)),
            }
        )
    return {
        "template_source": "external/academic-research-skills/deep-research/templates/literature_matrix_template.md",
        "themes": themes,
        "rows": rows,
        "gaps": [
            "No external cohort validation has been run in this project scaffold yet.",
            "No paired laboratory or reference-meter glucose values are available for sensor accuracy grids.",
            "Single-patient observational data cannot establish causal meal or activity effects.",
            "HAPF remains exploratory until nested subject-level validation and comparator ablations are complete.",
        ],
    }


def _academic_skill_sources(config: ExternalConfig) -> dict[str, Any]:
    base = resolve_project_path(config.academic_research_skills_path)
    relative_sources = [
        "academic-pipeline/SKILL.md",
        "deep-research/templates/literature_matrix_template.md",
        "deep-research/templates/preregistration_template.md",
        "academic-paper/templates/imrad_template.md",
        "academic-paper-reviewer/references/statistical_reporting_standards.md",
    ]
    return {
        "name": "academic-research-skills",
        "url": config.academic_research_skills_url,
        "path": str(base),
        "present": base.exists(),
        "used_sources": [
            {
                "relative_path": item,
                "present": (base / item).exists(),
                "absolute_path": str((base / item).resolve()),
            }
            for item in relative_sources
        ],
        "adaptation": "Converted the general research-to-paper workflow into per-cycle patient-data research gates.",
    }


def _integrity_checklist() -> dict[str, Any]:
    return {
        "cycle_required_sections": [
            "literature review and reference hooks",
            "explicit hypothesis and falsification criterion",
            "mechanistic reasoning stated as hypothesis, not fact",
            "mathematical/statistical formulation",
            "deterministic test result with n, p-value where available, and effect size",
            "ML prediction baseline or reason it is not applicable",
            "HAPF population/personalized/deployed forecast comparison or a structured readiness gap",
            "visualization references",
            "limitations, missingness, and next-step probe",
        ],
        "blocking_rules": [
            "No unsupported clinical advice.",
            "No citation outside reference_manifest without external verification.",
            "No causal language from observational single-patient association.",
            "No hidden model-generated code execution.",
        ],
    }


def _stat_row(result: TestResult) -> dict[str, Any]:
    p_value = _extract_p_value(result.metrics)
    effect = _extract_effect_size(result)
    return {
        "hypothesis_id": result.hypothesis_id,
        "method": result.method,
        "status": result.status,
        "summary": result.summary,
        "n": _extract_n(result.metrics),
        "p_value": p_value,
        "effect_size": effect,
        "has_complete_reporting": bool(result.status == "skipped" or effect or result.method == "missingness_pattern"),
    }


def _extract_p_value(metrics: dict[str, Any]) -> float | None:
    if isinstance(metrics.get("p_value"), (int, float)):
        return float(metrics["p_value"])
    spearman = metrics.get("spearman")
    if isinstance(spearman, dict) and isinstance(spearman.get("p_value"), (int, float)):
        return float(spearman["p_value"])
    top_pairs = metrics.get("top_pairs")
    if isinstance(top_pairs, list) and top_pairs and isinstance(top_pairs[0].get("p_value"), (int, float)):
        return float(top_pairs[0]["p_value"])
    return None


def _extract_n(metrics: dict[str, Any]) -> int | None:
    for key in ("n", "n_events", "total_n"):
        if isinstance(metrics.get(key), int):
            return int(metrics[key])
    spearman = metrics.get("spearman")
    if isinstance(spearman, dict) and isinstance(spearman.get("n"), int):
        return int(spearman["n"])
    top_pairs = metrics.get("top_pairs")
    if isinstance(top_pairs, list) and top_pairs and isinstance(top_pairs[0].get("n"), int):
        return int(top_pairs[0]["n"])
    return None


def _extract_effect_size(result: TestResult) -> dict[str, Any] | None:
    metrics = result.metrics
    spearman = metrics.get("spearman")
    if isinstance(spearman, dict) and isinstance(spearman.get("rho"), (int, float)):
        return {"metric": "spearman_rho", "value": float(spearman["rho"])}
    if result.method == "numeric_correlation":
        pairs = metrics.get("top_pairs")
        if isinstance(pairs, list) and pairs and isinstance(pairs[0].get("rho"), (int, float)):
            return {"metric": "spearman_rho", "value": float(pairs[0]["rho"])}
    if isinstance(metrics.get("epsilon_squared"), (int, float)):
        return {"metric": "epsilon_squared", "value": float(metrics["epsilon_squared"])}
    if isinstance(metrics.get("r_squared"), (int, float)):
        return {"metric": "r_squared", "value": float(metrics["r_squared"])}
    return None


def _holm_correction(rows: list[dict[str, Any]], alpha: float) -> list[dict[str, Any]]:
    p_rows = [row for row in rows if isinstance(row.get("p_value"), float)]
    p_rows.sort(key=lambda row: row["p_value"])
    output = []
    still_rejecting = True
    m = len(p_rows)
    for rank, row in enumerate(p_rows, start=1):
        threshold = alpha / (m - rank + 1)
        reject = bool(still_rejecting and row["p_value"] <= threshold)
        if not reject:
            still_rejecting = False
        output.append(
            {
                "hypothesis_id": row["hypothesis_id"],
                "rank": rank,
                "p_value": row["p_value"],
                "holm_threshold": threshold,
                "reject_after_holm": reject,
            }
        )
    return output


def _references_by_family(research_context: dict[str, Any]) -> dict[str, list[str]]:
    del research_context
    return {
        "circadian_pattern": ["battelino_2019_tir", "rodbard_2009_cgm_interpretation"],
        "meal_response": ["battelino_2019_tir", "ada_2026_glycemic_goals"],
        "exercise_response": ["battelino_2019_tir", "ada_2026_glycemic_goals"],
        "daily_trend": ["rodbard_2009_cgm_interpretation"],
        "numeric_correlation": ["rodbard_2009_cgm_interpretation"],
        "missingness_pattern": ["danne_2017_cgm_consensus"],
        "ml_prediction": ["rodbard_2009_cgm_interpretation"],
        "personalized_forecasting": [
            "yang_2023_personalized_bg",
            "daniels_2022_multitask_bg",
            "li_2020_glunet",
            "finn_2017_maml",
            "hu_2022_lora",
            "shamsian_2021_pfedhn",
            "marquand_2016_normative",
        ],
    }


def _figure_title(path: Path) -> str:
    titles = {
        "cgm_trace": "CGM trace with target range",
        "cgm_hourly_profile": "Mean glucose by hour",
        "ml_next_glucose_prediction": "Next-glucose prediction validation",
    }
    return titles.get(path.stem, path.stem.replace("_", " ").title())


def _figure_role(path: Path) -> str:
    if path.stem.startswith("cgm"):
        return "descriptive_cgm"
    if path.stem.startswith("ml"):
        return "prediction_validation"
    return "analysis_visualization"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
