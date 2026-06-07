from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        default = match.group(2) or ""
        return os.environ.get(name, default)

    return _ENV_PATTERN.sub(replace, value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _as_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


@dataclass(slots=True)
class CGMThresholds:
    low_mgdl: float = 70.0
    very_low_mgdl: float = 54.0
    target_low_mgdl: float = 70.0
    target_high_mgdl: float = 180.0
    very_high_mgdl: float = 250.0


@dataclass(slots=True)
class HypothesisConfig:
    max_per_cycle: int = 3
    alpha: float = 0.05


@dataclass(slots=True)
class AnalysisConfig:
    max_narrative_cycles: int = 5
    output_dir: Path = Path("runs")
    timezone: str = "America/New_York"
    min_numeric_non_null: int = 5
    plot: bool = True
    cgm: CGMThresholds = field(default_factory=CGMThresholds)
    hypothesis: HypothesisConfig = field(default_factory=HypothesisConfig)


@dataclass(slots=True)
class LLMConfig:
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_output_tokens: int = 1800
    codex_auth_path: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""


@dataclass(slots=True)
class ExternalConfig:
    welldoc_space_path: Path = Path("../WellDoc-SPACE")
    tools_path: Path = Path("../WellDoc-SPACE/Tools")
    codex_oauth_package_path: Path = Path("../HAI-Agent/packages/codex-oauth")


@dataclass(slots=True)
class DatabaseConfig:
    ssh_host: str = "10.175.198.65"
    ssh_user: str = "rgao28"
    ssh_port: int = 22
    ssh_key_path: str = ""
    tunnel_local_port: int = 15432
    remote_host: str = "127.0.0.1"
    remote_port: int = 5432
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""


@dataclass(slots=True)
class AppConfig:
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    external: ExternalConfig = field(default_factory=ExternalConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


def _load_raw_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _build_analysis_config(raw: dict[str, Any]) -> AnalysisConfig:
    cgm_raw = raw.get("cgm", {}) or {}
    hyp_raw = raw.get("hypothesis", {}) or {}
    return AnalysisConfig(
        max_narrative_cycles=_as_int(raw.get("max_narrative_cycles"), 5),
        output_dir=Path(str(raw.get("output_dir", "runs"))),
        timezone=str(raw.get("timezone", "America/New_York")),
        min_numeric_non_null=_as_int(raw.get("min_numeric_non_null"), 5),
        plot=_as_bool(raw.get("plot", True)),
        cgm=CGMThresholds(
            low_mgdl=_as_float(cgm_raw.get("low_mgdl"), 70.0),
            very_low_mgdl=_as_float(cgm_raw.get("very_low_mgdl"), 54.0),
            target_low_mgdl=_as_float(cgm_raw.get("target_low_mgdl"), 70.0),
            target_high_mgdl=_as_float(cgm_raw.get("target_high_mgdl"), 180.0),
            very_high_mgdl=_as_float(cgm_raw.get("very_high_mgdl"), 250.0),
        ),
        hypothesis=HypothesisConfig(
            max_per_cycle=_as_int(hyp_raw.get("max_per_cycle"), 3),
            alpha=_as_float(hyp_raw.get("alpha"), 0.05),
        ),
    )


def _build_llm_config(raw: dict[str, Any]) -> LLMConfig:
    return LLMConfig(
        provider=str(raw.get("provider", "mock")).strip() or "mock",
        model=str(raw.get("model", "gpt-4o-mini")).strip() or "gpt-4o-mini",
        temperature=_as_float(raw.get("temperature"), 0.2),
        max_output_tokens=_as_int(raw.get("max_output_tokens"), 1800),
        codex_auth_path=str(raw.get("codex_auth_path", "")),
        openai_base_url=str(raw.get("openai_base_url", "https://api.openai.com/v1")),
        openai_api_key=str(raw.get("openai_api_key", "")),
    )


def _build_external_config(raw: dict[str, Any]) -> ExternalConfig:
    return ExternalConfig(
        welldoc_space_path=Path(str(raw.get("welldoc_space_path", "../WellDoc-SPACE"))),
        tools_path=Path(str(raw.get("tools_path", "../WellDoc-SPACE/Tools"))),
        codex_oauth_package_path=Path(str(raw.get("codex_oauth_package_path", "../HAI-Agent/packages/codex-oauth"))),
    )


def _build_database_config(raw: dict[str, Any]) -> DatabaseConfig:
    return DatabaseConfig(
        ssh_host=str(raw.get("ssh_host", "10.175.198.65")),
        ssh_user=str(raw.get("ssh_user", "rgao28")),
        ssh_port=_as_int(raw.get("ssh_port"), 22),
        ssh_key_path=str(raw.get("ssh_key_path", "")),
        tunnel_local_port=_as_int(raw.get("tunnel_local_port"), 15432),
        remote_host=str(raw.get("remote_host", "127.0.0.1")),
        remote_port=_as_int(raw.get("remote_port"), 5432),
        db_name=str(raw.get("db_name", "")),
        db_user=str(raw.get("db_user", "")),
        db_password=str(raw.get("db_password", "")),
    )


def load_config(path: str | Path | None = None) -> AppConfig:
    raw = _expand_env(_load_raw_config(Path(path) if path else None))
    return AppConfig(
        analysis=_build_analysis_config(raw.get("analysis", {}) or {}),
        llm=_build_llm_config(raw.get("llm", {}) or {}),
        external=_build_external_config(raw.get("external", {}) or {}),
        database=_build_database_config(raw.get("database", {}) or {}),
    )

