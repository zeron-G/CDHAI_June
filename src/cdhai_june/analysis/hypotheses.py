from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from cdhai_june.config import AnalysisConfig
from cdhai_june.models import Hypothesis, PatientDataset, TestResult
from cdhai_june.utils import compact_text, write_json


class HypothesisPlanner:
    def __init__(self, config: AnalysisConfig) -> None:
        self.config = config

    def plan(
        self,
        *,
        cycle: int,
        dataset: PatientDataset,
        basic_profile: dict[str, Any],
        kb_context: dict[str, Any],
        llm_client: Any,
    ) -> list[Hypothesis]:
        llm_hypotheses = self._try_llm_plan(
            cycle=cycle,
            dataset=dataset,
            basic_profile=basic_profile,
            kb_context=kb_context,
            llm_client=llm_client,
        )
        if llm_hypotheses:
            return llm_hypotheses[: self.config.hypothesis.max_per_cycle]
        return self._deterministic_plan(cycle, dataset, basic_profile)[: self.config.hypothesis.max_per_cycle]

    def _try_llm_plan(
        self,
        *,
        cycle: int,
        dataset: PatientDataset,
        basic_profile: dict[str, Any],
        kb_context: dict[str, Any],
        llm_client: Any,
    ) -> list[Hypothesis]:
        if getattr(llm_client, "provider_name", "mock") == "mock":
            return []
        prompt = {
            "task": "Propose patient-data hypotheses as JSON only.",
            "cycle": cycle,
            "patient_id": dataset.patient_id,
            "column_roles": dataset.column_roles,
            "basic_profile_brief": compact_text(json.dumps(basic_profile, default=str), 5000),
            "recent_kb_context": kb_context,
            "allowed_test_families": [
                "meal_response",
                "exercise_response",
                "circadian_pattern",
                "daily_trend",
                "numeric_correlation",
                "missingness_pattern",
            ],
            "schema": [
                {
                    "statement": "plain-language hypothesis",
                    "rationale": "why this is worth testing",
                    "variables": ["column_a", "column_b"],
                    "test_family": "one allowed family",
                    "priority": 1,
                }
            ],
        }
        try:
            text = llm_client.generate(
                system="You are a careful biomedical data analyst. Return strict JSON without markdown.",
                prompt=json.dumps(prompt, default=str),
            )
            payload = _extract_json(text)
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        hypotheses: list[Hypothesis] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            family = str(item.get("test_family", "")).strip()
            if family not in HypothesisTester.ALLOWED_METHODS:
                continue
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"c{cycle:02d}-llm-{index:02d}",
                    statement=str(item.get("statement", "")).strip() or "LLM proposed hypothesis",
                    rationale=str(item.get("rationale", "")).strip(),
                    variables=[str(value) for value in item.get("variables", []) if str(value).strip()],
                    test_family=family,
                    cycle=cycle,
                    priority=int(item.get("priority", index)),
                    source="llm",
                )
            )
        return hypotheses

    def _deterministic_plan(
        self,
        cycle: int,
        dataset: PatientDataset,
        basic_profile: dict[str, Any],
    ) -> list[Hypothesis]:
        del basic_profile
        roles = dataset.column_roles
        glucose = roles.get("glucose")
        time_col = roles.get("timestamp")
        carbs = roles.get("carbs")
        exercise = roles.get("exercise") or roles.get("steps")
        hypotheses: list[Hypothesis] = []

        if glucose and time_col:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"c{cycle:02d}-circadian",
                    statement="Glucose varies by time of day for this patient.",
                    rationale="A circadian pattern can guide when future reports should inspect meals, exercise, and medication timing.",
                    variables=[time_col, glucose],
                    test_family="circadian_pattern",
                    cycle=cycle,
                    priority=1,
                )
            )
        if glucose and carbs:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"c{cycle:02d}-meal",
                    statement="Higher carbohydrate meal entries are associated with larger post-meal glucose rises.",
                    rationale="Meal response is a central patient-facing explanation target in the architecture sketch.",
                    variables=[carbs, glucose],
                    test_family="meal_response",
                    cycle=cycle,
                    priority=2,
                )
            )
        if glucose and exercise:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"c{cycle:02d}-exercise",
                    statement="Exercise or step-rich periods are associated with lower subsequent glucose.",
                    rationale="Activity is a likely behavioral modifier and should be checked before making meal-only claims.",
                    variables=[exercise, glucose],
                    test_family="exercise_response",
                    cycle=cycle,
                    priority=3,
                )
            )

        hypotheses.append(
            Hypothesis(
                hypothesis_id=f"c{cycle:02d}-missing",
                statement="Missingness or data gaps may cluster in specific columns or times.",
                rationale="Data quality can explain weak or misleading downstream findings.",
                variables=list(dataset.primary.columns),
                test_family="missingness_pattern",
                cycle=cycle,
                priority=4,
            )
        )

        numeric_columns = list(dataset.primary.select_dtypes(include="number").columns)
        if len(numeric_columns) >= 2:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"c{cycle:02d}-numeric",
                    statement="The strongest numeric relationships may reveal patient-specific behavioral or sensor patterns.",
                    rationale="This broad scan can surface relationships not covered by named CGM, meal, or activity probes.",
                    variables=numeric_columns,
                    test_family="numeric_correlation",
                    cycle=cycle,
                    priority=5,
                )
            )

        offset = (cycle - 1) % max(1, len(hypotheses))
        return hypotheses[offset:] + hypotheses[:offset]


class HypothesisTester:
    ALLOWED_METHODS = {
        "meal_response",
        "exercise_response",
        "circadian_pattern",
        "daily_trend",
        "numeric_correlation",
        "missingness_pattern",
    }

    def __init__(self, config: AnalysisConfig) -> None:
        self.config = config

    def test(self, dataset: PatientDataset, hypothesis: Hypothesis, cycle_dir: Path) -> TestResult:
        cycle_dir.mkdir(parents=True, exist_ok=True)
        family = hypothesis.test_family
        if family == "meal_response":
            return self._meal_response(dataset, hypothesis)
        if family == "exercise_response":
            return self._exercise_response(dataset, hypothesis)
        if family == "circadian_pattern":
            return self._circadian_pattern(dataset, hypothesis)
        if family == "daily_trend":
            return self._daily_trend(dataset, hypothesis)
        if family == "numeric_correlation":
            return self._numeric_correlation(dataset, hypothesis)
        if family == "missingness_pattern":
            return self._missingness_pattern(dataset, hypothesis)
        return TestResult(
            hypothesis_id=hypothesis.hypothesis_id,
            method=family,
            status="skipped",
            summary=f"Unsupported test family: {family}",
        )

    def _meal_response(self, dataset: PatientDataset, hypothesis: Hypothesis) -> TestResult:
        event_metrics = self._event_metrics(dataset).get("meal_response", {})
        if not event_metrics.get("available"):
            return _skipped(hypothesis, "meal_response", str(event_metrics.get("reason", "No meal response data.")))
        spearman = event_metrics.get("spearman")
        if spearman and spearman.get("rho") is not None:
            summary = (
                f"Meal response windows found n={event_metrics.get('n_events')}; "
                f"carb-vs-peak Spearman rho={spearman['rho']:.3f}, p={spearman['p_value']:.4g}."
            )
            status = _status_from_p(spearman.get("p_value"), self.config.hypothesis.alpha)
        else:
            summary = (
                f"Meal response windows found n={event_metrics.get('n_events')}; "
                f"mean post-meal delta={event_metrics.get('mean_delta_mgdl')} mg/dL."
            )
            status = "descriptive"
        return TestResult(hypothesis.hypothesis_id, "meal_response", status, summary, event_metrics)

    def _exercise_response(self, dataset: PatientDataset, hypothesis: Hypothesis) -> TestResult:
        event_metrics = self._event_metrics(dataset).get("exercise_response", {})
        if not event_metrics.get("available"):
            return _skipped(hypothesis, "exercise_response", str(event_metrics.get("reason", "No exercise response data.")))
        spearman = event_metrics.get("spearman")
        if spearman and spearman.get("rho") is not None:
            summary = (
                f"Exercise windows found n={event_metrics.get('n_events')}; "
                f"activity-vs-glucose-change Spearman rho={spearman['rho']:.3f}, p={spearman['p_value']:.4g}."
            )
            status = _status_from_p(spearman.get("p_value"), self.config.hypothesis.alpha)
        else:
            summary = (
                f"Exercise windows found n={event_metrics.get('n_events')}; "
                f"mean subsequent delta={event_metrics.get('mean_delta_mgdl')} mg/dL."
            )
            status = "descriptive"
        return TestResult(hypothesis.hypothesis_id, "exercise_response", status, summary, event_metrics)

    def _circadian_pattern(self, dataset: PatientDataset, hypothesis: Hypothesis) -> TestResult:
        df = dataset.primary.copy()
        time_col = dataset.column_roles.get("timestamp")
        glucose_col = dataset.column_roles.get("glucose")
        if not time_col or not glucose_col or time_col not in df or glucose_col not in df:
            return _skipped(hypothesis, "circadian_pattern", "Need timestamp and glucose columns.")
        if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
            return _skipped(hypothesis, "circadian_pattern", "Timestamp column is not datetime.")
        df[glucose_col] = pd.to_numeric(df[glucose_col], errors="coerce")
        df = df.dropna(subset=[time_col, glucose_col]).copy()
        if len(df) < 8:
            return _skipped(hypothesis, "circadian_pattern", "Not enough CGM rows.")
        df["daypart"] = pd.cut(
            df[time_col].dt.hour,
            bins=[-1, 5, 11, 17, 23],
            labels=["overnight", "morning", "afternoon", "evening"],
        )
        groups = [group[glucose_col].astype(float).values for _, group in df.groupby("daypart", observed=False) if len(group) >= 2]
        by_part = df.groupby("daypart", observed=False)[glucose_col].agg(["count", "mean", "median"]).reset_index()
        if len(groups) < 2:
            return _skipped(hypothesis, "circadian_pattern", "Need at least two populated dayparts.")
        stat, p_value = stats.kruskal(*groups)
        total_n = int(sum(len(group) for group in groups))
        group_count = int(len(groups))
        epsilon_squared = None
        if total_n > group_count:
            epsilon_squared = max(0.0, float((stat - group_count + 1) / (total_n - group_count)))
        metrics = {
            "test": "Kruskal-Wallis by daypart",
            "statistic": float(stat),
            "p_value": float(p_value),
            "total_n": total_n,
            "group_count": group_count,
            "epsilon_squared": epsilon_squared,
            "daypart_summary": by_part.to_dict(orient="records"),
        }
        status = _status_from_p(p_value, self.config.hypothesis.alpha)
        summary = f"Daypart glucose difference Kruskal-Wallis H={stat:.3f}, p={p_value:.4g}."
        return TestResult(hypothesis.hypothesis_id, "circadian_pattern", status, summary, metrics)

    def _daily_trend(self, dataset: PatientDataset, hypothesis: Hypothesis) -> TestResult:
        df = dataset.primary.copy()
        time_col = dataset.column_roles.get("timestamp")
        glucose_col = dataset.column_roles.get("glucose")
        if not time_col or not glucose_col or time_col not in df or glucose_col not in df:
            return _skipped(hypothesis, "daily_trend", "Need timestamp and glucose columns.")
        df[glucose_col] = pd.to_numeric(df[glucose_col], errors="coerce")
        df = df.dropna(subset=[time_col, glucose_col]).copy()
        if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
            return _skipped(hypothesis, "daily_trend", "Timestamp column is not datetime.")
        daily = df.groupby(df[time_col].dt.date)[glucose_col].mean().reset_index(name="mean_glucose")
        if len(daily) < 3:
            return _skipped(hypothesis, "daily_trend", "Need at least three days.")
        x = np.arange(len(daily))
        slope, intercept, r_value, p_value, stderr = stats.linregress(x, daily["mean_glucose"])
        metrics = {
            "slope_mgdl_per_day": float(slope),
            "intercept": float(intercept),
            "r_value": float(r_value),
            "r_squared": float(r_value**2),
            "p_value": float(p_value),
            "stderr": float(stderr),
            "daily": daily.assign(date=daily[time_col].astype(str)).drop(columns=[time_col]).to_dict(orient="records"),
        }
        status = _status_from_p(p_value, self.config.hypothesis.alpha)
        summary = f"Daily mean glucose trend slope={slope:.3f} mg/dL/day, p={p_value:.4g}."
        return TestResult(hypothesis.hypothesis_id, "daily_trend", status, summary, metrics)

    def _numeric_correlation(self, dataset: PatientDataset, hypothesis: Hypothesis) -> TestResult:
        df = dataset.primary.select_dtypes(include="number").copy()
        if df.shape[1] < 2:
            return _skipped(hypothesis, "numeric_correlation", "Need at least two numeric columns.")
        rows = []
        columns = list(df.columns)
        for i, left in enumerate(columns):
            for right in columns[i + 1 :]:
                joined = df[[left, right]].dropna()
                if len(joined) < self.config.min_numeric_non_null:
                    continue
                if joined[left].nunique() < 2 or joined[right].nunique() < 2:
                    continue
                rho, p_value = stats.spearmanr(joined[left], joined[right])
                if np.isnan(rho):
                    continue
                rows.append(
                    {
                        "left": str(left),
                        "right": str(right),
                        "rho": float(rho),
                        "p_value": float(p_value),
                        "n": int(len(joined)),
                    }
                )
        rows.sort(key=lambda row: abs(row["rho"]), reverse=True)
        if not rows:
            return _skipped(hypothesis, "numeric_correlation", "No valid numeric pairs.")
        strongest = rows[0]
        status = _status_from_p(strongest.get("p_value"), self.config.hypothesis.alpha)
        summary = (
            f"Strongest numeric Spearman pair: {strongest['left']} vs {strongest['right']} "
            f"rho={strongest['rho']:.3f}, p={strongest['p_value']:.4g}, n={strongest['n']}."
        )
        return TestResult(hypothesis.hypothesis_id, "numeric_correlation", status, summary, {"top_pairs": rows[:20]})

    def _missingness_pattern(self, dataset: PatientDataset, hypothesis: Hypothesis) -> TestResult:
        df = dataset.primary
        rows = []
        for column in df.columns:
            count = int(df[column].isna().sum())
            if count:
                rows.append({"column": str(column), "missing_count": count, "missing_pct": float(count / max(len(df), 1) * 100)})
        rows.sort(key=lambda row: row["missing_pct"], reverse=True)
        if not rows:
            return TestResult(
                hypothesis.hypothesis_id,
                "missingness_pattern",
                "descriptive",
                "No missing values were detected in the primary table.",
                {"missing_columns": []},
            )
        top = rows[0]
        summary = f"Highest missingness: {top['column']} at {top['missing_pct']:.1f}% ({top['missing_count']} rows)."
        return TestResult(hypothesis.hypothesis_id, "missingness_pattern", "descriptive", summary, {"missing_columns": rows})

    @staticmethod
    def _event_metrics(dataset: PatientDataset) -> dict[str, Any]:
        from tempfile import TemporaryDirectory

        from cdhai_june.analysis.events import analyze_events
        from cdhai_june.config import AnalysisConfig

        with TemporaryDirectory() as temp_dir:
            return analyze_events(dataset, AnalysisConfig(plot=False), Path(temp_dir))


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([idx for idx in (text.find("["), text.find("{")) if idx >= 0], default=-1)
        end = max(text.rfind("]"), text.rfind("}"))
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _status_from_p(p_value: Any, alpha: float) -> str:
    if p_value is None:
        return "descriptive"
    try:
        return "supported" if float(p_value) < alpha else "not_supported"
    except (TypeError, ValueError):
        return "descriptive"


def _skipped(hypothesis: Hypothesis, method: str, reason: str) -> TestResult:
    return TestResult(
        hypothesis_id=hypothesis.hypothesis_id,
        method=method,
        status="skipped",
        summary=reason,
        metrics={"reason": reason},
    )


def write_cycle_payload(cycle_dir: Path, hypotheses: list[Hypothesis], results: list[TestResult]) -> None:
    write_json(cycle_dir / "hypotheses.json", [hypothesis.to_json() for hypothesis in hypotheses])
    write_json(cycle_dir / "test_results.json", [result.to_json() for result in results])
