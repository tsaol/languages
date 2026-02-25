#!/bin/bash
# Daily sync: english.log → EngLearn DB → S3 → EC2
# Runs on local machine via cron

set -e

PROJECT_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
DB_PATH="$PROJECT_DIR/data/englearn.db"
LOG_PATH="$HOME/english.log"
S3_BUCKET="englearn-deploy-tmp"
EC2_INSTANCE="i-0f86894d2231b1cd0"
SYNC_LOG="$PROJECT_DIR/data/deploy_sync.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$SYNC_LOG"
}

log "=== Starting deploy sync ==="

# Step 1: Parse new english.log entries into local DB
log "Step 1: Syncing english.log → local DB"
englearn sync 2>&1 | tee -a "$SYNC_LOG"

# Step 2: Upload DB + english.log to S3
log "Step 2: Uploading to S3"
aws s3 cp "$DB_PATH" "s3://$S3_BUCKET/englearn.db" --quiet
aws s3 cp "$LOG_PATH" "s3://$S3_BUCKET/english.log" --quiet
log "  Uploaded DB ($(du -h "$DB_PATH" | cut -f1)) and english.log"

# Step 3: Generate presigned URLs (valid 5 min)
log "Step 3: Generating presigned URLs"
DB_URL=$(aws s3 presign "s3://$S3_BUCKET/englearn.db" --expires-in 300)
LOG_URL=$(aws s3 presign "s3://$S3_BUCKET/english.log" --expires-in 300)

# Step 4: Tell EC2 to download via presigned URL and restart
log "Step 4: Updating EC2 instance"
CMD_ID=$(aws ssm send-command \
  --instance-ids "$EC2_INSTANCE" \
  --document-name "AWS-RunShellScript" \
  --parameters commands="[
    \"python3 -c \\\"import urllib.request; urllib.request.urlretrieve('${DB_URL}', '/home/ubuntu/languages/data/englearn.db')\\\"\",
    \"python3 -c \\\"import urllib.request; urllib.request.urlretrieve('${LOG_URL}', '/home/ubuntu/english.log')\\\"\",
    \"chown ubuntu:ubuntu /home/ubuntu/languages/data/englearn.db /home/ubuntu/english.log\",
    \"systemctl restart englearn\",
    \"echo SYNC_DONE\"
  ]" \
  --timeout-seconds 60 \
  --output text --query 'Command.CommandId' 2>&1)

log "  SSM command: $CMD_ID"

# Wait for completion (max 60s)
for i in $(seq 1 12); do
    sleep 5
    STATUS=$(aws ssm get-command-invocation \
      --command-id "$CMD_ID" \
      --instance-id "$EC2_INSTANCE" \
      --query 'Status' --output text 2>/dev/null || echo "Pending")
    if [ "$STATUS" = "Success" ]; then
        log "  EC2 updated successfully"
        break
    elif [ "$STATUS" = "Failed" ]; then
        log "  ERROR: EC2 update failed"
        aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$EC2_INSTANCE" \
          --query 'StandardErrorContent' --output text >> "$SYNC_LOG" 2>&1
        break
    fi
done

log "=== Deploy sync complete ==="
