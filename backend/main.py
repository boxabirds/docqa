"""FastAPI backend for DocQA - PostgreSQL + pgvector based retrieval.

Standalone backend that queries PostgreSQL directly for GraphRAG data.
No longer depends on Kotaemon.
"""
import json
import os
from typing import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from openai import OpenAI

from .database import get_db
from .retriever import GraphRAGRetriever, RetrievalConfig

app = FastAPI(title="DocQA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# vLLM client for LLM inference (Qwen2.5-7B)
llm_client = OpenAI(
    base_url=os.getenv("VLLM_CHAT_URL", "http://vllm-chat:8000/v1"),
    api_key="not-needed"
)
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")


class ChatRequest(BaseModel):
    message: str
    collection_id: int = 1  # Default to first collection


class Collection(BaseModel):
    id: int
    name: str
    type: str


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/collections")
async def get_collections(db: AsyncSession = Depends(get_db)) -> list[Collection]:
    """List available collections from the database."""
    result = await db.execute(
        text("SELECT id, name FROM collections ORDER BY id")
    )
    collections = []
    for row in result.fetchall():
        collections.append(Collection(
            id=row[0],
            name=row[1],
            type="graphrag"
        ))
    return collections


@app.post("/api/chat")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Stream chat response using SSE.

    1. Retrieve relevant context from PostgreSQL using vector search
    2. Format context for LLM
    3. Stream LLM response via Ollama
    """

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # Initialize retriever
            retriever = GraphRAGRetriever(
                db=db,
                config=RetrievalConfig(
                    top_k_text_units=10,
                    top_k_entities=10,
                    top_k_relationships=20,
                    top_k_community_reports=3,
                )
            )

            # Retrieve context
            context = await retriever.retrieve(
                query=request.message,
                collection_id=request.collection_id,
            )

            # Format sources for frontend with page numbers
            sources = []
            for tu in context.text_units:
                # Get document IDs to look up file info
                doc_ids = tu.get("document_ids") or []
                if isinstance(doc_ids, str):
                    doc_ids = [doc_ids]

                # Use first document ID as file_id
                file_id = doc_ids[0] if doc_ids else None

                sources.append({
                    "file_id": file_id,
                    "file_name": tu.get("source_file") or "Unknown",
                    "page_number": tu.get("page_start"),
                    "page_end": tu.get("page_end"),
                    "text_snippet": tu.get("text", "")[:300],
                    "relevance_score": tu.get("similarity", 0),
                })

            # Add entity sources (different format)
            for entity in context.entities[:5]:
                sources.append({
                    "file_id": None,
                    "file_name": f"Entity: {entity.get('name', '')}",
                    "page_number": None,
                    "text_snippet": entity.get("description", "")[:300],
                    "relevance_score": entity.get("similarity", 0),
                })

            # Send sources first
            yield f"data: {json.dumps({'type': 'info', 'sources': sources})}\n\n"

            # Build prompt context
            prompt_context = context.to_prompt_context()

            if not prompt_context.strip():
                yield f"data: {json.dumps({'type': 'error', 'error': 'No context found for this collection'})}\n\n"
                return

            # Stream LLM response
            system_prompt = """You are a document analyst. Answer questions based on the provided context.
Be precise. Quote relevant passages when answering."""

            response = llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"CONTEXT:\n{prompt_context}\n\n---\nQUESTION: {request.message}"
                    }
                ],
                max_tokens=1000,
                stream=True,
            )

            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'type': 'chat', 'content': chunk.choices[0].delta.content})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/documents/{doc_id}/pdf")
async def get_pdf(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Serve PDF file for viewing in browser.

    Looks up the document by ID and returns the stored PDF file.
    """
    result = await db.execute(
        text("SELECT pdf_path, original_filename FROM documents WHERE id = :doc_id"),
        {"doc_id": doc_id}
    )
    row = result.fetchone()

    if not row or not row.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")

    pdf_path = Path(row.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing from storage")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=row.original_filename or pdf_path.name
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
