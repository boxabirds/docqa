#!/bin/bash
# Estimate GraphRAG indexing completion time
# Usage: ./graphrag_eta.sh

set -e

# Find latest GraphRAG directory
LATEST_DIR=$(docker exec kotaemon ls -t /app/ktem_app_data/user_data/files/graphrag/ 2>/dev/null | head -1)

if [ -z "$LATEST_DIR" ]; then
    echo "No GraphRAG indexing jobs found"
    exit 1
fi

GRAPHRAG_PATH="/app/ktem_app_data/user_data/files/graphrag/$LATEST_DIR"
LOG_FILE="$GRAPHRAG_PATH/output/indexing-engine.log"

# Count input files (chunks)
INPUT_COUNT=$(docker exec kotaemon ls "$GRAPHRAG_PATH/input/" 2>/dev/null | wc -l)

# Count completed LLM calls for entity extraction
COMPLETED_CALLS=$(docker exec kotaemon grep -c "perf - llm.chat.*Process.*took" "$LOG_FILE" 2>/dev/null || echo "0")

# Calculate average time per call
if [ "$COMPLETED_CALLS" -gt 0 ]; then
    AVG_TIME=$(docker exec kotaemon grep "perf - llm.chat.*Process.*took" "$LOG_FILE" 2>/dev/null | \
        awk '{for(i=1;i<=NF;i++) if($i=="took") print $(i+1)}' | \
        sed 's/\..*//' | \
        awk '{sum+=$1; count++} END {if(count>0) print int(sum/count); else print 0}')
else
    AVG_TIME=120  # Default estimate
fi

echo "=== GraphRAG ETA Calculator ==="
echo ""
echo "Job ID: $LATEST_DIR"
echo "Total chunks: $INPUT_COUNT"
echo "Completed LLM calls: $COMPLETED_CALLS"
echo "Average time per call: ${AVG_TIME}s"
echo ""

# Entity extraction phase (1 call per chunk)
REMAINING_ENTITY=$((INPUT_COUNT - COMPLETED_CALLS))
if [ "$REMAINING_ENTITY" -gt 0 ]; then
    ENTITY_ETA_SEC=$((REMAINING_ENTITY * AVG_TIME))
    ENTITY_ETA_MIN=$((ENTITY_ETA_SEC / 60))
    ENTITY_ETA_HR=$((ENTITY_ETA_MIN / 60))
    echo "Entity extraction phase:"
    echo "  Remaining: $REMAINING_ENTITY chunks"
    if [ "$ENTITY_ETA_HR" -gt 0 ]; then
        echo "  ETA: ~${ENTITY_ETA_HR}h $((ENTITY_ETA_MIN % 60))m"
    else
        echo "  ETA: ~${ENTITY_ETA_MIN}m"
    fi
else
    echo "Entity extraction: Complete"
fi

echo ""
echo "Note: Additional phases (summarization, community detection, reports)"
echo "      will add significant time after entity extraction."
echo ""
echo "Progress: $((COMPLETED_CALLS * 100 / INPUT_COUNT))% of entity extraction"
