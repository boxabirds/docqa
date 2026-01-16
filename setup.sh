#!/bin/bash
# Setup script for Document Q&A with Open WebUI + Ollama

set -e

echo "==========================================="
echo "Document Q&A Setup (Open WebUI + Ollama)"
echo "==========================================="

# Check NVIDIA
if ! nvidia-smi &> /dev/null; then
    echo "❌ NVIDIA drivers not found"
    exit 1
fi
echo "✅ NVIDIA GPU detected"

# Check Docker GPU support, configure if needed
if ! docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi &> /dev/null 2>&1; then
    echo "⚠️  Docker GPU support not working, configuring..."
    
    # Configure NVIDIA Container Toolkit
    if ! command -v nvidia-ctk &> /dev/null; then
        echo "❌ nvidia-container-toolkit not installed"
        echo "Install with: sudo apt install nvidia-container-toolkit"
        exit 1
    fi
    
    echo "   Configuring Docker runtime..."
    sudo nvidia-ctk runtime configure --runtime=docker
    
    echo "   Restarting Docker..."
    sudo systemctl restart docker
    
    # Wait for Docker to come back
    sleep 3
    
    # Test again
    if ! docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi &> /dev/null 2>&1; then
        echo "❌ Docker GPU support still not working"
        echo "   Check: cat /etc/docker/daemon.json"
        exit 1
    fi
fi
echo "✅ Docker GPU support working"

# Start services
echo ""
echo "Starting services..."
docker compose up -d

# Wait for Ollama
echo "Waiting for Ollama to be ready..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "✅ Ollama ready"

# Pull models
echo ""
echo "Pulling models (this will take a while)..."
docker exec ollama ollama pull qwen3:30b-a3b
docker exec ollama ollama pull nomic-embed-text:latest
docker exec ollama ollama pull qwen2.5vl:7b

echo ""
echo "==========================================="
echo "✅ Setup complete!"
echo ""
echo "Open http://localhost:3000 in your browser"
echo ""
echo "First time setup:"
echo "  1. Create an admin account"
echo "  2. Go to Admin Panel > Settings > Documents"
echo "  3. Set RAG embedding model to 'nomic-embed-text:latest'"
echo "  4. Upload docs via Workspace > Documents or directly in chat"
echo ""
echo "To use RAG in chat:"
echo "  - Type # to reference uploaded documents"
echo "  - Or just upload files directly to the chat"
echo "==========================================="
