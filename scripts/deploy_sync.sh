#!/bin/bash
# Daily sync: new english.log lines → EngLearn API on EC2
# Runs on local machine via cron

set -e

PROJECT_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
LOG_PATH="$HOME/english.log"
STATE_FILE="$PROJECT_DIR/data/last_synced_line"
EC2_API="http://172.16.134.84:5555/api/sync-log"
SYNC_LOG="$PROJECT_DIR/data/deploy_sync.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$SYNC_LOG"
}

# Get last synced line number
LAST_LINE=0
if [ -f "$STATE_FILE" ]; then
    LAST_LINE=$(cat "$STATE_FILE")
fi
TOTAL_LINES=$(wc -l < "$LOG_PATH")

if [ "$TOTAL_LINES" -le "$LAST_LINE" ]; then
    log "No new lines (total: $TOTAL_LINES, synced: $LAST_LINE)"
    exit 0
fi

NEW_COUNT=$((TOTAL_LINES - LAST_LINE))
log "Syncing $NEW_COUNT new lines ($LAST_LINE → $TOTAL_LINES)"

# Extract new lines and build JSON
LINES_JSON=$(tail -n +"$((LAST_LINE + 1))" "$LOG_PATH" | python3 -c "
import sys, json
lines = [l for l in sys.stdin.readlines() if l.strip()]
print(json.dumps({'lines': lines}))
")

# POST to EC2
RESP=$(curl -s -w "\n%{http_code}" -X POST "$EC2_API" \
  -H "Content-Type: application/json" \
  -d "$LINES_JSON")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "$TOTAL_LINES" > "$STATE_FILE"
    log "OK: $BODY"
else
    log "FAILED (HTTP $HTTP_CODE): $BODY"
    exit 1
fi
