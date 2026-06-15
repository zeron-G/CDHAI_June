#!/usr/bin/env python3
"""Run the CDHAI_June server database audit over SSH.

Authentication is intentionally read from an environment variable, SSH key, or
an interactive getpass prompt. Do not pass passwords on the command line.
"""

from __future__ import annotations

import argparse
import getpass
import os
import posixpath
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload and run server_database_audit.py over SSH.")
    parser.add_argument("--host", default=os.environ.get("CDHAI_DB_SSH_HOST", "10.175.198.65"))
    parser.add_argument("--user", default=os.environ.get("CDHAI_DB_SSH_USER", "rgao28"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CDHAI_DB_SSH_PORT", "22")))
    parser.add_argument("--key-path", default=os.environ.get("CDHAI_DB_SSH_KEY_PATH", ""))
    parser.add_argument("--password-env", default="CDHAI_DB_SSH_PASSWORD")
    parser.add_argument("--ask-password", action="store_true", help="Prompt for SSH password without echo.")
    parser.add_argument("--remote-output-dir", default="")
    parser.add_argument("--local-output-dir", default="reports/database_audit/latest")
    parser.add_argument("--max-exact-rows", type=int, default=100_000)
    parser.add_argument("--max-columns-per-table", type=int, default=40)
    parser.add_argument("--sqlite-root", action="append", default=[])
    args = parser.parse_args()

    try:
        import paramiko
    except ImportError:
        print("paramiko is required for remote audit. Install it or run scripts/server_database_audit.py directly on the server.", file=sys.stderr)
        return 2

    password = os.environ.get(args.password_env)
    if args.ask_password and not password:
        password = getpass.getpass(f"SSH password for {args.user}@{args.host}: ")

    key_filename = str(Path(args.key_path).expanduser()) if args.key_path else None
    if not password and not key_filename:
        print(
            f"No SSH credential available. Set {args.password_env}, pass --key-path, or run with --ask-password.",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    server_script = repo_root / "scripts" / "server_database_audit.py"
    if not server_script.exists():
        print(f"Missing server audit script: {server_script}", file=sys.stderr)
        return 2

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    remote_output_dir = args.remote_output_dir or f"~/cdhai_database_audit_{timestamp}"
    local_output_dir = Path(args.local_output_dir).expanduser().resolve()
    local_output_dir.mkdir(parents=True, exist_ok=True)

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=args.host,
            port=args.port,
            username=args.user,
            password=password,
            key_filename=key_filename,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            look_for_keys=not key_filename,
        )
        sftp = client.open_sftp()
        remote_script = f"/tmp/cdhai_server_database_audit_{timestamp}.py"
        sftp.put(str(server_script), remote_script)
        sftp.chmod(remote_script, 0o700)
        sqlite_args = " ".join(shell_quote_arg("--sqlite-root") + " " + shell_quote_arg(root) for root in args.sqlite_root)
        command = (
            f"python3 {shell_quote_arg(remote_script)} "
            f"--output-dir {shell_quote_arg(remote_output_dir)} "
            f"--max-exact-rows {int(args.max_exact_rows)} "
            f"--max-columns-per-table {int(args.max_columns_per_table)} "
            f"{sqlite_args}"
        ).strip()
        exit_code, stdout, stderr = run_ssh(client, command, timeout_hint="database audit")
        if exit_code != 0:
            print(stderr or stdout, file=sys.stderr)
            return exit_code or 1

        expanded_remote_dir = remote_path(client, remote_output_dir)
        for name in ["database_inventory.json", "database_inventory_report.md"]:
            sftp.get(posixpath.join(expanded_remote_dir, name), str(local_output_dir / name))
        run_ssh(client, f"rm -f {shell_quote_arg(remote_script)}", timeout_hint="cleanup")
    finally:
        client.close()

    print(f"Downloaded audit report to {local_output_dir}")
    return 0


def run_ssh(client: object, command: str, timeout_hint: str) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, get_pty=False)
    del stdin
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if code != 0 and not err:
        err = f"Remote command failed during {timeout_hint}: {command}"
    return code, out, err


def remote_path(client: object, path: str) -> str:
    code, out, err = run_ssh(client, f"python3 - <<'PY'\nfrom pathlib import Path\nprint(Path({path!r}).expanduser().resolve())\nPY", "path resolution")
    if code != 0:
        raise RuntimeError(err)
    return out.strip()


def shell_quote_arg(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
