#!/bin/bash
# Reindex demo documents with page markers
#
# This script:
# 1. Deletes the existing "Digital Twin PRD" collection
# 2. Runs the indexer pipeline (OCR → GraphRAG → import to PostgreSQL)
# 3. The new OCR stage stores PDFs and inserts page markers
#
# Usage: ./scripts/reindex_demo.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COLLECTION_NAME="Digital Twin PRD"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Container paths (indexer container)
CONTAINER_PDF_DIR="/data/credo"
CONTAINER_OUTPUT_DIR="/app/indexer_jobs/demo_$TIMESTAMP"

echo "=== Reindex Demo Documents ==="
echo "Collection: $COLLECTION_NAME"
echo "Output: $CONTAINER_OUTPUT_DIR"
echo ""

# GPU Management: Stop vLLM services to free GPU for OCR
echo "Stopping vLLM services to free GPU for OCR..."
docker compose --profile vllm stop vllm-llm vllm-embed vllm-chat 2>/dev/null || true

# Step 1: Delete existing collection (if exists)
echo "Step 1: Checking for existing collection..."
COLLECTION_ID=$(docker exec docqa-postgres psql -U docqa -d docqa -t -c \
    "SELECT id FROM collections WHERE name = '$COLLECTION_NAME'" 2>/dev/null | tr -d ' ')

if [ -n "$COLLECTION_ID" ]; then
    echo "  Deleting collection $COLLECTION_ID: $COLLECTION_NAME"
    docker exec docqa-postgres psql -U docqa -d docqa -c \
        "DELETE FROM collections WHERE id = $COLLECTION_ID"
else
    echo "  No existing collection found"
fi

# Step 2: Run OCR stage inside indexer container
echo ""
echo "Step 2: Running OCR extraction with page markers..."

# Run OCR with streaming output (stderr shows progress)
docker exec -t indexer python3 -u -c "
import sys
import json
import subprocess
import shutil
from pathlib import Path
from collections import defaultdict

# Setup paths
pdf_dir = Path('$CONTAINER_PDF_DIR')
output_dir = Path('$CONTAINER_OUTPUT_DIR')
output_dir.mkdir(parents=True, exist_ok=True)
pdf_storage = output_dir / 'pdfs'
pdf_storage.mkdir(exist_ok=True)

pdf_files = sorted(pdf_dir.glob('*.pdf'))
print(f'Found {len(pdf_files)} PDFs')
print()

# Process each PDF with progress
for i, pdf in enumerate(pdf_files, 1):
    print(f'[{i}/{len(pdf_files)}] Processing: {pdf.name}')

    # Copy PDF to storage
    shutil.copy(pdf, pdf_storage / pdf.name)

    # Run Docling extraction
    sys.path.insert(0, '/app')
    from kotaemon.loaders.docling_loader import DoclingReader
    reader = DoclingReader()
    docs = reader.load_data(pdf)

    # Group by page
    text_docs = [d for d in docs if d.metadata.get('type', 'text') == 'text']
    page_to_texts = defaultdict(list)
    for d in text_docs:
        page_num = d.metadata.get('page_label', 1)
        page_to_texts[page_num].append(d.text)

    # Write with page markers
    txt_file = output_dir / f'{pdf.stem}.txt'
    text_parts = []
    for page_num in sorted(page_to_texts.keys()):
        text_parts.append(f'<!-- PAGE {page_num} -->')
        text_parts.extend(page_to_texts[page_num])
    txt_file.write_text('\n\n'.join(text_parts))

    print(f'         -> {len(page_to_texts)} pages, {len(text_docs)} sections')

print()
print(f'OCR complete. PDFs stored in: {pdf_storage}')
"

# Step 3: Run GraphRAG indexing
echo ""
echo "Step 3: Starting vLLM services for entity extraction..."
docker compose --profile vllm up -d vllm-llm vllm-embed vllm-chat lfm2-adapter 2>/dev/null

# Wait for vLLM to be ready
echo "  Waiting for vLLM services to initialize..."
sleep 30

echo "Running GraphRAG indexing..."

docker exec -t indexer bash -c "
cd $CONTAINER_OUTPUT_DIR

# Initialize GraphRAG
python3 -m graphrag.index --root . --init 2>/dev/null

# Copy vLLM settings (LFM2 for entity extraction, Qwen for reports)
cp /app/graphrag_settings.yaml settings.yaml

# Create input directory and move text files
mkdir -p input
mv *.txt input/ 2>/dev/null || true

# Run indexing with progress
echo 'Starting GraphRAG indexing...'
python3 -m graphrag.index --root . --reporter rich
"

echo "  GraphRAG output in: $CONTAINER_OUTPUT_DIR/output"

# Step 4: Import to PostgreSQL
echo ""
echo "Step 4: Importing to PostgreSQL..."

# Copy output from indexer to backend container (backend has asyncpg)
TEMP_DIR="/tmp/graphrag_import_$$"
mkdir -p "$TEMP_DIR"

echo "  Copying output files..."
docker cp "indexer:$CONTAINER_OUTPUT_DIR/output" "$TEMP_DIR/"
docker cp "indexer:$CONTAINER_OUTPUT_DIR/pdfs" "$TEMP_DIR/" 2>/dev/null || true

# Copy to backend container
docker cp "$TEMP_DIR/output" docqa-backend:/tmp/graphrag_output
docker exec docqa-backend mkdir -p /tmp/graphrag_output/pdfs
if [ -d "$TEMP_DIR/pdfs" ]; then
    docker cp "$TEMP_DIR/pdfs/." docqa-backend:/tmp/graphrag_output/pdfs/
fi

# Run import from backend container
echo "  Running import..."
docker exec docqa-backend python3 -m backend.import_parquet /tmp/graphrag_output "$COLLECTION_NAME"

# Cleanup
rm -rf "$TEMP_DIR"

# Get the new collection ID
NEW_ID=$(docker exec docqa-postgres psql -U docqa -d docqa -t -c \
    "SELECT id FROM collections WHERE name = '$COLLECTION_NAME'" | tr -d ' ')

echo ""
echo "=== Complete ==="
echo "Collection: $COLLECTION_NAME (id=$NEW_ID)"
echo "Output: ~/.docqa/indexer/demo_$TIMESTAMP"
echo ""

# Check if page markers and source files were captured
echo "Verifying data..."
docker exec docqa-postgres psql -U docqa -d docqa -c \
    "SELECT COUNT(*) as total, COUNT(page_start) as with_pages, COUNT(source_file) as with_source FROM text_units WHERE collection_id = $NEW_ID"

# Check PDF paths
echo ""
echo "PDF storage:"
docker exec docqa-postgres psql -U docqa -d docqa -c \
    "SELECT original_filename, pdf_path IS NOT NULL as has_path FROM documents WHERE collection_id = $NEW_ID"

# Update chatStore.ts if collection ID changed
CURRENT_ID=$(grep -o 'DEMO_COLLECTION_ID = [0-9]*' "$PROJECT_DIR/frontend/src/stores/chatStore.ts" 2>/dev/null | grep -o '[0-9]*' || echo "")
if [ -n "$CURRENT_ID" ] && [ "$CURRENT_ID" != "$NEW_ID" ]; then
    echo ""
    echo "NOTE: Update frontend/src/stores/chatStore.ts:"
    echo "  DEMO_COLLECTION_ID = $NEW_ID  (currently $CURRENT_ID)"
fi
