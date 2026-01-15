#!/bin/bash
# Monitor GraphRAG indexing progress
# Usage: ./graphrag_status.sh [--watch]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

show_status() {
    echo -e "${BLUE}=== GraphRAG Indexing Status ===${NC}"
    echo ""

    # Find latest GraphRAG directory
    LATEST_DIR=$(docker exec kotaemon ls -t /app/ktem_app_data/user_data/files/graphrag/ 2>/dev/null | head -1)

    if [ -z "$LATEST_DIR" ]; then
        echo -e "${YELLOW}No GraphRAG indexing jobs found${NC}"
        return
    fi

    GRAPHRAG_PATH="/app/ktem_app_data/user_data/files/graphrag/$LATEST_DIR"
    LOG_FILE="$GRAPHRAG_PATH/output/indexing-engine.log"

    echo -e "${GREEN}Active job:${NC} $LATEST_DIR"
    echo ""

    # Count input files
    INPUT_COUNT=$(docker exec kotaemon ls "$GRAPHRAG_PATH/input/" 2>/dev/null | wc -l)
    echo -e "${GREEN}Input files:${NC} $INPUT_COUNT"

    # Check completed workflows
    echo ""
    echo -e "${BLUE}Workflow progress:${NC}"
    WORKFLOWS=("create_base_text_units" "create_base_extracted_entities" "create_summarized_entities"
               "create_base_entity_graph" "create_final_entities" "create_final_nodes"
               "create_final_communities" "create_final_relationships" "create_final_text_units"
               "create_final_community_reports" "create_base_documents" "create_final_documents")

    for wf in "${WORKFLOWS[@]}"; do
        if docker exec kotaemon test -f "$GRAPHRAG_PATH/output/${wf}.parquet" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $wf"
        else
            # Check if currently running
            if docker exec kotaemon grep -q "dependencies for $wf" "$LOG_FILE" 2>/dev/null; then
                LAST_LINE=$(docker exec kotaemon tail -1 "$LOG_FILE" 2>/dev/null)
                if echo "$LAST_LINE" | grep -q "HTTP Request"; then
                    echo -e "  ${YELLOW}⟳${NC} $wf (in progress)"
                else
                    echo -e "  ${YELLOW}⟳${NC} $wf (running)"
                fi
            else
                echo -e "  ${RED}○${NC} $wf"
            fi
        fi
    done

    # Show LLM call stats
    echo ""
    echo -e "${BLUE}LLM calls:${NC}"
    CALL_COUNT=$(docker exec kotaemon grep -c "HTTP Request: POST.*chat/completions.*200 OK" "$LOG_FILE" 2>/dev/null || echo "0")
    LAST_CALL=$(docker exec kotaemon grep "HTTP Request: POST.*chat/completions.*200 OK" "$LOG_FILE" 2>/dev/null | tail -1 | cut -d' ' -f1 || echo "N/A")
    echo "  Completed: $CALL_COUNT"
    echo "  Last call: $LAST_CALL"

    # GPU status
    echo ""
    echo -e "${BLUE}GPU status:${NC}"
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null | \
        awk -F', ' '{printf "  Utilization: %s | Memory: %s / %s\n", $1, $2, $3}'

    echo ""
    echo -e "${BLUE}Latest log entries:${NC}"
    docker exec kotaemon tail -3 "$LOG_FILE" 2>/dev/null | sed 's/^/  /'
}

if [ "$1" == "--watch" ]; then
    while true; do
        clear
        show_status
        echo ""
        echo -e "${YELLOW}Refreshing in 30s... (Ctrl+C to exit)${NC}"
        sleep 30
    done
else
    show_status
fi
