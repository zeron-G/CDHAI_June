from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from cdhai_june.config import ExternalConfig
from cdhai_june.external.haipipe_toolkit import resolve_project_path


@dataclass(slots=True)
class FoundationStatus:
    name: str
    role: str
    url: str
    path: str
    present: bool
    installable_package: str | None = None
    installed: bool | None = None
    module_origin: str | None = None
    install_hint: str | None = None

    def to_json(self) -> dict[str, str | bool | None]:
        return {
            "name": self.name,
            "role": self.role,
            "url": self.url,
            "path": self.path,
            "present": self.present,
            "installable_package": self.installable_package,
            "installed": self.installed,
            "module_origin": self.module_origin,
            "install_hint": self.install_hint,
        }


def _package_status(
    *,
    name: str,
    role: str,
    url: str,
    path: Path,
    module_name: str,
    install_hint: str,
) -> FoundationStatus:
    resolved = resolve_project_path(path)
    spec = find_spec(module_name)
    return FoundationStatus(
        name=name,
        role=role,
        url=url,
        path=str(resolved),
        present=resolved.exists(),
        installable_package=module_name.replace("_", "-"),
        installed=spec is not None,
        module_origin=spec.origin if spec else None,
        install_hint=install_hint,
    )


def foundational_dependency_statuses(config: ExternalConfig) -> dict[str, dict[str, str | bool | None]]:
    tools_path = resolve_project_path(config.tools_path)
    statuses = {
        "haipipe_toolkit": _package_status(
            name="haipipe_toolkit",
            role="Health AI data/model pipeline substrate and WellDoc-compatible patient records.",
            url=config.haipipe_toolkit_url,
            path=config.haipipe_toolkit_path,
            module_name="haipipe",
            install_hint="python -m pip install -e external/haipipe-toolkit",
        ),
        "tools": FoundationStatus(
            name="tools",
            role="Research/plugin/skill toolkit, including haipipe workflow skills and discovery utilities.",
            url=config.tools_url,
            path=str(tools_path),
            present=tools_path.exists(),
            install_hint="git submodule update --init --recursive external/tools",
        ),
        "codex_oauth": _package_status(
            name="codex_oauth",
            role="Preferred local Codex OAuth LLM transport for report and hypothesis generation.",
            url=config.codex_oauth_url,
            path=config.codex_oauth_package_path,
            module_name="codex_oauth",
            install_hint="python -m pip install -e external/codex-oauth",
        ),
        "academic_research_skills": FoundationStatus(
            name="academic_research_skills",
            role=(
                "Paper-grade research loop substrate: literature matrix, preregistration, "
                "statistical reporting, review, and integrity-gate templates."
            ),
            url=config.academic_research_skills_url,
            path=str(resolve_project_path(config.academic_research_skills_path)),
            present=resolve_project_path(config.academic_research_skills_path).exists(),
            install_hint="git submodule update --init --recursive external/academic-research-skills",
        ),
    }
    return {name: status.to_json() for name, status in statuses.items()}
