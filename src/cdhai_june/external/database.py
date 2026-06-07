from __future__ import annotations

from cdhai_june.config import DatabaseConfig


def ssh_tunnel_command(config: DatabaseConfig) -> str:
    key_part = f' -i "{config.ssh_key_path}"' if config.ssh_key_path else ""
    return (
        f"ssh{key_part} -N -L "
        f"{config.tunnel_local_port}:{config.remote_host}:{config.remote_port} "
        f"-p {config.ssh_port} {config.ssh_user}@{config.ssh_host}"
    )


def database_runtime_hint(config: DatabaseConfig) -> dict[str, str | int]:
    return {
        "ssh_host": config.ssh_host,
        "ssh_user": config.ssh_user,
        "ssh_port": config.ssh_port,
        "tunnel_command": ssh_tunnel_command(config),
        "local_database_host": "127.0.0.1",
        "local_database_port": config.tunnel_local_port,
        "note": "Set DB name/user/password from environment at runtime; do not commit credentials.",
    }

