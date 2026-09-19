#!/usr/bin/env bash
# Continuously run complete XHS Kanban campaigns, one at a time.
#
# Retention is owned HERE, not by whatever supervisor happens to start this
# script:
#
#   * this script re-points its own stdout/stderr at logs/loop.out.log in APPEND
#     mode and truncates that file at the start of every round, so the log never
#     holds more than one round's output — and the supervisor that spawned us
#     receives no output to accumulate either;
#   * run.py deletes every card, worker session and browser tab a round created
#     before it returns.
#
# A fresh checkout therefore needs nothing beyond `runner-config.json`:
#
#   ./run_loop.sh
#
# Optional overrides: XHS_AGENT_PROFILE, XHS_ACCOUNT_NAME,
# XHS_LOOP_SLEEP_SECONDS.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/loop.out.log"

# Our own append-only fd: truncating the file below can never leave a hole.
exec >> "$LOG_FILE" 2>&1

PROFILE="${XHS_AGENT_PROFILE:-}"
ACCOUNT_NAME="${XHS_ACCOUNT_NAME:-}"
SLEEP_SECONDS="${XHS_LOOP_SLEEP_SECONDS:-5}"

round_args=()
[ -n "$PROFILE" ] && round_args+=(--profile "$PROFILE")
[ -n "$ACCOUNT_NAME" ] && round_args+=(--account-name "$ACCOUNT_NAME")

while true; do
    : > "$LOG_FILE"
    printf '[%s] Starting new run...\n' "$(date '+%Y-%m-%d %H:%M:%S')"
    rc=0
    python3 run.py "${round_args[@]}" || rc=$?
    if [ "$rc" -eq 3 ]; then
        printf '[%s] Xiaohongshu login required; the loop is stopping. Scan the QR code in the shared browser, then restart this script.\n' \
            "$(date '+%Y-%m-%d %H:%M:%S')"
        exit 0
    fi
    if [ "$rc" -eq 0 ]; then
        result="completed"
    else
        result="failed"
    fi
    printf '[%s] Run %s; next run starts in %s seconds.\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$result" "$SLEEP_SECONDS"
    sleep "$SLEEP_SECONDS"
done
