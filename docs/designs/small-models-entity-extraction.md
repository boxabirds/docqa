# Small Models for Entity Extraction Research

## Problem
GraphRAG indexing takes 62+ minutes, with 99.7% of time spent on LLM entity extraction (727 sequential calls at 5.15s average using qwen2.5:14b).

## Goal
Find a smaller, faster model that excels at entity extraction to replace qwen2.5:14b for the GraphRAG indexing phase.

---

## Model Comparison

### Specialized Extraction Models

| Model | Size | Ollama | Specialty | Notes |
|-------|------|--------|-----------|-------|
| **[LFM2-1.2B-Extract](https://huggingface.co/LiquidAI/LFM2-1.2B-Extract)** | 1.2B | ✅ GGUF | Structured extraction (JSON/XML/YAML) | Outperforms Gemma 3 27B on extraction |
| **[LFM2-2.6B-Exp](https://huggingface.co/LiquidAI/LFM2-2.6B-Exp)** | 2.6B | ✅ GGUF | Data extraction, RAG, tool use | IFBench beats DeepSeek R1 (263x larger) |
| [GLiNER](https://github.com/urchade/GLiNER) | 50-300M | ❌ | NER only (encoder model) | Fastest, but not decoder-based |
| [UniversalNER-7B](https://universal-ner.github.io/) | 7B | ❓ | NER via instruction tuning | 84.78% F1 on 20 datasets |

### General Small Models (Entity Extraction Benchmarks)

| Model | Size | Ollama | Entity Extraction Score | Speed vs 14B |
|-------|------|--------|------------------------|--------------|
| **[Gemma 2B](https://ollama.com/library/gemma2)** | 2B | ✅ `gemma2:2b` | 9.7/10 (best overall) | ~7x faster |
| [Llama 3.2 3B](https://ollama.com/library/llama3.2) | 3B | ✅ `llama3.2:3b` | 7.5/10 (best for People) | ~5x faster |
| [Phi-3 Mini](https://ollama.com/library/phi3) | 3.8B | ✅ `phi3:mini` | High accuracy | ~4x faster |
| [Qwen2.5 3B](https://ollama.com/library/qwen2.5) | 3B | ✅ `qwen2.5:3b` | 6.0/10 | ~5x faster |
| [SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) | 3B | ✅ | Outperforms Llama 3.2 3B | ~5x faster |

---

## Top Recommendations

### 1. LFM2-1.2B-Extract (Best for Structured Extraction)

**Why:** Purpose-built for extracting structured data from unstructured text - exactly what GraphRAG needs.

- Outperforms Gemma 3 27B (22.5x larger) on extraction benchmarks
- Outputs JSON/XML/YAML natively
- 1.2B params = ~12x faster than qwen2.5:14b
- GGUF available for Ollama

**Estimated speedup:** 62 min → ~5 min

```bash
# To install (when GGUF available on Ollama)
ollama pull liquidai/lfm2-1.2b-extract
```

### 2. LFM2-2.6B-Exp (Best Balance)

**Why:** Excellent for data extraction + tool use, better reasoning than 1.2B.

- Specifically designed for RAG and data extraction
- Pure RL training improves instruction following
- 2.6B params = ~5x faster than qwen2.5:14b
- 32K context (matches current setup)

**Estimated speedup:** 62 min → ~12 min

### 3. Gemma 2B (Best General-Purpose Fallback)

**Why:** Highest accuracy in general entity extraction benchmarks, already in Ollama.

- 9.7/10 average score across entity types
- Well-tested, stable, production-ready
- 2B params = ~7x faster than qwen2.5:14b

**Estimated speedup:** 62 min → ~9 min

```bash
ollama pull gemma2:2b
```

---

## Implementation Approach

### Option A: Simple Model Swap (Low Risk)

Change `graphrag_settings.yaml`:

```yaml
llm:
  model: gemma2:2b  # Was: qwen2.5:14b
  # OR
  model: qwen2.5:3b  # Smaller Qwen, same family
```

**Pros:** Minimal changes, same GraphRAG prompts work
**Cons:** May need prompt tuning for smaller model

### Option B: Specialized Extraction Model (Higher Reward)

Use LFM2-1.2B-Extract with custom Modelfile:

```dockerfile
# Modelfile.lfm2-extract
FROM LiquidAI/LFM2-1.2B-Extract-GGUF:Q4_K_M
PARAMETER temperature 0
SYSTEM "Extract entities and relationships from the following text into JSON format."
```

```bash
ollama create lfm2-extract -f Modelfile.lfm2-extract
```

Then update `graphrag_settings.yaml`:
```yaml
llm:
  model: lfm2-extract
```

**Pros:** Purpose-built for extraction, potentially best quality
**Cons:** May need to adjust GraphRAG prompts for JSON output format

### Option C: Hybrid Approach

Use different models for different GraphRAG phases:
- **Entity extraction:** LFM2-1.2B-Extract (fast)
- **Summarization:** qwen2.5:14b (quality)
- **Query answering:** qwen2.5:14b (quality)

Requires modifying `graphrag_settings.yaml` to support multiple models.

---

## Expected Performance

| Model | Params | Est. Time/Call | Total (727 calls) | Speedup |
|-------|--------|----------------|-------------------|---------|
| qwen2.5:14b (current) | 14B | 5.15s | 62 min | 1x |
| **LFM2-1.2B-Extract** | 1.2B | ~0.4s | ~5 min | **12x** |
| **LFM2-2.6B-Exp** | 2.6B | ~1.0s | ~12 min | **5x** |
| **Gemma 2B** | 2B | ~0.7s | ~9 min | **7x** |
| qwen2.5:3b | 3B | ~1.0s | ~12 min | 5x |
| phi3:mini | 3.8B | ~1.2s | ~15 min | 4x |

---

## Quality Considerations

### Risks with Smaller Models
1. **Fewer entities extracted** - May miss subtle relationships
2. **Hallucinated entities** - Lower reasoning = more errors
3. **Format compliance** - May not follow GraphRAG's expected output format

### Mitigation
1. **Test on your corpus first** - Run side-by-side comparison
2. **Use extraction-specialized models** - LFM2-Extract designed for this
3. **Increase entity verification** - Post-process to filter hallucinations

---

## Verification Plan

1. **Baseline:** Current qwen2.5:14b extraction on CReDO corpus
   - Count entities extracted
   - Time total indexing
   - Check query quality

2. **Test:** Same corpus with candidate model
   - Compare entity count (should be ≥90% of baseline)
   - Measure speedup
   - Test same queries for quality

3. **Metrics:**
   - Entity recall: extracted_new / extracted_baseline
   - Query F1: Manual evaluation of 10 test queries
   - Speed: Total indexing time

---

## Sources

- [LFM2-1.2B-Extract](https://huggingface.co/LiquidAI/LFM2-1.2B-Extract)
- [LFM2-2.6B-Exp](https://huggingface.co/LiquidAI/LFM2-2.6B-Exp)
- [LFM2-2.6B-Exp-GGUF](https://huggingface.co/LiquidAI/LFM2-2.6B-Exp-GGUF)
- [Gemma 2B vs Llama 3.2 vs Qwen 7B Entity Extraction](https://www.analyticsvidhya.com/blog/2025/01/gemma-2b-vs-llama-3-2-vs-qwen-7b/)
- [UniversalNER](https://universal-ner.github.io/)
- [GLiNER GitHub](https://github.com/urchade/GLiNER)
- [Ollama Model Library](https://ollama.com/library)
