# Int8 Embedding Quantization Research

## Question
Can scalar int8 quantization help speed up GraphRAG indexing?

## TL;DR
**Partial benefit.** Int8 quantization would help with:
- ✅ 4x smaller embedding storage (faster writes, smaller indexes)
- ✅ 3-4x faster similarity search during retrieval
- ❌ Does NOT speed up embedding generation itself

**The real indexing bottleneck is LLM-based entity extraction, not embeddings.**

---

## Current Embedding Setup

| Setting | Value |
|---------|-------|
| Model | `bge-m3` (1024 dimensions) |
| API | Ollama OpenAI-compatible endpoint |
| Vector Store | LanceDB (parquet-based) |
| Precision | float32 (no quantization) |
| Async Mode | threaded |

**Embedding calls during indexing:**
- ~200 calls per document collection (one per entity)
- ~42ms per embedding
- ~8.6 minutes for 716-entity collection

---

## What Int8 Quantization Does

Converts `float32` embeddings (4 bytes/value) to `int8` (1 byte/value):

```python
from sentence_transformers.quantization import quantize_embeddings

# Original: 1024 dims × 4 bytes = 4KB per embedding
# Int8:     1024 dims × 1 byte  = 1KB per embedding (4x smaller)
int8_embeddings = quantize_embeddings(embeddings, precision="int8")
```

**Performance Impact:**

| Metric | Float32 | Int8 | Benefit |
|--------|---------|------|---------|
| Storage | 4KB/emb | 1KB/emb | **4x smaller** |
| Search Speed | 1x | 3.66x | **3-4x faster** |
| Accuracy | 100% | 97% | Minimal loss |

---

## Where Int8 Would Help

### 1. During Indexing
- **Faster LanceDB writes** - Smaller embeddings = faster storage
- **Smaller parquet files** - 4x reduction in `create_final_entities.parquet`
- **Less disk I/O** - Important for large collections

### 2. During Retrieval
- **Faster similarity search** - 3-4x speedup in LanceDB queries
- **Lower memory usage** - Can fit larger indexes in RAM
- **Rescoring** - Use int8 for initial search, float32 for top-K reranking

---

## Where Int8 Would NOT Help

### The Real Bottleneck: LLM Entity Extraction

From current config (`graphrag_settings.yaml`):
```yaml
llm:
  concurrent_requests: 1  # Sequential LLM calls!
```

**Indexing time breakdown:**
1. **Chunking**: Fast (~1s)
2. **Entity Extraction**: SLOW - 1 LLM call per chunk (sequential)
3. **Embedding Generation**: Medium - via Ollama
4. **Storage**: Fast

**The bottleneck is step 2**, not embeddings. Each chunk requires an LLM call to extract entities, and these run sequentially.

---

## Better Optimizations for Indexing Speed

### High Impact (address real bottleneck)

| Change | Current | Proposed | Impact |
|--------|---------|----------|--------|
| LLM Concurrency | 1 | 2-4 | **2-4x faster extraction** |
| Chunk Size | 512 | 1024 | **50% fewer LLM calls** |
| Parallelization Stagger | 0.5s | 0.0s | Faster parallel starts |

### Medium Impact (embedding-related)

| Change | Current | Proposed | Impact |
|--------|---------|----------|--------|
| Batch Embeddings | Individual | Batches of 32 | Fewer API roundtrips |
| Int8 Quantization | None | Int8 | 4x smaller storage |
| Embedding Cache | None | Redis/disk | Skip duplicate texts |

### Low Impact

| Change | Current | Proposed | Impact |
|--------|---------|----------|--------|
| async_mode | threaded | asyncio | Minor I/O improvement |

---

## Implementation Approach (if proceeding)

### Option A: Quantize at Storage Time
Modify `graphrag_pipelines_patched.py` to quantize before storing:

```python
from sentence_transformers.quantization import quantize_embeddings

# After getting embeddings from Ollama
embeddings = get_embeddings_from_ollama(texts)

# Quantize before storing
int8_embeddings = quantize_embeddings(
    embeddings,
    precision="int8",
    calibration_embeddings=calibration_set  # Required!
)

# Store int8 to parquet
store_to_lancedb(int8_embeddings)
```

**Requires:**
- Calibration dataset (corpus sample for range calculation)
- Modify GraphRAG's internal embedding storage
- Update retrieval to handle int8

### Option B: Use Embedding Model with Native Quantization
Some models support int8 natively:
- `mixedbread-ai/mxbai-embed-large-v1` - Excellent int8 support
- Current `bge-m3` - Unknown int8 compatibility

### Option C: LanceDB Native Quantization
LanceDB may support quantization directly - needs investigation.

---

## Recommendation

### For Indexing Speed: Focus on LLM bottleneck first

1. **Increase `concurrent_requests` to 2-4** in `graphrag_settings.yaml`
2. **Increase `chunks.size` to 1024** (fewer chunks = fewer LLM calls)
3. **Reduce `parallelization.stagger` to 0.0**

Expected improvement: **2-4x faster indexing**

### For Storage/Retrieval: Consider int8 later

Int8 quantization is worthwhile but secondary:
- Implement after fixing LLM bottleneck
- Requires calibration dataset
- Test accuracy with bge-m3 first (not all models quantize well)

---

## Code References

- Embedding config: `graphrag_settings.yaml` (lines 15-22)
- Embedding usage: `graphrag_pipelines_patched.py` (lines 252-277)
- LanceDB storage: `graphrag_pipelines_patched.py` (lines 228-236)
- Current bottleneck: `concurrent_requests: 1` in settings

## External References

- [HuggingFace Embedding Quantization Blog](https://huggingface.co/blog/embedding-quantization)
- [Sentence Transformers Quantization](https://sbert.net/examples/applications/embedding-quantization/)
