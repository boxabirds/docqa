#!/bin/bash
# Test Kotaemon chat via Gradio API
# Usage: ./tests/api_chat.sh "What is Credo?"

QUERY="${1:-What is Credo?}"
python3 "$(dirname "$0")/api_chat.py" "$QUERY"
