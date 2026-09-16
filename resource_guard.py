#!/usr/bin/env python3
"""Autonomous cleanup guard for the XHS Kanban workflow.

Cleanup is driven by a session registry written by the orchestrator
before workers start. This registry is the single source of truth;
the guard never depends on workers remembering or reporting anything.

As a secondary safety net, the guard also checks for any live sessions
matching the prefix — catching sessions started after the registry was written.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

SESSION_PREFIX = "xhs-kanban-"
REGISTRY_FILE = "browser-sessions.json"
TEMP_DIRS = ("runtime", "runtime-params", "evidence", "roundtable")
TEMP_ROOT_FILES = ("current-run.json", "full-e2e-current.json")


def browser(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["agent-browser", *args], text=True, capture_output=True)


def cleanup_browser_sessions(root: Path) -> dict[str, Any]:
    """Close tabs for all XHS Kanban sessions.

    Primary source: the registry file written by run_iteration.py.
    Secondary source: live session list matching the prefix.
    """
    sessions: set[str] = set()

    # Primary: read the registry written by the orchestrator before dispatch.
    registry_path = root / "runtime" / REGISTRY_FILE
    if registry_path.is_file():
        try:
            for name in json.loads(registry_path.read_text(encoding="utf-8")):
                if isinstance(name, str) and name.startswith(SESSION_PREFIX):
                    sessions.add(name)
        except (json.JSONDecodeError, OSError):
            pass

    # Secondary: any live sessions the registry doesn't know about.
    listed = browser("session", "list", "--json")
    if listed.returncode == 0:
        try:
            for name in json.loads(listed.stdout).get("data", {}).get("sessions", []):
                if isinstance(name, str) and name.startswith(SESSION_PREFIX):
                    sessions.add(name)
        except (json.JSONDecodeError, AttributeError):
            pass

    closed: list[str] = []
    errors: list[str] = []
    for name in sorted(sessions):
        # `close` tears down the session's daemon; `tab close` only closes the
        # tab and leaves the daemon resident, so the next run refreshes it and it
        # never reaches its idle timeout.
        browser("--session", name, "tab", "close")
        proc = browser("--session", name, "close")
        detail = (proc.stderr or proc.stdout).strip()
        if proc.returncode == 0 or "tab_gone" in detail or "no active tab" in detail.lower():
            closed.append(name)
        else:
            errors.append(f"{name}: {detail[-1000:]}")

    return {
        "status": "PARTIAL" if errors else "COMPLETED",
        "sessions_from_registry": sorted(sessions),
        "closed": closed,
        "errors": errors,
    }


def cleanup_local_temp(root: Path) -> dict[str, Any]:
    """Delete only fixed, project-local transient paths."""
    root = root.resolve()
    removed: list[str] = []
    errors: list[str] = []
    for dirname in TEMP_DIRS:
        path = (root / dirname).resolve()
        if path.parent != root or not path.exists():
            continue
        try:
            shutil.rmtree(path)
            removed.append(str(path))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    for filename in TEMP_ROOT_FILES:
        path = (root / filename).resolve()
        if path.parent != root or not path.exists():
            continue
        try:
            path.unlink()
            removed.append(str(path))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return {"status": "PARTIAL" if errors else "COMPLETED", "removed": removed, "errors": errors}


def check_resources() -> dict[str, object]:
    """Safe pre-flight: never clean shared browser state before a run."""
    return {"browser_cleanup": "deferred_to_autonomous_final_guard", "closed": []}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--final", action="store_true", help="run autonomous final cleanup")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    if args.final:
        browser_result = cleanup_browser_sessions(Path(args.root))
        files_result = cleanup_local_temp(Path(args.root))
        output = {
            "ok": browser_result["status"] == "COMPLETED" and files_result["status"] == "COMPLETED",
            "browser": browser_result,
            "files": files_result,
        }
    else:
        output = check_resources()
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
