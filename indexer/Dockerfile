# Indexer - GPU-aware pipeline orchestrator
# Uses kotaemon base for Docling GPU support
FROM ghcr.io/cinnamon/kotaemon:main-full

# Reinstall PyTorch with CUDA support (same as kotaemon-cuda)
RUN pip uninstall -y torch torchvision torchaudio && \
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install additional indexer dependencies
RUN pip install --no-cache-dir \
    click>=8.0 \
    httpx>=0.25 \
    graphrag>=0.5.0 \
    pandas>=2.0 \
    pyarrow>=14.0 \
    pyyaml>=6.0 \
    docker>=7.0

# Copy indexer package
COPY indexer /app/indexer

# Apply Docling patch for GPU acceleration
COPY docling_loader_patched.py /app/libs/kotaemon/kotaemon/loaders/docling_loader.py

# Create jobs directory
RUN mkdir -p /app/indexer_jobs

# Set Python path
ENV PYTHONPATH=/app:/app/libs/kotaemon:/app/libs/ktem
ENV PYTHONUNBUFFERED=1

WORKDIR /app

ENTRYPOINT ["python", "-m", "indexer"]
CMD ["--help"]
