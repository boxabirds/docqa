# DocQA - GraphRAG Document Q&A System

A GPU-accelerated document analysis system with knowledge graph retrieval, built on PostgreSQL + pgvector.

## Documentation

- **[Technical Overview](docs/guides/overview.md)** - How the GraphRAG retrieval algorithm works
- **[Parameters Reference](docs/parameters.md)** - Configuration options

## Stack

| Component | Technology |
|-----------|------------|
| **Frontend** | React 19 + Vite + TailwindCSS + Zustand |
| **Backend API** | FastAPI with async PostgreSQL |
| **Database** | PostgreSQL 16 + pgvector |
| **LLM Inference** | vLLM (Qwen2.5-7B-Instruct) |
| **Embeddings** | BGE-M3 via vLLM |
| **Entity Extraction** | LFM2-1.2B-Extract via vLLM |
| **Document Processing** | Docling (GPU-accelerated OCR) |
| **Retrieval** | Custom GraphRAG with pgvector similarity search |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   React     │────▶│   FastAPI   │────▶│   PostgreSQL    │
│  Frontend   │     │   Backend   │     │   + pgvector    │
└─────────────┘     └──────┬──────┘     └─────────────────┘
     :3001                 │                     ▲
                           │                     │
                           ▼                     │
                    ┌─────────────┐              │
                    │    vLLM     │              │
                    │  (Chat +    │              │
                    │  Embeddings)│              │
                    └─────────────┘              │
                                                 │
┌─────────────┐     ┌─────────────┐              │
│   Docling   │────▶│   Indexer   │──────────────┘
│    (OCR)    │     │  Pipeline   │
└─────────────┘     └─────────────┘
```

## Quick Start

```bash
# Start core services (PostgreSQL + backend + frontend)
docker compose up -d postgres backend

# Start vLLM services for inference
docker compose --profile vllm up -d

# Frontend development server
cd frontend && npm install && npm run dev
```

- **Frontend**: http://localhost:3001
- **Backend API**: http://localhost:8080
- **API docs**: http://localhost:8080/docs

## Services

### Core Services (default profile)

```bash
docker compose up -d
```

| Service | Port | Description |
|---------|------|-------------|
| `postgres` | 5433 | PostgreSQL 16 + pgvector |
| `backend` | 8080 | FastAPI REST API |
| `kotaemon` | 3000 | Gradio UI (legacy, for Docling) |
| `ollama` | 11434 | Deprecated, kept for Kotaemon |

### vLLM Services (vllm profile)

```bash
docker compose --profile vllm up -d
```

| Service | Port | Model | VRAM |
|---------|------|-------|------|
| `vllm-chat` | 8004 | Qwen2.5-7B-Instruct | ~14GB |
| `vllm-embed` | 8003 | BGE-M3 | ~1.5GB |
| `vllm-llm` | 8001 | LFM2-1.2B-Extract | ~3.7GB |
| `lfm2-adapter` | 8002 | Format adapter | CPU |
| `indexer` | - | Pipeline orchestrator | GPU |

## Indexing Documents

The indexer pipeline processes documents through multiple stages:

1. **OCR** - Docling extracts text from PDFs with layout understanding
2. **Entity Extraction** - LFM2 extracts entities and relationships
3. **Community Detection** - Leiden algorithm clusters the knowledge graph
4. **Community Reports** - Qwen2.5-7B generates summaries
5. **Embeddings** - BGE-M3 embeds entities and text units

```bash
# Run indexer interactively
docker exec -it indexer bash
python -m indexer.cli index /data/my_documents --collection "My Collection"
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/collections` | GET | List document collections |
| `/api/conversations` | GET/POST | Manage conversations |
| `/api/conversations/{id}` | GET/PATCH/DELETE | Single conversation |
| `/api/chat` | POST | Stream chat response (SSE) |
| `/api/documents/{id}/pdf` | GET | Serve PDF for viewing |

### Chat Request

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the main topic?", "collection_id": 1}'
```

Response is Server-Sent Events with types: `info`, `chat`, `done`, `error`.

## Data Storage

All data persists to `~/.docqa/`:

| Path | Contents |
|------|----------|
| `~/.docqa/postgres` | PostgreSQL data |
| `~/.docqa/kotaemon` | Docling models, Kotaemon data |
| `~/.docqa/indexer` | Indexer job state |

## Development

### Frontend

```bash
cd frontend
npm install
npm run dev      # Dev server on :3001
npm run build    # Production build
npm run test     # Playwright tests
```

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

## Commands

```bash
# View logs
docker compose logs -f backend
docker compose --profile vllm logs -f vllm-chat

# Stop all
docker compose --profile vllm down

# Full reset (removes all data)
docker compose --profile vllm down -v
rm -rf ~/.docqa

# Check GPU usage
nvidia-smi
```

## Troubleshooting

### vLLM not responding
```bash
docker compose --profile vllm logs vllm-chat
# Check if model is loaded (first request triggers download)
```

### Out of VRAM
The full vLLM stack needs ~20GB VRAM. Run fewer services or use smaller models:
```bash
# Run only embeddings + chat (skip entity extraction)
docker compose --profile vllm up -d vllm-embed vllm-chat
```

### Database connection errors
```bash
# Check PostgreSQL is healthy
docker compose logs postgres
docker exec docqa-postgres pg_isready -U docqa
```

## Legacy Components

- **Kotaemon** (port 3000): Original Gradio UI, kept for Docling integration
- **Ollama** (port 11434): Deprecated, kept only for Kotaemon compatibility

The main application now uses the React frontend + FastAPI backend.
