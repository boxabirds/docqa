#!/usr/bin/env python3
"""Direct GraphRAG chat - bypasses the broken UI.

Usage from host:
  docker exec kotaemon python /app/tests/graphrag_chat.py "What is Credo?"
  docker exec kotaemon python /app/tests/graphrag_chat.py "Is Cadent cost of heat failures in scope?"
"""

import sys
import os
sys.path.insert(0, '/app')
os.chdir('/app')

from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import declarative_base
from ktem.db.models import engine
from ktem.index.file.graph.pipelines import GraphRAGRetrieverPipeline
from openai import OpenAI


def get_file_id():
    """Get first file_id from the Credo4 GraphRAG index."""
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT source_id FROM index__4__index WHERE relation_type='graph' LIMIT 1"
        ))
        row = result.fetchone()
        return row[0] if row else None


def chat(question: str) -> str:
    """Query GraphRAG and generate response."""
    Base = declarative_base()

    class Index4Index(Base):
        __tablename__ = 'index__4__index'
        id = Column(Integer, primary_key=True)
        source_id = Column(String)
        target_id = Column(String)
        relation_type = Column(String)
        user = Column(String)

    file_id = get_file_id()
    if not file_id:
        return "Error: No GraphRAG index found"

    # Run GraphRAG retrieval
    pipeline = GraphRAGRetrieverPipeline(Index=Index4Index, file_ids=[file_id])
    docs = pipeline.run(question)

    # Build context from retrieved docs
    context = ""
    for doc in docs:
        if doc.metadata.get('type') != 'plot':
            header = doc.metadata.get('file_name', '')
            text = doc.text[:3000]
            context += f"{header}\n{text}\n\n"

    # Generate response
    client = OpenAI(base_url='http://ollama:11434/v1', api_key='ollama')
    response = client.chat.completions.create(
        model='qwen2.5:14b',
        messages=[
            {
                'role': 'system',
                'content': 'Answer the question based on the knowledge graph context. Be direct and concise.'
            },
            {
                'role': 'user',
                'content': f'{context}\n\nQuestion: {question}'
            }
        ],
        max_tokens=500
    )

    return response.choices[0].message.content


if __name__ == '__main__':
    question = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'What is Credo?'
    print(f"Q: {question}")
    print(f"\nA: {chat(question)}")
