#!/bin/bash
# Direct GraphRAG chat - bypasses the broken UI
# Usage: ./tests/chat.sh "What is Credo?"

QUERY="${1:-What is Credo?}"
docker exec kotaemon python /app/tests/graphrag_chat.py "$QUERY"
