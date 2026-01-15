#!/bin/bash
# Run GraphRAG entity extraction benchmarks
#
# Usage:
#   ./benchmarks/run.sh                          # Run baseline (qwen2.5:14b) on 1 file
#   ./benchmarks/run.sh gemma2:2b                # Run specific model
#   ./benchmarks/run.sh gemma2:2b 3              # Run on 3 files
#   ./benchmarks/run.sh --all                    # Run all models in models.txt
#   ./benchmarks/run.sh --all --pull             # Run all, pulling missing models
#   ./benchmarks/run.sh --report                 # Generate comparison report only

set -e
cd "$(dirname "$0")/.."

if [[ "$1" == "--all" ]]; then
    shift
    docker exec kotaemon python /app/benchmarks/run_all.py "$@"
elif [[ "$1" == "--report" ]]; then
    docker exec kotaemon python /app/benchmarks/run_all.py --report-only
else
    MODEL="${1:-qwen2.5:14b}"
    NUM_FILES="${2:-1}"
    shift 2 2>/dev/null || true
    docker exec kotaemon python /app/benchmarks/benchmark.py --model "$MODEL" --num-files "$NUM_FILES" "$@"
fi
