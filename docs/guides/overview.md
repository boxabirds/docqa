# GraphRAG Technical Overview

This guide explains how the GraphRAG retrieval system works, from indexing to query-time retrieval.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     INDEXING TIME (GraphRAG)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Documents → Chunks → LLM extracts → ENTITIES + RELATIONSHIPS   │
│                              │                                  │
│                              ▼                                  │
│                    Build Knowledge Graph                        │
│                              │                                  │
│                              ▼                                  │
│               Leiden Algorithm clusters entities                │
│                              │                                  │
│                              ▼                                  │
│                    COMMUNITIES (clusters)                       │
│                              │                                  │
│                              ▼                                  │
│           LLM generates COMMUNITY REPORTS (summaries)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      QUERY TIME (retriever)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Query → Vector search → ENTITIES                               │
│                              │                                  │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│         text_unit_ids   relationships    community              │
│              │               │               │                  │
│              ▼               ▼               ▼                  │
│         TEXT_UNITS     RELATIONSHIPS    COMMUNITY_REPORTS       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## What GraphRAG Provides vs Basic RAG

| Component | Basic RAG | GraphRAG |
|-----------|-----------|----------|
| Text chunks | Direct vector search | Via entity links |
| Entity extraction | No | "CADENT is an organization" |
| Relationships | No | "CADENT → provides data to → CREDO" |
| Community summaries | No | "This cluster covers UK gas infrastructure..." |

## Retrieval Algorithm

### Step 1: Embed the Query

```python
query = "Is Cadent cost of failure in scope?"
query_embedding = embed(query)  # → 1024-dim vector via BGE-M3
```

The embedding model (BAAI/bge-m3) maps text to 1024-dimensional vectors where semantically similar text points in similar directions.

### Step 2: Vector Search on Entities (pgvector)

```sql
SELECT id, name, type, description, text_unit_ids,
       1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
FROM entities
WHERE collection_id = :collection_id
  AND embedding IS NOT NULL
ORDER BY embedding <=> CAST(:query_embedding AS vector)
LIMIT 10
```

The `<=>` operator is pgvector's **cosine distance**:
- `cosine_distance = 1 - cosine_similarity`
- `ORDER BY embedding <=> query` returns most similar first (smallest distance)

**What's stored in `entities.embedding`?**

During GraphRAG indexing, each entity's **description** was embedded:

| name | description | embedding |
|------|-------------|-----------|
| CADENT | Gas distribution network operator, partner in CReDO | [0.045, -0.123, ...] |
| COST_OF_FAILURE | Economic metric measuring financial impact | [0.012, 0.089, ...] |
| MVP_SCOPE | Initial release features for CReDO Digital Twin | [-0.034, 0.156, ...] |

Entities are found by matching their **descriptions**, not their names.

### Step 3: Get Candidate Text Units

```python
# Collect all text_unit_ids from found entities
candidate_text_units = await self._get_text_units_for_entities(entities)
```

Each entity has a `text_unit_ids` array linking to the source chunks where it appears.

### Step 4: Re-rank Text Units by Query Similarity

This is the key step that matches Kotaemon's `LocalSearchMixedContext`:

```python
async def _rank_text_units_by_query(candidates, query_embedding, max_tokens=4000):
    scored = []
    for tu in candidates:
        # Embed text unit at query time
        tu_embedding = await embed(tu["text"])
        # Cosine similarity
        similarity = cosine_similarity(query_embedding, tu_embedding)
        scored.append((similarity, tu))

    # Sort by similarity descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Select top units within token budget
    selected = []
    total_tokens = 0
    for similarity, tu in scored:
        if total_tokens + tu.tokens > max_tokens:
            break
        selected.append(tu)
        total_tokens += tu.tokens

    return selected
```

**Why this matters**: Without re-ranking, ALL text units linked to found entities are returned, including irrelevant ones. Re-ranking filters to only the chunks semantically similar to the query.

### Step 5: Get Relationships

```sql
SELECT source, target, description, weight
FROM relationships
WHERE collection_id = :collection_id
  AND (source = ANY(:entity_names) OR target = ANY(:entity_names))
ORDER BY weight DESC
LIMIT 20
```

### Step 6: Get Community Reports

```python
# Look up which communities the found entities belong to
entity_communities = await self._get_communities_for_entities(entity_ids)

# Get reports for those specific communities
community_reports = await self._get_community_reports_for_communities(
    collection_id, entity_communities, top_k=3
)
```

This connects community reports to the query via entities, rather than just returning top-ranked reports globally.

## Cosine Similarity

The similarity metric used throughout:

```
                  A · B           Σ(aᵢ × bᵢ)
similarity = ─────────── = ───────────────────────
              ||A|| ||B||   √Σ(aᵢ²) × √Σ(bᵢ²)
```

Returns value between -1 and 1:
- **1.0** = identical direction (highly relevant)
- **0.0** = orthogonal (unrelated)
- **-1.0** = opposite (rare in practice)

## Example: Query Processing

```
Query: "Is Cadent cost of failure in scope?"
         ↓
Step 1: Embed query → [0.023, -0.145, 0.089, ...]
         ↓
Step 2: Entity search finds:
        - CADENT (similarity: 0.78)
        - COST_OF_FAILURE (similarity: 0.72)
        - MVP_SCOPE (similarity: 0.65)
         ↓
Step 3: Get ALL text_units linked to these entities (15+ chunks)
         ↓
Step 4: Re-rank by query similarity:
        - "Cadent CoF is out of scope for MVP..." (0.82) ✓
        - "UKPN cost of failure calculations..." (0.71) ✓
        - "Asset failures displayed in table..." (0.45) ✓
        - "NGT provides synthetic data..." (0.31) ✗ (cut by budget)
         ↓
Step 5: Get relationships involving CADENT, COST_OF_FAILURE, MVP_SCOPE
         ↓
Step 6: Get community reports for entity communities
         ↓
Return: RetrievedContext(entities, relationships, text_units, community_reports)
```

## Database Schema

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `collections` | Document sets | id, name |
| `documents` | Source PDFs | id, collection_id, title |
| `entities` | Graph nodes | id, name, type, description, embedding, text_unit_ids |
| `relationships` | Graph edges | source, target, description, weight |
| `text_units` | Text chunks | id, text, n_tokens |
| `nodes` | Entity metadata | id, community, level, degree |
| `communities` | Entity clusters | id, community, level |
| `community_reports` | LLM summaries | id, community, title, summary, full_content, rank |

## Embedding Service

The retriever uses BGE-M3 for embeddings, trying Ollama first then falling back to vLLM:

```python
class EmbeddingService:
    async def embed(self, text: str) -> list[float]:
        # Try Ollama first
        try:
            response = await client.post(f"{ollama_url}/embeddings", ...)
            return response["data"][0]["embedding"]
        except:
            pass

        # Fall back to vLLM
        response = await client.post(f"{vllm_url}/embeddings", ...)
        return response["data"][0]["embedding"]
```

## Configuration

Retrieval parameters in `RetrievalConfig`:

```python
@dataclass
class RetrievalConfig:
    top_k_text_units: int = 10      # Max text units to return
    top_k_entities: int = 10         # Entities from vector search
    top_k_relationships: int = 20    # Related relationships
    top_k_community_reports: int = 3 # Community summaries
```

Token budget for text unit selection: 4000 tokens (configurable in `_rank_text_units_by_query`).
