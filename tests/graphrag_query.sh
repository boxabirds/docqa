#!/bin/bash
# Query GraphRAG knowledge graph
# Usage: ./tests/graphrag_query.sh "What is Credo?"

QUERY="${1:-What is Credo?}"
docker exec kotaemon python /app/tests/graphrag_query.py "$QUERY"
