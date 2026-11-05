#!/usr/bin/env bash
# Keep the container active until the usage limit resets.
# Writes a heartbeat every INTERVAL seconds for DURATION seconds, then exits.
# Uses no model tokens: it is a plain shell process.
#
# Usage: keepalive.sh [duration_seconds] [interval_seconds]
#   default: 7000s (~1h57m), heartbeat every 120s
set -u
DURATION="${1:-7000}"
INTERVAL="${2:-120}"
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/keepalive.txt"
END=$(( $(date +%s) + DURATION ))

while [ "$(date +%s)" -lt "$END" ]; do
  {
    echo "heartbeat $(date -u +%FT%TZ)"
    echo "load: $(cut -d' ' -f1-3 /proc/loadavg)"
    echo "disk: $(df -h / | awk 'NR==2{print $4" free ("$5" used)"}')"
    echo "remaining: $(( END - $(date +%s) ))s"
  } > "$OUT"
  sleep "$INTERVAL"
done
echo "done $(date -u +%FT%TZ)" >> "$OUT"
