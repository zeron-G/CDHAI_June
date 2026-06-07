from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from cdhai_june.config import ExternalConfig


@dataclass(slots=True)
class HaipipeToolkitStatus:
    package_name: str
    submodule_url: str
    submodule_path: str
    submodule_present: bool
    pyproject_present: bool
    installed: bool
    module_origin: str | None
    install_hint: str

    def to_json(self) -> dict[str, str | bool | None]:
        return {
            "package_name": self.package_name,
            "submodule_url": self.submodule_url,
            "submodule_path": self.submodule_path,
            "submodule_present": self.submodule_present,
            "pyproject_present": self.pyproject_present,
            "installed": self.installed,
            "module_origin": self.module_origin,
            "install_hint": self.install_hint,
        }


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else project_root() / path


def haipipe_toolkit_status(config: ExternalConfig) -> HaipipeToolkitStatus:
    submodule_path = resolve_project_path(config.haipipe_toolkit_path)
    spec = find_spec("haipipe")
    return HaipipeToolkitStatus(
        package_name="haipipe",
        submodule_url=config.haipipe_toolkit_url,
        submodule_path=str(submodule_path),
        submodule_present=submodule_path.exists(),
        pyproject_present=(submodule_path / "pyproject.toml").exists(),
        installed=spec is not None,
        module_origin=spec.origin if spec else None,
        install_hint="git submodule update --init --recursive && python -m pip install -e external/haipipe-toolkit",
    )
