"""FastAPI backend for DocQA - PostgreSQL + pgvector based retrieval.

Standalone backend that queries PostgreSQL directly for GraphRAG data.
No longer depends on Kotaemon.
"""
import json
import os
from datetime import datetime
from typing import AsyncGenerator, Optional
from uuid import UUID

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
    conversation_id: Optional[str] = None  # Optional conversation for context


class Collection(BaseModel):
    id: int
    name: str
    type: str


class ConversationCreate(BaseModel):
    collection_id: int
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: str


class Message(BaseModel):
    id: str
    role: str
    content: str
    sources: Optional[list] = None
    created_at: datetime


class Conversation(BaseModel):
    id: str
    collection_id: Optional[int]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: Optional[list[Message]] = None


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


# ============================================================
# Conversations CRUD
# ============================================================

@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new conversation."""
    result = await db.execute(
        text("""
            INSERT INTO conversations (collection_id, title)
            VALUES (:collection_id, :title)
            RETURNING id, collection_id, title, created_at, updated_at
        """),
        {"collection_id": request.collection_id, "title": request.title}
    )
    row = result.fetchone()
    await db.commit()

    return Conversation(
        id=str(row.id),
        collection_id=row.collection_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.get("/api/conversations", response_model=list[Conversation])
async def list_conversations(
    collection_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """List conversations, optionally filtered by collection."""
    if collection_id:
        result = await db.execute(
            text("""
                SELECT id, collection_id, title, created_at, updated_at
                FROM conversations
                WHERE collection_id = :collection_id
                ORDER BY updated_at DESC
            """),
            {"collection_id": collection_id}
        )
    else:
        result = await db.execute(
            text("""
                SELECT id, collection_id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
            """)
        )

    return [
        Conversation(
            id=str(row.id),
            collection_id=row.collection_id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in result.fetchall()
    ]


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a conversation with its messages."""
    # Get conversation
    result = await db.execute(
        text("""
            SELECT id, collection_id, title, created_at, updated_at
            FROM conversations
            WHERE id = :id
        """),
        {"id": conversation_id}
    )
    conv_row = result.fetchone()

    if not conv_row:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get messages
    result = await db.execute(
        text("""
            SELECT id, role, content, sources, created_at
            FROM messages
            WHERE conversation_id = :conversation_id
            ORDER BY created_at ASC
        """),
        {"conversation_id": conversation_id}
    )

    messages = [
        Message(
            id=str(row.id),
            role=row.role,
            content=row.content,
            sources=row.sources,
            created_at=row.created_at,
        )
        for row in result.fetchall()
    ]

    return Conversation(
        id=str(conv_row.id),
        collection_id=conv_row.collection_id,
        title=conv_row.title,
        created_at=conv_row.created_at,
        updated_at=conv_row.updated_at,
        messages=messages,
    )


@app.patch("/api/conversations/{conversation_id}", response_model=Conversation)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a conversation (rename)."""
    result = await db.execute(
        text("""
            UPDATE conversations
            SET title = :title
            WHERE id = :id
            RETURNING id, collection_id, title, created_at, updated_at
        """),
        {"id": conversation_id, "title": request.title}
    )
    row = result.fetchone()
    await db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return Conversation(
        id=str(row.id),
        collection_id=row.collection_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a conversation and its messages."""
    result = await db.execute(
        text("DELETE FROM conversations WHERE id = :id RETURNING id"),
        {"id": conversation_id}
    )
    row = result.fetchone()
    await db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"status": "deleted", "id": conversation_id}


@app.post("/api/chat")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Stream chat response using SSE.

    1. Load conversation history if conversation_id provided
    2. Retrieve relevant context from PostgreSQL using vector search
    3. Build prompt with history + context
    4. Stream LLM response
    5. Save messages to database
    """
    # Load conversation history if provided
    history_messages = []
    if request.conversation_id:
        result = await db.execute(
            text("""
                SELECT role, content FROM messages
                WHERE conversation_id = :conversation_id
                ORDER BY created_at ASC
                LIMIT 10
            """),
            {"conversation_id": request.conversation_id}
        )
        history_messages = [{"role": row.role, "content": row.content} for row in result.fetchall()]

    # We need to collect data during streaming for saving later
    sources_data = []
    full_response = []

    async def generate() -> AsyncGenerator[str, None]:
        nonlocal sources_data, full_response

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

            # Retrieve context for current query
            context = await retriever.retrieve(
                query=request.message,
                collection_id=request.collection_id,
            )

            # Format sources for frontend with page numbers
            sources = []
            for tu in context.text_units:
                doc_ids = tu.get("document_ids") or []
                if isinstance(doc_ids, str):
                    doc_ids = [doc_ids]
                file_id = doc_ids[0] if doc_ids else None

                sources.append({
                    "file_id": file_id,
                    "file_name": tu.get("source_file") or "Unknown",
                    "page_number": tu.get("page_start"),
                    "page_end": tu.get("page_end"),
                    "text_snippet": tu.get("text", "")[:300],
                    "relevance_score": tu.get("similarity", 0),
                })

            # Add entity sources
            for entity in context.entities[:5]:
                sources.append({
                    "file_id": None,
                    "file_name": f"Entity: {entity.get('name', '')}",
                    "page_number": None,
                    "text_snippet": entity.get("description", "")[:300],
                    "relevance_score": entity.get("similarity", 0),
                })

            sources_data = sources
            yield f"data: {json.dumps({'type': 'info', 'sources': sources})}\n\n"

            # Build prompt context
            prompt_context = context.to_prompt_context()

            if not prompt_context.strip():
                yield f"data: {json.dumps({'type': 'error', 'error': 'No context found for this collection'})}\n\n"
                return

            # Build messages array with system prompt, history, and current query
            system_prompt = """You are a document analyst. Answer questions based on the provided context.
Be precise. Quote relevant passages when answering.
Use the conversation history for context about previous questions."""

            messages = [{"role": "system", "content": system_prompt}]

            # Add conversation history (without re-adding context each time)
            for msg in history_messages:
                messages.append(msg)

            # Add current query with fresh context
            messages.append({
                "role": "user",
                "content": f"CONTEXT:\n{prompt_context}\n\n---\nQUESTION: {request.message}"
            })

            # Stream LLM response
            response = llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                max_tokens=1000,
                stream=True,
            )

            for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response.append(content)
                    yield f"data: {json.dumps({'type': 'chat', 'content': content})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    async def generate_and_save():
        """Wrapper that saves messages after streaming completes."""
        async for chunk in generate():
            yield chunk

        # Save messages to database if conversation_id provided
        if request.conversation_id and full_response:
            try:
                # Save user message
                await db.execute(
                    text("""
                        INSERT INTO messages (conversation_id, role, content)
                        VALUES (:conversation_id, 'user', :content)
                    """),
                    {"conversation_id": request.conversation_id, "content": request.message}
                )

                # Save assistant response with sources
                await db.execute(
                    text("""
                        INSERT INTO messages (conversation_id, role, content, sources)
                        VALUES (:conversation_id, 'assistant', :content, :sources)
                    """),
                    {
                        "conversation_id": request.conversation_id,
                        "content": "".join(full_response),
                        "sources": json.dumps(sources_data) if sources_data else None,
                    }
                )

                # Update conversation timestamp
                await db.execute(
                    text("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                    {"id": request.conversation_id}
                )

                await db.commit()
            except Exception as e:
                # Log but don't fail the response
                print(f"Error saving messages: {e}")

    return StreamingResponse(
        generate_and_save(),
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
