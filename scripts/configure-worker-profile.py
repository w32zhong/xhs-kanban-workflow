#!/usr/bin/env python3
"""Configure a dedicated Hermes profile for this Kanban workflow."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml


def hermes_profile_config(profile: str) -> Path:
    proc = subprocess.run(
        ["hermes", "--profile", profile, "config", "path"],
        text=True,
        capture_output=True,
        check=True,
    )
    return Path(proc.stdout.strip()).expanduser().resolve()


def configure(profile: str, workspace: Path) -> Path:
    if profile == "default":
        raise ValueError("refusing to configure the default profile; use a dedicated worker profile")
    config_path = hermes_profile_config(profile)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    agent = data.setdefault("agent", {})
    disabled = list(agent.get("disabled_toolsets") or [])
    disabled = [name for name in disabled if name != "kanban"]
    if "vision" not in disabled:
        disabled.append("vision")
    agent["disabled_toolsets"] = disabled

    terminal = data.setdefault("terminal", {})
    terminal["backend"] = "local"
    terminal["cwd"] = str(workspace.resolve())

    # Retention lives in the repo, not in whatever supervisor spawns the loop: a
    # worker profile is disposable, so cap its logs and let it prune the sessions
    # its kanban runs create instead of keeping them for the default 90 days.
    logging_cfg = data.setdefault("logging", {})
    logging_cfg["level"] = "WARNING"
    logging_cfg["max_size_mb"] = 1
    logging_cfg["backup_count"] = 0

    sessions = data.setdefault("sessions", {})
    sessions["auto_prune"] = True
    sessions["retention_days"] = 1
    sessions["auto_archive"] = False
    sessions["vacuum_after_prune"] = True
    sessions["min_interval_hours"] = 1

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable native Kanban worker tools, disable Vision, and set the project cwd."
    )
    parser.add_argument("--profile", required=True, help="Dedicated non-default Hermes profile")
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        parser.error(f"workspace does not exist: {workspace}")
    try:
        path = configure(args.profile, workspace)
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(f"configured {args.profile}: {path}")
    print("native Kanban worker tools enabled; Vision disabled; terminal cwd set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
