#!/bin/bash
# Detailed GraphRAG monitoring - shows chunk and entity extraction progress
# Usage: ./graphrag_monitor.sh [-f|--follow]

set -e

FOLLOW=false
[[ "$1" == "-f" || "$1" == "--follow" ]] && FOLLOW=true

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

GRAPHRAG_DIR=$(docker exec kotaemon ls -t /app/ktem_app_data/user_data/files/graphrag/ 2>/dev/null | head -1)

if [ -z "$GRAPHRAG_DIR" ]; then
    echo "No GraphRAG job found. Upload documents first."
    exit 1
fi

LOG="/app/ktem_app_data/user_data/files/graphrag/$GRAPHRAG_DIR/output/indexing-engine.log"
OUTPUT_DIR="/app/ktem_app_data/user_data/files/graphrag/$GRAPHRAG_DIR/output"

show_status() {
    clear
    echo -e "${BLUE}=== GraphRAG Monitor ===${NC}"
    echo -e "Job: ${CYAN}$GRAPHRAG_DIR${NC}"
    echo ""

    # Chunk info
    CHUNK_COUNT=$(docker exec kotaemon cat "$OUTPUT_DIR/create_base_text_units.parquet" 2>/dev/null | wc -c)
    if [ "$CHUNK_COUNT" -gt 0 ]; then
        CHUNKS=$(docker exec kotaemon python -c "
import pandas as pd
df = pd.read_parquet('$OUTPUT_DIR/create_base_text_units.parquet')
print(f'Chunks: {len(df)} | Avg tokens: {df[\"n_tokens\"].mean():.0f} | Total tokens: {df[\"n_tokens\"].sum()}')" 2>/dev/null)
        echo -e "${GREEN}$CHUNKS${NC}"
    fi
    echo ""

    # LLM calls progress
    COMPLETED=$(docker exec kotaemon grep -c "HTTP Request: POST.*200 OK" "$LOG" 2>/dev/null || echo 0)
    TOTAL_CHUNKS=$(docker exec kotaemon python -c "import pandas as pd; print(len(pd.read_parquet('$OUTPUT_DIR/create_base_text_units.parquet')))" 2>/dev/null || echo "?")

    echo -e "${BLUE}Entity Extraction:${NC}"
    echo -e "  Progress: ${GREEN}$COMPLETED${NC} / $TOTAL_CHUNKS chunks"

    # Calculate speed
    TIMES=$(docker exec kotaemon grep "took" "$LOG" 2>/dev/null | tail -5 | awk '{for(i=1;i<=NF;i++) if($i=="took") print $(i+1)}' | sed 's/\..*//')
    if [ -n "$TIMES" ]; then
        AVG=$(echo "$TIMES" | awk '{sum+=$1; n++} END {if(n>0) print sum/n; else print 0}')
        echo -e "  Avg time/chunk: ${YELLOW}${AVG}s${NC}"

        REMAINING=$((TOTAL_CHUNKS - COMPLETED))
        if [ "$REMAINING" -gt 0 ] && [ "$AVG" != "0" ]; then
            ETA_SEC=$(echo "$REMAINING * $AVG / 2" | bc 2>/dev/null || echo "?")  # /2 for parallel
            ETA_MIN=$((ETA_SEC / 60))
            echo -e "  ETA: ${YELLOW}~${ETA_MIN}m${NC}"
        fi
    fi
    echo ""

    # Token stats from recent calls
    echo -e "${BLUE}Recent LLM calls:${NC}"
    docker exec kotaemon grep "perf - llm.chat" "$LOG" 2>/dev/null | tail -5 | \
        awk -F'took |input_tokens=|output_tokens=' '{
            time=$2; sub(/\..*/,"",time);
            in=$3; sub(/,.*/,"",in);
            out=$4; sub(/,.*/,"",out);
            if(out+0 > 0) tps=out/time; else tps=0;
            printf "  %3ss | in:%4s out:%4s | %.0f t/s\n", time, in, out, tps
        }'
    echo ""

    # GPU status
    echo -e "${BLUE}GPU:${NC}"
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null | \
        awk -F', ' '{printf "  %s util | %s / %s\n", $1, $2, $3}'

    # Current workflow
    echo ""
    echo -e "${BLUE}Current workflow:${NC}"
    docker exec kotaemon grep "dependencies for" "$LOG" 2>/dev/null | tail -1 | \
        awk -F'dependencies for |:' '{print "  " $2}'
}

if [ "$FOLLOW" = true ]; then
    while true; do
        show_status
        echo ""
        echo -e "${YELLOW}Refreshing in 10s... (Ctrl+C to exit)${NC}"
        sleep 10
    done
else
    show_status
fi
