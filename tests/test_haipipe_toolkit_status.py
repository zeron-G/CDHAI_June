from cdhai_june.config import ExternalConfig
from cdhai_june.external.haipipe_toolkit import haipipe_toolkit_status


def test_haipipe_toolkit_status_reports_submodule_metadata() -> None:
    status = haipipe_toolkit_status(ExternalConfig())

    assert status.package_name == "haipipe"
    assert status.submodule_url.endswith("JHU-CDHAI/WellDoc-SPACE.git")
    assert "external" in status.submodule_path
    assert "haipipe-toolkit" in status.submodule_path
