#!/usr/bin/env python3
"""Query GraphRAG knowledge graph directly.

Usage from host:
  ./tests/graphrag_query.sh "What is Credo?"
"""

import sys
import os
import pandas as pd
from openai import OpenAI

def find_latest_graphrag_job():
    base = '/app/ktem_app_data/user_data/files/graphrag'
    if not os.path.exists(base):
        return None
    jobs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    if not jobs:
        return None
    for job in sorted(jobs, key=lambda x: os.path.getmtime(os.path.join(base, x)), reverse=True):
        output_dir = os.path.join(base, job, 'output')
        if os.path.exists(os.path.join(output_dir, 'create_final_entities.parquet')):
            return output_dir
    return None

def query_graphrag(question: str, top_k: int = 8) -> str:
    client = OpenAI(base_url='http://ollama:11434/v1', api_key='ollama')

    output_dir = find_latest_graphrag_job()
    if not output_dir:
        return "Error: No GraphRAG job found with completed indexing"

    entities = pd.read_parquet(f'{output_dir}/create_final_entities.parquet')

    keywords = [w.lower() for w in question.split() if len(w) > 3]
    pattern = '|'.join(keywords) if keywords else question.lower()

    name_match = entities['name'].str.lower().str.contains(pattern, na=False, regex=True)
    desc_match = entities['description'].str.lower().str.contains(pattern, na=False, regex=True)
    matches = entities[name_match | desc_match].head(top_k)

    if len(matches) == 0:
        matches = entities.head(top_k)

    context = 'Knowledge graph entities:\n\n'
    for _, row in matches.iterrows():
        desc = str(row['description'])[:500] if pd.notna(row['description']) else 'N/A'
        context += f"Entity: {row['name']}\nType: {row['type']}\nDescription: {desc}\n\n"

    response = client.chat.completions.create(
        model='qwen2.5:14b',
        messages=[
            {'role': 'system', 'content': 'Answer based on the knowledge graph context. Be concise and factual.'},
            {'role': 'user', 'content': f'{context}\nQuestion: {question}'}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content

if __name__ == '__main__':
    question = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'What is Credo?'
    print(query_graphrag(question))
