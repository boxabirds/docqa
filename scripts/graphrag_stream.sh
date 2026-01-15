#!/bin/bash
# Stream GraphRAG progress in real-time
# Usage: ./graphrag_stream.sh

GRAPHRAG_DIR=$(docker exec kotaemon ls -t /app/ktem_app_data/user_data/files/graphrag/ 2>/dev/null | head -1)

if [ -z "$GRAPHRAG_DIR" ]; then
    echo "No GraphRAG job found. Upload documents first."
    exit 1
fi

LOG="/app/ktem_app_data/user_data/files/graphrag/$GRAPHRAG_DIR/output/indexing-engine.log"

echo "Job: $GRAPHRAG_DIR"

# Wait for log file to exist
echo "Waiting for indexing to start..."
while ! docker exec kotaemon test -f "$LOG" 2>/dev/null; do
    sleep 1
    printf "."
done
echo ""
echo "Streaming:"
echo "---"

chunks=0
docker exec kotaemon tail -f "$LOG" 2>/dev/null | while read -r line; do
    case "$line" in
        *create_base_text_units*)
            echo -e "\033[32m[CHUNKS]\033[0m $line"
            ;;
        *extracted_entities*)
            echo -e "\033[36m[ENTITY]\033[0m $line"
            ;;
        *"perf - llm"*)
            # Extract time (first number after "took") and tokens
            time=$(echo "$line" | grep -oE 'took [0-9.]+' | grep -oE '[0-9.]+' | cut -d. -f1)
            tokens=$(echo "$line" | grep -oE 'output_tokens=[0-9]+' | grep -oE '[0-9]+')
            if [ -n "$time" ] && [ -n "$tokens" ] && [ "$time" -gt 0 ] 2>/dev/null; then
                tps=$((tokens / time))
                echo -e "\033[33m[LLM]\033[0m ${time}s ${tokens} tokens (${tps} t/s)"
            fi
            ;;
        *"HTTP Request"*"200 OK"*)
            ((chunks++))
            echo -e "\033[32m[PROGRESS]\033[0m $chunks chunks processed"
            ;;
        *"Running workflow"*)
            echo -e "\033[35m[WORKFLOW]\033[0m $line"
            ;;
        *[Ee]rror*)
            echo -e "\033[31m[ERROR]\033[0m $line"
            ;;
    esac
done
