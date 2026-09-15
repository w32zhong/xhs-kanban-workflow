#!/usr/bin/env python3
"""Run one bounded XHS Kanban test workflow and clean transient resources.

This runner is manual while the workflow is being refined. It does not create
Cron jobs or push changes.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent
RUNTIME_DIRS = ("runtime", "runtime-params", "logs", "evidence", "roundtable")
RUNTIME_ROOT_FILES = ("current-run.json", "full-e2e-current.json")
DRAFT_FILE = Path("runtime") / "chair-decision.json"
ACTIVE_STATUSES = {"triage", "todo", "scheduled", "ready", "running", "review", "blocked"}
WAITING_STATUSES = {"triage", "todo", "scheduled", "ready", "blocked"}

# When the scout stage finds the Xiaohongshu login lost, the runner blocks the
# remaining cards (they stay visible on the board as the "waiting for a human"
# signal) and then stops the whole loop. Restoring the session needs a QR scan by
# a person, so there is nothing useful to do until an operator restarts the
# runner by hand: sleeping or spinning more rounds would only burn memory.
LOGIN_REQUIRED_REASON = (
    "小红书登录态失效（scout 返回 LOGIN_REQUIRED）：等待人工扫码登录后再继续，本卡保持阻塞，禁止自动重试"
)


class LoginRequired(Exception):
    """Raised when scout reports a lost Xiaohongshu login; aborts the round."""


@dataclass(frozen=True)
class RunnerConfig:
    profile: str
    workspace: Path
    account_name: str
    board_slug: str = "xhs-run"
    poll_seconds: int = 3
    timeout_minutes: int = 45
    keep_board: bool = False
    max_output_chars: int = 6000


def load_config(
    root: Path,
    config_path: Path,
    *,
    profile: str | None = None,
    workspace: str | None = None,
    account_name: str | None = None,
    poll_seconds: int | None = None,
    timeout_minutes: int | None = None,
    keep_board: bool | None = None,
) -> RunnerConfig:
    data: dict[str, Any] = {}
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
    config_dir = config_path.resolve().parent
    raw_workspace = workspace or os.environ.get("XHS_WORKSPACE") or data.get("workspace") or str(root)
    workspace_path = Path(raw_workspace).expanduser()
    if not workspace_path.is_absolute():
        workspace_path = config_dir / workspace_path
    resolved_profile = profile or os.environ.get("XHS_AGENT_PROFILE") or data.get("profile")
    resolved_account = account_name or os.environ.get("XHS_ACCOUNT_NAME") or data.get("account_name")
    if not resolved_profile:
        raise ValueError("agent profile is required: set --profile, XHS_AGENT_PROFILE, or runner-config.json")
    if resolved_profile == "default":
        raise ValueError("default profile is not allowed; configure a dedicated worker profile")
    if not resolved_account:
        raise ValueError("account name is required: set --account-name, XHS_ACCOUNT_NAME, or runner-config.json")
    return RunnerConfig(
        profile=str(resolved_profile),
        workspace=workspace_path.resolve(),
        account_name=str(resolved_account),
        board_slug=str(data.get("board_slug", "xhs-run")),
        poll_seconds=int(poll_seconds or data.get("poll_seconds", 3)),
        timeout_minutes=int(timeout_minutes or data.get("timeout_minutes", 45)),
        keep_board=bool(data.get("keep_board", False) if keep_board is None else keep_board),
        max_output_chars=int(data.get("max_output_chars", 6000)),
    )


def command(args: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True)
    if check and proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(args)}: {detail[-1200:]}")
    return proc


@contextlib.contextmanager
def runner_lock(root: Path = ROOT) -> Iterator[None]:
    lock_path = root / ".run.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another XHS workflow run is already active") from exc
        yield


def list_boards() -> set[str]:
    proc = command(["hermes", "kanban", "boards", "list", "--json"])
    return {item["slug"] for item in json.loads(proc.stdout)}


def prepare_board(board_slug: str, workspace: Path) -> None:
    """Create the persistent board once, otherwise reuse it in place."""
    boards = list_boards()
    if board_slug in boards:
        command(["hermes", "kanban", "boards", "set-default-workdir", board_slug, str(workspace)])
        command(["hermes", "kanban", "boards", "switch", board_slug])
        return
    board_name = "小红书侦察兵快速迭代" if board_slug == "xhs-scout" else "小红书流程测试 · 未定稿"
    command([
        "hermes", "kanban", "boards", "create", board_slug,
        "--name", board_name,
        "--default-workdir", str(workspace),
        "--switch",
    ])


def start_iteration(root: Path, cfg: RunnerConfig, *, pipeline_config: Path | None = None) -> dict[str, Any]:
    args = [
        sys.executable,
        str(root / "run_iteration.py"),
        "--profile", cfg.profile,
        "--workspace", str(cfg.workspace),
        "--board-slug", cfg.board_slug,
        "--account-name", cfg.account_name,
    ]
    if pipeline_config is not None:
        args.extend(["--config", str(pipeline_config)])
    proc = command(args, cwd=root)
    return json.loads(proc.stdout)


def list_tasks(board: str) -> list[dict[str, Any]]:
    proc = command(["hermes", "kanban", "--board", board, "list", "--json"])
    return json.loads(proc.stdout)


def archive_visible_tasks(board: str) -> None:
    """Archive every currently visible card while preserving board history."""
    task_ids = [task_id for task in list_tasks(board) if isinstance(task_id := task.get("id"), str) and task_id]
    if task_ids:
        command(["hermes", "kanban", "--board", board, "archive", *task_ids])


def board_is_terminal(tasks: list[dict[str, Any]], current_task_ids: set[str]) -> bool:
    """Return whether every task created by this iteration has terminated."""
    if not current_task_ids:
        return False
    current = {task.get("id"): task for task in tasks if task.get("id") in current_task_ids}
    return current_task_ids <= current.keys() and not any(
        task.get("status") in ACTIVE_STATUSES for task in current.values()
    )


def activate_waiting_task(board: str, task_id: str, profile: str) -> None:
    """Assign the next semantically approved card so the dispatcher may spawn it."""
    command(["hermes", "kanban", "--board", board, "assign", task_id, profile])


def dispatch_board(board: str, *, max_tasks: int = 2) -> None:
    """Dispatch newly assigned cards without waiting for the periodic timer."""
    command(["hermes", "kanban", "--board", board, "dispatch", "--max", str(max_tasks)])


def finish_without_worker(board: str, task_id: str, reason: str) -> None:
    """Complete a waiting card deterministically so no LLM worker is spawned."""
    command([
        "hermes", "kanban", "--board", board, "promote", task_id,
        "semantic gate skip", "--force",
    ])
    metadata = json.dumps({"status": "SKIPPED", "reason": reason}, ensure_ascii=False)
    command([
        "hermes", "kanban", "--board", board, "complete", task_id,
        "--summary", f"SKIPPED: {reason}",
        "--metadata", metadata,
    ])


def block_for_login(board: str, task_ids: list[str], reason: str = LOGIN_REQUIRED_REASON) -> None:
    """Stickily block the pending cards so the board visibly waits for a human.

    ``block`` only accepts running/ready cards, so todo cards are promoted
    first. Sticky blocks survive dispatcher passes: nothing is respawned until
    an operator unblocks the cards.
    """
    for task_id in task_ids:
        command(["hermes", "kanban", "--board", board, "promote", task_id, reason, "--force"], check=False)
        command(["hermes", "kanban", "--board", board, "block", task_id, reason], check=False)


def _result_status(run: dict[str, Any]) -> str | None:
    metadata = run.get("metadata") or {}
    return (
        metadata.get("status")
        or metadata.get("publish_status")
        or metadata.get("decision")
        or metadata.get("recommendation")
    )


def normalize_approved_draft(root: Path = ROOT) -> dict[str, Any]:
    """Collapse newlines in the approved draft before it reaches the publisher.

    The Xiaohongshu web comment box submits on Enter, so a draft that contains a
    newline is published as a truncated first line, and the input step can even
    duplicate a prefix. Prompt rules already forbid newlines; this guard makes
    the guarantee deterministic no matter what the chair agent produced.
    """
    path = root / DRAFT_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "SKIPPED_UNREADABLE", "path": str(path), "error": str(exc)}
    draft = data.get("final_comment")
    if not isinstance(draft, str) or not draft.strip():
        return {"status": "SKIPPED_NO_DRAFT", "path": str(path)}
    normalized = re.sub(r"[ \t]*[\r\n]+[ \t]*", " ", draft)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized).strip()
    if normalized == draft:
        return {"status": "UNCHANGED", "path": str(path)}
    data["final_comment"] = normalized
    data["line_count"] = 1
    data["newline_normalized"] = True
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        return {"status": "FAILED", "path": str(path), "error": str(exc)}
    return {
        "status": "NORMALIZED",
        "path": str(path),
        "removed_line_breaks": draft.count("\n") + draft.count("\r"),
    }


def apply_semantic_gates(
    board: str,
    state: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> bool:
    """Launch the quality roundtable and keep irreversible actions gated.

    Returns True when it changed the board and False when there is nothing to
    do. Raises :class:`LoginRequired` after blocking the remaining cards when
    the scout reports that the Xiaohongshu login is missing.
    """
    created = state.get("created", [])
    key_to_id = {item.get("key"): item.get("id") for item in created}
    task_by_id = {task.get("id"): task for task in tasks}
    profile = str(state.get("profile") or "")

    def stage_status(key: str) -> str | None:
        task_id = key_to_id.get(key)
        task = task_by_id.get(task_id, {})
        if not task_id or task.get("status") != "done" or not task.get("assignee"):
            return None
        return _result_status(latest_run(board, task_id))

    def activate(keys: list[str]) -> bool:
        changed = False
        for key in keys:
            task_id = key_to_id.get(key)
            task = task_by_id.get(task_id, {})
            if task_id and task.get("status") in WAITING_STATUSES and not task.get("assignee"):
                if not profile:
                    raise RuntimeError("iteration state is missing worker profile")
                activate_waiting_task(board, task_id, profile)
                changed = True
        if changed:
            dispatch_board(board, max_tasks=2)
        return changed

    def skip(keys: list[str], reason: str) -> bool:
        changed = False
        for key in keys:
            task_id = key_to_id.get(key)
            task = task_by_id.get(task_id, {})
            if task_id and task.get("status") in WAITING_STATUSES:
                finish_without_worker(board, task_id, reason)
                changed = True
        return changed

    scout = stage_status("scout")
    if scout is None:
        return False
    downstream = ["review-a", "review-b", "chair", "publish-send", "publish-verify"]
    if scout != "FOUND":
        if scout == "LOGIN_REQUIRED":
            # The scout agent found the Xiaohongshu login lost. A human has to
            # scan the QR code, so block the remaining cards — they stay visible
            # on the board as the signal that the campaign is waiting — and then
            # abort the runner instead of sampling the same failure again.
            pending = [
                key_to_id[key] for key in downstream
                if key_to_id.get(key)
                and task_by_id.get(key_to_id[key], {}).get("status") in WAITING_STATUSES
            ]
            block_for_login(board, pending)
            print(
                f"[login-gate] scout={scout}; {len(pending)} cards blocked; "
                f"runner stopping until an operator restores the Xiaohongshu login",
                file=sys.stderr,
                flush=True,
            )
            raise LoginRequired(f"scout reported {scout}")
        return skip(downstream, f"scout ended with {scout}")

    # Both reviewers run in parallel. Their job is to improve the answer; PASS,
    # REVISE, and even a single REJECT all proceed to independent chair synthesis.
    if activate(["review-a", "review-b"]):
        return True
    review_a = stage_status("review-a")
    review_b = stage_status("review-b")
    if review_a is None or review_b is None:
        return False
    if activate(["chair"]):
        return True

    chair = stage_status("chair")
    if chair is None:
        return False
    if chair != "APPROVE":
        return skip(["publish-send", "publish-verify"], f"chair ended with {chair}")
    # Deterministic safety net: the approved draft must be a single line before
    # it reaches the publisher, because the XHS comment box submits on Enter.
    draft_guard = normalize_approved_draft()
    if draft_guard.get("status") == "NORMALIZED":
        print(
            f"[draft-guard] collapsed {draft_guard['removed_line_breaks']} line break(s) "
            f"in the approved draft: {draft_guard['path']}",
            file=sys.stderr,
            flush=True,
        )
    if activate(["publish-send"]):
        return True

    publish = stage_status("publish-send")
    if publish is None:
        return False
    if publish != "SEND_SUCCESS":
        return skip(["publish-verify"], f"publish-send ended with {publish}")
    return activate(["publish-verify"])


def wait_for_board(board: str, state: dict[str, Any], cfg: RunnerConfig) -> list[dict[str, Any]]:
    deadline = time.monotonic() + cfg.timeout_minutes * 60
    created = state.get("created", [])
    current_task_ids = {
        item.get("id") for item in created
        if isinstance(item.get("id"), str) and item.get("id")
    }
    created_by_id = {item.get("id"): item for item in created}
    while True:
        tasks = list_tasks(board)
        gate = apply_semantic_gates(board, state, tasks)
        if gate:
            tasks = list_tasks(board)
        if board_is_terminal(tasks, current_task_ids):
            return tasks
        if time.monotonic() >= deadline:
            task_by_id = {task.get("id"): task for task in tasks}
            pending = []
            for task_id in current_task_ids:
                task = task_by_id.get(task_id, {})
                status = task.get("status", "missing")
                if status in ACTIVE_STATUSES or status == "missing":
                    created_task = created_by_id.get(task_id, {})
                    pending.append({
                        "key": created_task.get("key"),
                        "id": task_id,
                        "status": status,
                        "assignee": task.get("assignee"),
                    })
            pending.sort(key=lambda item: (str(item.get("key")), str(item.get("id"))))
            detail = json.dumps(pending, ensure_ascii=False, separators=(",", ":"))
            raise TimeoutError(
                f"board {board} exceeded {cfg.timeout_minutes} minutes; current nonterminal tasks: {detail}"
            )
        time.sleep(cfg.poll_seconds)


def latest_run(board: str, task_id: str) -> dict[str, Any]:
    proc = command(["hermes", "kanban", "--board", board, "runs", task_id, "--json"])
    runs = json.loads(proc.stdout)
    return runs[-1] if runs else {}


def compact_result(board: str, state: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {task["id"]: task for task in tasks}
    stages: list[dict[str, Any]] = []
    for created in state.get("created", []):
        task = by_id.get(created["id"], {})
        run = latest_run(board, created["id"])
        metadata = run.get("metadata") or {}
        stages.append({
            "key": created.get("key"),
            "task_id": created.get("id"),
            "task_status": task.get("status"),
            "outcome": run.get("outcome"),
            "result_status": (
                metadata.get("status")
                or metadata.get("publish_status")
                or metadata.get("decision")
                or metadata.get("recommendation")
            ),
            "metadata": metadata,
        })
    verify = next((stage for stage in stages if stage["key"] == "publish-verify"), {})
    publish = next((stage for stage in stages if stage["key"] == "publish-send"), {})
    return {
        "status": "COMPLETED",
        "board": board,
        "target_id": state.get("target_id"),
        "publish_status": publish.get("result_status"),
        "verify_status": verify.get("result_status"),
        "published_and_verified": is_published_and_verified(stages),
        "stages": stages,
    }


def is_published_and_verified(stages: list[dict[str, Any]]) -> bool:
    status = {stage.get("key"): stage.get("result_status") for stage in stages}
    verify = next((stage for stage in stages if stage.get("key") == "publish-verify"), {})
    verify_metadata = verify.get("metadata") or {}
    return (
        status.get("chair") == "APPROVE"
        and status.get("publish-send") == "SEND_SUCCESS"
        and status.get("publish-verify") in {"VERIFIED", "DUPLICATES_DELETED"}
        and verify_metadata.get("exact_draft_count_in_target_thread", "1") in (1, "1")
    )


def snapshot_runtime_files(root: Path) -> set[Path]:
    files: set[Path] = set()
    for dirname in RUNTIME_DIRS:
        base = root / dirname
        if base.is_dir():
            files.update(path.resolve() for path in base.rglob("*") if path.is_file())
    for name in RUNTIME_ROOT_FILES:
        path = root / name
        if path.is_file():
            files.add(path.resolve())
    return files


def cleanup_new_runtime_files(root: Path, before: set[Path]) -> dict[str, Any]:
    """Remove bounded transient artifacts.

    ``before`` is retained in the API for testability and compatibility, but
    recurring runs intentionally clear stale artifacts too: every allowlisted
    path is generated runtime state and ignored by git.
    """
    after = snapshot_runtime_files(root)
    removed: list[str] = []
    errors: list[str] = []
    for path in sorted(after):
        try:
            path.unlink(missing_ok=True)
            removed.append(str(path))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    for dirname in RUNTIME_DIRS:
        base = root / dirname
        if base.is_dir():
            for directory in sorted((p for p in base.rglob("*") if p.is_dir()), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
    return {"removed_count": len(removed), "errors": errors}


def run_final_guard(root: Path = ROOT) -> dict[str, Any]:
    """Run autonomous prefix-based browser and project-temp cleanup."""
    proc = command(
        ["python3", str(root / "resource_guard.py"), "--final", "--root", str(root)],
        cwd=root,
        check=False,
    )
    if proc.returncode:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()[-1000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "final guard returned invalid JSON"}


def remove_board(board: str) -> dict[str, Any]:
    proc = command(["hermes", "kanban", "boards", "rm", board, "--delete"], check=False)
    return {"ok": proc.returncode == 0, "detail": (proc.stderr or proc.stdout).strip()[-1000:]}


def execute_campaign(root: Path, cfg: RunnerConfig, *, pipeline_config: Path | None = None) -> dict[str, Any]:
    started = time.time()
    runtime_before = snapshot_runtime_files(root)
    board: str | None = None
    result: dict[str, Any] = {"status": "ERROR", "error": "runner did not start"}
    cleanup: dict[str, Any] = {}
    try:
        with runner_lock(root):
            prepare_board(cfg.board_slug, cfg.workspace)
            archive_visible_tasks(cfg.board_slug)
            state = start_iteration(root, cfg, pipeline_config=pipeline_config)
            started_board = state.get("board")
            if not isinstance(started_board, str) or not started_board:
                raise RuntimeError("run_iteration.py did not return a board slug")
            board = started_board
            tasks = wait_for_board(started_board, state, cfg)
            result = compact_result(started_board, state, tasks)
    except LoginRequired as exc:
        # Not an error: a human has to scan the QR code and restart the runner.
        result = {"status": "LOGIN_REQUIRED", "detail": str(exc)}
    except Exception as exc:
        result = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        cleanup["board"] = {"ok": True, "kept": True, "slug": cfg.board_slug}
        cleanup["guard"] = run_final_guard(root)
    result["cleanup"] = cleanup
    result["elapsed_seconds"] = round(time.time() - started, 1)
    if board and "board" not in result:
        result["board"] = board
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one bounded XHS Kanban workflow with guaranteed cleanup")
    parser.add_argument("--config", default=str(ROOT / "runner-config.json"))
    parser.add_argument("--pipeline-config", help="Override pipeline.json passed to run_iteration.py")
    parser.add_argument("--scout-only", action="store_true", help="Run only the scout refinement pipeline")
    parser.add_argument("--profile")
    parser.add_argument("--workspace")
    parser.add_argument("--account-name", help="Current Xiaohongshu account nickname used for duplicate checks")
    parser.add_argument("--poll-seconds", type=int)
    parser.add_argument("--timeout-minutes", type=int)
    parser.add_argument("--keep-board", action="store_true", default=None)
    parser.add_argument("--inject-error", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg: RunnerConfig | None = None
    try:
        cfg = load_config(
            ROOT,
            Path(args.config),
            profile=args.profile,
            workspace=args.workspace,
            account_name=args.account_name,
            poll_seconds=args.poll_seconds,
            timeout_minutes=args.timeout_minutes,
            keep_board=args.keep_board,
        )
        if args.inject_error:
            raise RuntimeError("injected test error")
        pipeline_config = Path(args.pipeline_config).expanduser().resolve() if args.pipeline_config else None
        if args.scout_only:
            pipeline_config = ROOT / "scout-pipeline.json"
            cfg = RunnerConfig(
                profile=cfg.profile,
                workspace=cfg.workspace,
                account_name=cfg.account_name,
                board_slug="xhs-scout",
                poll_seconds=cfg.poll_seconds,
                timeout_minutes=min(cfg.timeout_minutes, 8),
                keep_board=True,
                max_output_chars=cfg.max_output_chars,
            )
        result = execute_campaign(ROOT, cfg, pipeline_config=pipeline_config)
    except Exception as exc:
        result = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    max_chars = cfg.max_output_chars if cfg is not None else 6000
    print(text if len(text) <= max_chars else text[:max_chars] + "\n...TRUNCATED")
    status = result.get("status")
    if status == "LOGIN_REQUIRED":
        # Distinct exit code so run_loop.sh stops instead of starting a new round.
        return 3
    return 0 if status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
