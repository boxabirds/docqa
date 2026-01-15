# Tunable Parameters Reference

MECE (Mutually Exclusive, Collectively Exhaustive) list of all tunable parameters for performance and quality optimization.

---

## 1. Ollama Runtime Configuration

Parameters controlling the LLM inference engine.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `OLLAMA_CONTEXT_LENGTH` | Maximum context window size (tokens) | `32768` | `16384` (faster), `65536` (more context) |
| `OLLAMA_NUM_PARALLEL` | Concurrent request slots | `2` | `1` (less VRAM), `4` (more throughput) |
| `OLLAMA_KV_CACHE_TYPE` | KV cache quantization | `q8_0` | `f16` (quality), `q4_0` (memory) |
| `OLLAMA_FLASH_ATTENTION` | Flash attention optimization | `1` (enabled) | `0` (disabled, for debugging) |

**Location**: `docker-compose.yml` → `ollama.environment`

---

## 2. LLM Model Configuration

Parameters set in the Ollama Modelfile.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `num_ctx` | Model context window | `16384` (qwen3-nothink) | `8192` (faster), `32768` (more context) |
| `temperature` | Sampling temperature | `0.3` | `0.0` (deterministic), `0.7` (creative) |
| `num_gpu` | GPU layers | `999` (all) | Lower values for hybrid CPU/GPU |
| Template | Chat template format | No thinking tags | With `<think>` tags (slower, reasoning) |

**Location**: Ollama Modelfiles (`ollama create` command)

**Current Models**:
- `qwen3-nothink` - 30B, Q4_K_M, 16K context, no thinking
- `qwen2.5vl:7b` - 7B VLM for figure captioning
- `nomic-embed-text` - Embeddings

---

## 3. GraphRAG Chunking Configuration

Parameters controlling document segmentation for entity extraction.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `chunks.size` | Target chunk size (tokens) | `512` | `256` (granular), `1024` (broader context) |
| `chunks.overlap` | Token overlap between chunks | `50` | `0` (none), `100` (more redundancy) |
| `chunks.strategy.type` | Chunking algorithm | `sentence` | `tokens` (fixed-size) |
| `chunks.group_by_columns` | Grouping key | `[id]` | Document-level grouping options |

**Location**: `graphrag_settings.yaml` → `chunks`

**Trade-offs**:
- Smaller chunks → More LLM calls, finer entities, higher cost
- Larger chunks → Fewer calls, may miss entities, lower cost
- More overlap → Better entity continuity, more redundancy
- Sentence strategy → Respects semantic boundaries

---

## 4. GraphRAG LLM Configuration

Parameters for entity extraction LLM calls.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `llm.model` | Model for entity extraction | `qwen3-nothink` | Other Ollama models |
| `llm.max_tokens` | Max output tokens per call | `2000` | `1000` (faster), `4000` (complex docs) |
| `llm.concurrent_requests` | Parallel LLM calls | `4` | `1` (sequential), `8` (if VRAM allows) |
| `llm.request_timeout` | Timeout per request (seconds) | `300.0` | `120.0` (fail fast), `600.0` (complex) |
| `llm.model_supports_json` | JSON output mode | `true` | `false` (if model struggles) |
| `llm.tokens_per_minute` | Rate limit | `0` (unlimited) | Set if API-limited |
| `llm.requests_per_minute` | Rate limit | `0` (unlimited) | Set if API-limited |

**Location**: `graphrag_settings.yaml` → `llm`

---

## 5. GraphRAG Parallelization

Parameters controlling parallel execution.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `parallelization.stagger` | Delay between parallel starts (s) | `0.5` | `0.0` (aggressive), `1.0` (gentler) |
| `async_mode` | Async execution mode | `threaded` | `asyncio` (if supported) |

**Location**: `graphrag_settings.yaml` → `parallelization`, `async_mode`

---

## 6. GraphRAG Embeddings Configuration

Parameters for vector embeddings.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `embeddings.llm.model` | Embedding model | `nomic-embed-text` | `mxbai-embed-large`, `bge-large` |
| `embeddings.async_mode` | Async mode for embeddings | `threaded` | `asyncio` |

**Location**: `graphrag_settings.yaml` → `embeddings`

**Model Comparison**:
| Model | Dimensions | Speed | Quality |
|-------|------------|-------|---------|
| `nomic-embed-text` | 768 | Fast | Good |
| `mxbai-embed-large` | 1024 | Medium | Better |
| `bge-large-en` | 1024 | Medium | Better |

---

## 7. Docling PDF Processing

Parameters for document parsing and OCR.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `ocr_options.use_gpu` | GPU acceleration for OCR | `true` | `false` (CPU fallback) |
| `ocr_options.lang` | OCR languages | `['en']` | `['en', 'de']` (multilingual) |
| `table_structure_options.mode` | Table extraction quality | `ACCURATE` | `FAST` (speed priority) |
| `table_structure_options.do_cell_matching` | Cell matching | `true` | `false` (simpler tables) |
| `do_table_structure` | Enable table extraction | `true` | `false` (text-only) |
| `do_ocr` | Enable OCR | `true` | `false` (native PDFs only) |

**Location**: `docling_loader_patched.py` → `converter_()` method

---

## 8. VLM Figure Captioning

Parameters for visual language model figure processing.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| `KH_VLM_ENDPOINT` | VLM API endpoint | `http://ollama:11434/v1/chat/completions` | External API |
| `KH_VLM_MODEL` | VLM model | `qwen2.5vl:7b` | `llava:13b`, `llava:34b` |
| `max_figure_to_caption` | Max figures to process | `100` | `10` (faster), `500` (thorough) |
| `figure_friendly_filetypes` | File types for figure extraction | `.pdf, .jpeg, .jpg, .png...` | Subset for specific workflows |

**Location**:
- `docker-compose.yml` → `kotaemon.environment`
- `docling_loader_patched.py` → class parameters

**VLM Model Comparison**:
| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `qwen2.5vl:7b` | 7B | ~17 t/s | Good |
| `llava:13b` | 13B | ~10 t/s | Better |
| `llava:34b` | 34B | ~5 t/s | Best |

---

## 9. Kotaemon RAG Configuration

Parameters for retrieval and response generation (configured in UI).

| Parameter | Description | Typical Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| Top-K retrieval | Number of chunks retrieved | `5` | `3` (focused), `10` (broad) |
| Similarity threshold | Minimum relevance score | `0.7` | `0.5` (recall), `0.9` (precision) |
| Reranking | Rerank retrieved chunks | Enabled | Disabled (faster) |
| Multimodal | Include images in context | `true` | `false` (text-only) |

**Location**: Kotaemon UI settings per collection

---

## 10. Docker Resource Allocation

Parameters for container resource limits.

| Parameter | Description | Current Value | Alternatives to Explore |
|-----------|-------------|---------------|------------------------|
| GPU count | GPUs allocated | `1` | `all` (multi-GPU) |
| GPU capabilities | Required GPU features | `[gpu]` | `[gpu, compute]` |
| Memory limits | Container memory cap | Unlimited | `32g` (prevent OOM) |
| CPU limits | Container CPU cap | Unlimited | `8` (limit interference) |

**Location**: `docker-compose.yml` → `deploy.resources`

---

## Quick Reference: Performance vs Quality Trade-offs

### For Maximum Speed
```yaml
# Ollama
OLLAMA_CONTEXT_LENGTH: 16384
OLLAMA_NUM_PARALLEL: 1
OLLAMA_KV_CACHE_TYPE: q4_0

# GraphRAG
chunks.size: 1024
chunks.overlap: 0
llm.max_tokens: 1000
llm.concurrent_requests: 2

# Docling
table_structure_options.mode: FAST
max_figure_to_caption: 10
```

### For Maximum Quality
```yaml
# Ollama
OLLAMA_CONTEXT_LENGTH: 32768
OLLAMA_NUM_PARALLEL: 2
OLLAMA_KV_CACHE_TYPE: f16

# GraphRAG
chunks.size: 256
chunks.overlap: 100
chunks.strategy: sentences
llm.max_tokens: 4000
llm.concurrent_requests: 4

# Docling
table_structure_options.mode: ACCURATE
max_figure_to_caption: 500
```

### Current Configuration (Balanced)
```yaml
# Ollama
OLLAMA_CONTEXT_LENGTH: 32768
OLLAMA_NUM_PARALLEL: 2
OLLAMA_KV_CACHE_TYPE: q8_0

# GraphRAG
chunks.size: 512
chunks.overlap: 50
chunks.strategy: sentences
llm.max_tokens: 2000
llm.concurrent_requests: 4

# Docling
table_structure_options.mode: ACCURATE
max_figure_to_caption: 100
```

---

## Parameter Interaction Notes

1. **Context vs VRAM**: Larger `num_ctx` requires more VRAM. If model doesn't fit, Ollama falls back to CPU (100x slower).

2. **Parallel vs Memory**: `OLLAMA_NUM_PARALLEL` × `num_ctx` determines total KV cache memory.

3. **Chunk size vs LLM calls**: GraphRAG makes ~1 LLM call per chunk. Smaller chunks = more calls = longer indexing.

4. **Overlap vs Redundancy**: Higher overlap improves entity extraction continuity but increases total chunks.

5. **VLM speed**: VLMs are inherently slower (~17 t/s) than text-only models (~200 t/s) due to vision encoding.

6. **Model swapping**: With `NUM_PARALLEL=2`, Ollama can keep 2 models loaded, reducing swap overhead.
