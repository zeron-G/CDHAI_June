from cdhai_june.config import ExternalConfig
from cdhai_june.external.foundations import foundational_dependency_statuses


def test_foundational_dependency_statuses_cover_user_repos() -> None:
    statuses = foundational_dependency_statuses(ExternalConfig())

    assert set(statuses) == {
        "haipipe_toolkit",
        "tools",
        "codex_oauth",
        "academic_research_skills",
        "cdhai_hapf",
    }
    assert statuses["tools"]["url"] == "https://github.com/jluo41/Tools.git"
    assert statuses["codex_oauth"]["url"] == "https://github.com/zeron-G/codex_oauth.git"
    assert statuses["haipipe_toolkit"]["url"] == "https://github.com/JHU-CDHAI/WellDoc-SPACE.git"
    assert statuses["academic_research_skills"]["url"] == "https://github.com/Imbad0202/academic-research-skills.git"
    assert statuses["cdhai_hapf"]["url"] == "https://github.com/zeron-G/CDHAI-HAPF.git"
