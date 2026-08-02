#!/usr/bin/env bash
# Scheduled scan wrapper — add to cron or launchd
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$PROJECT_DIR/.venv/bin/event-concierge"
LOG="$PROJECT_DIR/data/event-concierge.log"

mkdir -p "$PROJECT_DIR/data"
cd "$PROJECT_DIR"

if [[ ! -x "$VENV" ]]; then
  echo "Run scripts/setup.py first" >&2
  exit 1
fi

echo "[$(date -Iseconds)] Starting scheduled scan" >> "$LOG"
"$VENV" scan >> "$LOG" 2>&1
echo "[$(date -Iseconds)] Scan complete" >> "$LOG"
