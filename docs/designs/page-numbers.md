# Source Page Linkages: Click Source → View PDF Page

## Goal
When a user clicks a source reference, open the actual PDF page in a viewer.

## Current State
- Sources display: ✅ Shows source cards with file name, snippet, relevance score
- PdfViewer component: ✅ Exists but shows placeholder "Page X content would be rendered here"
- Click handler: ✅ `openPdfViewer({id, name, page})` works
- **Page numbers**: ❌ Not stored - Docling captures them but they're lost during indexing
- **Original PDFs**: ❌ Not stored - only extracted text is kept
- **Backend sources format**: ❌ Returns `{title, content, score}` not `{file_id, file_name, page_number}`

## Architecture

```
PDF Input
    ↓
Docling Extraction (page_no in prov[0]["page_no"]) ← Page info EXISTS here
    ↓
OCR Stage writes .txt files ← Page info LOST here (no markers)
    ↓
GraphRAG chunking (512 tokens)
    ↓
text_units parquet (no page column)
    ↓
PostgreSQL (no page column)
```

## Implementation Plan

### Step 1: Store Original PDFs
**Files**: `indexer/stages/ocr.py`

Copy input PDFs to a persistent storage location during indexing:
```python
# In ocr.py after processing
pdf_storage = output_dir / "pdfs"
pdf_storage.mkdir(exist_ok=True)
shutil.copy(pdf_path, pdf_storage / pdf_path.name)
```

### Step 2: Insert Page Markers in Text Output
**Files**: `indexer/stages/ocr.py`, `docling_loader_patched.py`

When writing .txt files, insert page boundary markers:
```python
# Instead of just combining text
text_content = ""
for page_num, texts in page_number_to_text.items():
    text_content += f"\n<!-- PAGE {page_num} -->\n"
    text_content += "\n".join(texts)
```

### Step 3: Capture Page Numbers During Chunking
**Files**: `indexer/stages/graphrag.py` (or custom pre-processing)

Parse page markers when creating text_units:
```python
import re
def extract_page_numbers(text):
    # Find all page markers in the text chunk
    pages = re.findall(r'<!-- PAGE (\d+) -->', text)
    return [int(p) for p in pages] if pages else None
```

### Step 4: Schema Changes
**Files**: `backend/schema.sql`

```sql
-- Add to text_units table
ALTER TABLE text_units ADD COLUMN page_start INTEGER;
ALTER TABLE text_units ADD COLUMN page_end INTEGER;
ALTER TABLE text_units ADD COLUMN source_file VARCHAR(500);

-- Add documents storage
ALTER TABLE documents ADD COLUMN original_filename VARCHAR(500);
ALTER TABLE documents ADD COLUMN pdf_path VARCHAR(1000);
```

### Step 5: Update Import Script
**Files**: `backend/import_parquet.py`

Handle new page columns during parquet import.

### Step 6: Backend - Return Proper Source Format
**Files**: `backend/main.py`

Change source format from:
```python
{"title": "Text Unit", "content": text[:500], "score": 0.8}
```
To:
```python
{
    "file_id": document_id,
    "file_name": original_filename,
    "page_number": page_start,
    "text_snippet": text[:200],
    "relevance_score": similarity
}
```

### Step 7: Backend - Serve PDFs
**Files**: `backend/main.py`

Add endpoint to serve stored PDFs:
```python
@app.get("/api/documents/{doc_id}/pdf")
async def get_pdf(doc_id: str):
    # Return PDF file for viewing
    pdf_path = await get_pdf_path(doc_id)
    return FileResponse(pdf_path, media_type="application/pdf")
```

### Step 8: Frontend - PDF Viewer
**Files**: `frontend/src/components/sources/PdfViewer.tsx`

Replace placeholder with actual PDF rendering:
```typescript
import { Document, Page } from 'react-pdf';

// In PdfViewer component
<Document file={`/api/documents/${fileId}/pdf`}>
  <Page pageNumber={currentPage} />
</Document>
```

## Files to Modify

| File | Change |
|------|--------|
| `indexer/stages/ocr.py` | Copy PDFs, insert page markers |
| `docling_loader_patched.py` | Keep page info in output |
| `backend/schema.sql` | Add page columns |
| `backend/import_parquet.py` | Import page numbers |
| `backend/main.py` | New source format, PDF endpoint |
| `backend/retriever.py` | Include page info in results |
| `frontend/src/components/sources/PdfViewer.tsx` | Real PDF rendering |
| `frontend/package.json` | Add react-pdf dependency |

## Verification

1. **Re-index a collection** with page markers
2. **Query the collection** and check sources have page numbers
3. **Click a source** → PDF viewer opens at correct page
4. **Navigate pages** in viewer

## Dependencies to Add

```bash
# Frontend
npm install react-pdf
```

## Note

This requires **re-indexing** all collections to capture page numbers. Existing collections won't have page data until re-indexed.
