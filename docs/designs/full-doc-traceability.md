# Full Document Traceability Design

## Goal
Enable full traceability from PDF page → chunk → GraphRAG entity/text_unit, allowing the UI to show source document names and jump to relevant pages.

## Current State

### What Works
- **Docling** already captures metadata during PDF parsing:
  - `page_label` - page number
  - `file_name` - original filename
  - `file_path` - full path
  - `type` - text/table/image

### Where Metadata Is Lost
In `graphrag_pipelines_patched.py`, the `write_docs_to_files` method discards metadata:

```python
def write_docs_to_files(self, graph_id: str, docs: list[Document]):
    for doc in docs:
        if doc.metadata.get("type", "text") == "text":
            with open(input_path / f"{doc.doc_id}.txt", "w") as f:
                f.write(doc.text)  # <-- Only writes text, loses metadata!
```

GraphRAG then indexes these plain text files, with no way to trace back to original PDF pages.

## Proposed Solution

### 1. Store Chunk Metadata During Indexing

Modify `GraphRAGIndexingPipeline.write_docs_to_files` to also store metadata:

```python
def write_docs_to_files(self, graph_id: str, docs: list[Document]):
    root_path, input_path = prepare_graph_index_path(graph_id)
    input_path.mkdir(parents=True, exist_ok=True)

    # Store metadata mapping
    metadata_map = {}

    for doc in docs:
        if doc.metadata.get("type", "text") == "text":
            with open(input_path / f"{doc.doc_id}.txt", "w") as f:
                f.write(doc.text)

            # Preserve metadata
            metadata_map[doc.doc_id] = {
                "file_name": doc.metadata.get("file_name"),
                "page_label": doc.metadata.get("page_label"),
                "file_path": str(doc.metadata.get("file_path", "")),
                "file_id": doc.metadata.get("file_id"),  # Kotaemon's internal ID
            }

    # Save metadata to JSON
    with open(root_path / "chunk_metadata.json", "w") as f:
        json.dump(metadata_map, f)

    return root_path
```

### 2. Match Text Units to Original Chunks

GraphRAG's `text_units` table contains the indexed text. We need to match these back to our original doc_ids.

Option A: **Fuzzy text matching** - Match text_unit content to original chunks
Option B: **Embed doc_id in text** - Prepend each chunk with a marker like `[DOC:abc123]`
Option C: **Use GraphRAG's document_ids field** - text_units may already track source document

Recommended: **Option B** - Most reliable, minimal overhead:

```python
# During indexing
with open(input_path / f"{doc.doc_id}.txt", "w") as f:
    f.write(f"[CHUNK_ID:{doc.doc_id}]\n{doc.text}")

# During retrieval - parse chunk ID from text_unit
import re
def extract_chunk_id(text: str) -> str | None:
    match = re.match(r'\[CHUNK_ID:([^\]]+)\]', text)
    return match.group(1) if match else None
```

### 3. Update Retrieval to Return Full Source Info

Modify `GraphRAGRetrieverPipeline.format_context_records`:

```python
def format_context_records(self, context_records, metadata_map: dict) -> list[RetrievedDocument]:
    sources = context_records.get("sources", [])

    docs = []
    for idx, row in sources.iterrows():
        text_unit_id, text = row["id"], row["text"]

        # Extract original chunk ID
        chunk_id = extract_chunk_id(text)
        chunk_meta = metadata_map.get(chunk_id, {})

        # Clean text (remove chunk ID marker)
        clean_text = re.sub(r'^\[CHUNK_ID:[^\]]+\]\n?', '', text)

        docs.append(RetrievedDocument(
            text=clean_text,
            metadata={
                "file_name": chunk_meta.get("file_name", "Unknown"),
                "page_label": chunk_meta.get("page_label", 1),
                "file_id": chunk_meta.get("file_id"),
                "type": "source",
            },
            score=1.0,
        ))

    return docs
```

### 4. Update Backend API Response

```python
# In backend/main.py
sources.append({
    "file_id": doc.metadata.get("file_id"),
    "file_name": doc.metadata.get("file_name", "Unknown"),
    "page_number": doc.metadata.get("page_label", 1),
    "text_snippet": doc.text[:500],
    "relevance_score": doc.score,
})
```

## Data Flow After Implementation

```
PDF Upload
    │
    ▼
Docling Parser
    │ extracts: text, page_label, file_name, file_path
    ▼
GraphRAG Indexing Pipeline
    │ writes: chunk text files + chunk_metadata.json
    ▼
GraphRAG Index
    │ creates: entities, relationships, text_units
    ▼
GraphRAG Retrieval
    │ returns: text_units with [CHUNK_ID:xxx] markers
    ▼
Metadata Lookup
    │ maps: chunk_id → {file_name, page_label, file_id}
    ▼
API Response
    │ returns: sources with full traceability
    ▼
Frontend
    │ displays: "Document.pdf, Page 5" with click-to-view
```

## Files to Modify

1. **`graphrag_pipelines_patched.py`**
   - `write_docs_to_files()` - Store metadata JSON
   - `format_context_records()` - Look up metadata, return full source info
   - `_build_graph_search()` - Load metadata map

2. **`backend/main.py`**
   - Update source format to match frontend expectations

3. **Frontend** (already implemented, just needs correct data)
   - `SourceItem.tsx` - Already handles `file_name`, `page_number`, `text_snippet`
   - `PdfViewer.tsx` - Already can open PDFs to specific pages

## Re-indexing Required

**Yes** - existing indexed collections don't have the metadata mapping. After implementing the changes:

1. Delete existing GraphRAG index data
2. Re-upload/re-index PDFs
3. New indexes will include traceability metadata

## Future Enhancements

- **Highlight text in PDF** - Store bbox coordinates, use PDF.js to highlight
- **Entity → Source mapping** - Show which pages contributed to each entity
- **Source confidence scores** - Weight sources by relevance to query
