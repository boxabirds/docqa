# Document Q&A with GraphRAG + PostgreSQL

A self-contained, GPU-accelerated document analysis system with knowledge graph retrieval.

## Documentation

- **[Technical Overview](docs/guides/overview.md)** - How the GraphRAG retrieval algorithm works
- **[Parameters Reference](docs/parameters.md)** - Configuration options

## Stack

- **Open WebUI** - ChatGPT-like interface with built-in RAG (45k+ GitHub stars)
- **Ollama** - Local LLM inference
- **Apache Tika** - Document extraction (PDF, DOCX, PPTX, XLSX, etc. + OCR)
- **Qwen3-30B-A3B** - MoE model, excellent reasoning at ~70 tok/s
- **nomic-embed-text** - Fast, high-quality embeddings

## Quick Start

```bash
chmod +x setup.sh
./setup.sh
```

Then open http://localhost:3000

## Manual Setup

```bash
# Start services
docker compose up -d

# Pull models (first run only, ~20GB total)
docker exec ollama ollama pull qwen3:30b-a3b
docker exec ollama ollama pull nomic-embed-text:latest

# Optional: vision model for diagrams/images
docker exec ollama ollama pull qwen3-vl:8b
```

## What You Get

- **ChatGPT-style interface** - familiar UX
- **Upload docs via web** - drag & drop in chat or via Documents tab
- **Supports**: PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, TXT, MD, HTML, RTF, and more
- **OCR built-in** - scanned PDFs work out of the box
- **Knowledge bases** - group documents into searchable collections
- **Multi-user** - each user has their own chat history and docs

## Configuration

### First-Time Setup

1. Open http://localhost:3000
2. Create admin account (first user becomes admin)
3. Settings are pre-configured via environment variables, but you can adjust in **Admin Panel > Settings > Documents**

### Increase Context Length (Important!)

Go to **Admin Panel > Settings > Models**, select your model, and set **Context Length** to **32768** or higher. The default 2048 is too small for RAG.

### Alternative: Docling for Complex PDFs

If you have scientific papers, invoices, or documents with complex tables, swap Tika for Docling:

```yaml
# In docker-compose.yml, replace tika service with:
docling:
  image: ghcr.io/docling-project/docling-serve-cu124:latest
  container_name: docling
  ports:
    - "5001:5001"
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]

# And update open-webui environment:
- CONTENT_EXTRACTION_ENGINE=docling
- DOCLING_SERVER_URL=http://docling:5001
```

## Usage

### Upload Documents

**Option 1: Document Library**
- Go to **Workspace > Documents**
- Click **+** to upload files
- Supports: PDF, DOCX, XLSX, PPTX, TXT, MD, HTML

**Option 2: Direct Upload in Chat**
- Click the 📎 icon in chat
- Upload files inline with your question

### Query Documents

**Option 1: # Reference**
- Type `#` in chat to see available documents
- Select document(s) to include in context

**Option 2: Knowledge Bases**
- Go to **Workspace > Knowledge**
- Create a knowledge base from multiple documents
- Reference with `#knowledge-base-name` in chat

### Image Analysis

Upload images directly in chat - Open WebUI will route to the vision model if available.

## Commands

```bash
# View logs
docker compose logs -f

# Stop
docker compose down

# Update Open WebUI
docker compose pull
docker compose up -d

# Full reset (removes all data)
docker compose down -v
```

## Troubleshooting

### "Model not found"
```bash
docker exec ollama ollama list  # Check installed models
docker exec ollama ollama pull qwen3:30b-a3b
```

### Slow RAG / timeouts
Increase model context length in Admin Panel > Settings > Models

### Poor extraction quality
Try switching Content Extraction engine:
- **Tika**: Good general-purpose
- **Docling**: Better for complex layouts, tables

### Out of VRAM
The 30B-A3B model needs ~21GB. Check with `nvidia-smi`.

## Data Locations

| Data | Container Path | Volume |
|------|----------------|--------|
| Documents & Settings | /app/backend/data | open_webui_data |
| LLM Models | /root/.ollama | ollama_data |

## Backup

```bash
# Backup Open WebUI data (documents, settings, chat history)
docker run --rm -v open_webui_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/openwebui-backup.tar.gz /data

# Restore
docker run --rm -v open_webui_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/openwebui-backup.tar.gz -C /
```

## Why Open WebUI?

- 45k+ GitHub stars, very active development
- Built-in RAG with 9 vector DB options
- Multiple document extraction engines
- ChatGPT-style UX
- Multi-user support
- No custom code to maintain
