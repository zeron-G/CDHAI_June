import subprocess
import sys
from pathlib import Path


def test_database_audit_scripts_expose_help() -> None:
    root = Path(__file__).parents[1]
    for script in ["server_database_audit.py", "remote_database_audit.py", "welldoc_space_manifest_audit.py"]:
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / script), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout
