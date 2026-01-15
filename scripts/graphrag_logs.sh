#!/bin/bash
# Stream GraphRAG indexing logs
# Usage: ./graphrag_logs.sh [-f|--follow] [lines]

set -e

FOLLOW=false
LINES=50

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        *)
            LINES=$1
            shift
            ;;
    esac
done

# Find latest GraphRAG directory
LATEST_DIR=$(docker exec kotaemon ls -t /app/ktem_app_data/user_data/files/graphrag/ 2>/dev/null | head -1)

if [ -z "$LATEST_DIR" ]; then
    echo "No GraphRAG indexing jobs found"
    exit 1
fi

LOG_FILE="/app/ktem_app_data/user_data/files/graphrag/$LATEST_DIR/output/indexing-engine.log"

echo "=== GraphRAG Log: $LATEST_DIR ==="
echo ""

if [ "$FOLLOW" = true ]; then
    docker exec kotaemon tail -f "$LOG_FILE" 2>/dev/null
else
    docker exec kotaemon tail -$LINES "$LOG_FILE" 2>/dev/null
fi
