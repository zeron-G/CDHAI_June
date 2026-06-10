from pathlib import Path


def test_ci_workflows_exist_and_cover_core_gates() -> None:
    root = Path(__file__).parents[1]
    ci = root / ".github" / "workflows" / "ci.yml"
    release = root / ".github" / "workflows" / "release.yml"

    assert ci.exists()
    assert release.exists()
    ci_text = ci.read_text(encoding="utf-8")
    release_text = release.read_text(encoding="utf-8")
    assert "python -m ruff check src tests" in ci_text
    assert "python -m pytest" in ci_text
    assert "python -m cdhai_june run" in ci_text
    assert "python -m build" in ci_text
    assert "python -m build" in release_text
    assert "actions/checkout@v6" in ci_text
    assert "actions/setup-python@v6" in ci_text
    assert "actions/checkout@v6" in release_text
    assert "actions/setup-python@v6" in release_text
    assert "windows-2025-vs2026" in ci_text
    assert "windows-latest" not in ci_text
