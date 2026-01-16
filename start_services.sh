#!/bin/bash
# Start both FastAPI backend and Gradio frontend

# Install FastAPI dependencies
pip install -q fastapi uvicorn sse-starlette

# Start FastAPI in background
cd /app
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

# Start Gradio (foreground - this is the main process)
exec /app/launch.sh
