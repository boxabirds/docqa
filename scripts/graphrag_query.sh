#!/bin/bash
# Query GraphRAG directly
# Usage: ./graphrag_query.sh "What is Credo?"

QUERY="${1:-What is Credo?}"

docker exec kotaemon python -c "
import pandas as pd
from openai import OpenAI

client = OpenAI(base_url='http://ollama:11434/v1', api_key='ollama')

# Load entities
entities = pd.read_parquet('/app/ktem_app_data/user_data/files/graphrag/e818ff91-6532-41ca-8bd9-572499d1f76c/output/create_final_entities.parquet')

# Search for relevant entities (simple keyword match)
query_lower = '''$QUERY'''.lower()
keywords = [w for w in query_lower.split() if len(w) > 3]

# Find matching entities
matches = entities[entities['name'].str.lower().str.contains('|'.join(keywords), na=False) |
                   entities['description'].str.lower().str.contains('|'.join(keywords), na=False)]

# Build context
context = 'Relevant entities from knowledge graph:\n\n'
for _, row in matches.head(8).iterrows():
    desc = str(row['description'])[:500] if pd.notna(row['description']) else ''
    context += f'''Entity: {row[\"name\"]}
Type: {row[\"type\"]}
Description: {desc}

'''

# Query LLM
response = client.chat.completions.create(
    model='qwen2.5:14b',
    messages=[
        {'role': 'system', 'content': 'Answer the question based on the knowledge graph context provided. Be concise and factual.'},
        {'role': 'user', 'content': f'{context}\nQuestion: $QUERY'}
    ],
    max_tokens=500
)
print(response.choices[0].message.content)
"
