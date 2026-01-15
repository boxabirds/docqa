#!/usr/bin/env python3
"""
LFM2-Extract Adapter for GraphRAG Entity Extraction

Converts between formats:
- GraphRAG expects: ("entity"<|>NAME<|>TYPE<|>DESCRIPTION)
- LFM2-Extract outputs: JSON structured data

This adapter ONLY handles entity extraction requests.
Other pipeline stages (community reports, summarization) are configured
in graphrag_settings.yaml to go directly to their respective models.

Run as: uvicorn lfm2_adapter:app --host 0.0.0.0 --port 8002
"""

import json
import re
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

# LFM2-Extract for entity extraction
VLLM_LFM2_URL = "http://vllm-llm:8000/v1/chat/completions"

# Schema to request from LFM2-Extract
ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Entity name"},
                    "type": {"type": "string", "description": "Entity type (e.g., PERSON, ORGANIZATION, LOCATION, EVENT, CONCEPT)"},
                    "description": {"type": "string", "description": "Brief description of the entity"}
                },
                "required": ["name", "type", "description"]
            }
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source entity name"},
                    "target": {"type": "string", "description": "Target entity name"},
                    "description": {"type": "string", "description": "Description of the relationship"},
                    "strength": {"type": "integer", "description": "Relationship strength 1-10"}
                },
                "required": ["source", "target", "description", "strength"]
            }
        }
    },
    "required": ["entities", "relationships"]
}


def is_followup_prompt(messages: list) -> bool:
    """Check if this is a GraphRAG follow-up prompt asking for missed entities.

    GraphRAG sends follow-up prompts like "MANY entities and relationships were missed"
    with no real text to analyze. Returning empty prevents hallucination.
    """
    if not messages:
        return False

    all_content = ""
    for msg in messages:
        all_content += msg.get("content", "") + " "
    all_lower = all_content.lower()

    return "many entities and relationships were missed" in all_lower


def extract_real_text(user_msg: str) -> str:
    """Extract just the real text from GraphRAG prompt, stripping examples.

    GraphRAG prompts have format:
    ... examples ...
    -Real Data-
    ... actual text to analyze ...
    """
    # Look for "Real Data" marker - the structure is:
    # ... examples ...
    # -Real Data-
    # Entity_types: ...
    # Text:
    # <actual text>
    if "-Real Data-" in user_msg:
        # Split at -Real Data-
        after_marker = user_msg.split("-Real Data-", 1)[1]

        # Look for "Text:" or "Text:\n" after the marker
        if "Text:" in after_marker:
            text_part = after_marker.split("Text:", 1)[1]
            # Clean up any trailing markers
            for end_marker in ["######################", "Output:", "<|COMPLETE|>"]:
                if end_marker in text_part:
                    text_part = text_part.split(end_marker)[0]
            result = text_part.strip()
            if result:
                print(f"[ADAPTER] Extracted real text ({len(result)} chars): {result[:200]}...")
                return result

        # No Text: marker, use everything after -Real Data-
        result = after_marker.strip()
        if result:
            print(f"[ADAPTER] Extracted after -Real Data- ({len(result)} chars): {result[:200]}...")
            return result

    # No markers found - return as-is
    print(f"[ADAPTER] No markers found, using full message ({len(user_msg)} chars): {user_msg[:200]}...")
    return user_msg


def convert_prompt_for_lfm2(messages: list) -> list:
    """Convert GraphRAG prompt to LFM2-Extract format.

    Key insight from POC testing: LFM2-1.2B hallucinates when given
    CSV-formatted examples from GraphRAG. Solution is to:
    1. Strip all examples
    2. Extract only the real text
    3. Use explicit "ONLY from this text" instruction
    """
    # GraphRAG puts examples in system message, real data either in system or user
    system_msg = ""
    user_msg = ""
    for msg in messages:
        if msg.get("role") == "system":
            system_msg = msg.get("content", "")
        elif msg.get("role") == "user":
            user_msg = msg.get("content", "")

    # GraphRAG puts the full prompt in the user message (system is empty)
    # Try user message first, then fall back to system
    combined = user_msg + "\n" + system_msg
    real_text = extract_real_text(combined)

    # If extraction failed, use raw user message as last resort
    if not real_text:
        real_text = user_msg if user_msg else system_msg

    print(f"[ADAPTER] Final text to analyze ({len(real_text)} chars): {real_text[:200]}...")

    # Create clean prompt without examples - include scope/constraint extraction
    new_messages = [
        {
            "role": "system",
            "content": """Extract entities from the USER TEXT ONLY. Follow these rules:
1. Only extract entities explicitly named in the user's text
2. Include scope constraints in description (e.g., "out of scope", "no data available")
3. Output valid JSON: {"entities": [{"name": "...", "type": "...", "description": "..."}], "relationships": []}
4. Do NOT hallucinate entities not in the text"""
        },
        {
            "role": "user",
            "content": f"USER TEXT:\n{real_text}\n\nExtract entities from the above text only."
        }
    ]
    return new_messages


def convert_json_to_graphrag(json_response: dict, original_text: str = "") -> str:
    """Convert LFM2-Extract JSON to GraphRAG text format.

    GraphRAG uses these delimiters:
    - tuple_delimiter: <|>  (between fields in a tuple)
    - record_delimiter: ##  (between records)
    - completion_delimiter: <|COMPLETE|>  (at the end)
    """
    records = []

    entities = json_response.get("entities", [])
    relationships = json_response.get("relationships", [])

    for entity in entities:
        # Handle both LFM2-Extract format (entity_name) and our requested format (name)
        name = entity.get("entity_name", entity.get("name", "")).upper()
        etype = entity.get("entity_type", entity.get("type", "UNKNOWN")).upper()
        desc = entity.get("entity_description", entity.get("description", ""))
        if name:
            records.append(f'("entity"<|>{name}<|>{etype}<|>{desc})')

    # Process structured relationships
    for rel in relationships:
        if isinstance(rel, str):
            continue
        # Handle multiple field naming conventions from different LFM2 outputs
        source = (
            rel.get("source_entity") or
            rel.get("source") or
            rel.get("entity1") or  # LFM2 sometimes uses entity1/entity2
            ""
        ).upper()
        target = (
            rel.get("target_entity") or
            rel.get("target") or
            rel.get("entity2") or  # LFM2 sometimes uses entity1/entity2
            ""
        ).upper()
        desc = rel.get("relationship_description", rel.get("description", ""))
        strength = rel.get("relationship_strength", rel.get("strength", 5))
        if source and target and source != target:  # Avoid self-loops
            records.append(f'("relationship"<|>{source}<|>{target}<|>{desc}<|>{strength})')

    # Join with record delimiter and add completion delimiter
    output = "##".join(records)
    if output:
        output += "<|COMPLETE|>"
    return output


def extract_json_from_response(text: str) -> dict:
    """Extract JSON from LFM2 response, handling truncated/incomplete JSON."""
    # Try to find JSON in code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*)', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)

    # Find the start of JSON
    start = text.find('{')
    if start < 0:
        return {"entities": [], "relationships": []}

    text = text[start:]

    # Try to parse as-is first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to repair truncated JSON by closing arrays and braces
    # This handles cases where output was cut off mid-generation
    repaired = text.rstrip()

    # Close any unclosed strings
    if repaired.count('"') % 2 == 1:
        repaired += '"'

    # Try to close arrays and objects
    for _ in range(5):  # Try multiple closing attempts
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            # Add closing brackets based on what's missing
            if "Expecting ',' or ']'" in str(e) or "Expecting value" in str(e):
                # Likely in an array, close it
                repaired = repaired.rstrip(',') + ']}'
            elif "Expecting ',' or '}'" in str(e):
                # Close the object
                repaired = repaired.rstrip(',') + '}'
            elif "Expecting ':'" in str(e):
                # Truncated key, remove it
                repaired = re.sub(r'"[^"]*$', '', repaired) + ']}'
            else:
                repaired += '}]}'

    # Last resort: extract what we can with regex
    entities = []
    entity_pattern = r'"(?:entity_)?name":\s*"([^"]+)"[^}]*"(?:entity_)?type":\s*"([^"]+)"[^}]*"(?:entity_)?description":\s*"([^"]*)"'
    for match in re.finditer(entity_pattern, text):
        entities.append({
            "entity_name": match.group(1),
            "entity_type": match.group(2),
            "entity_description": match.group(3)
        })

    if entities:
        return {"entities": entities, "relationships": []}

    return {"entities": [], "relationships": []}


def is_entity_extraction_prompt(messages: list) -> bool:
    """Detect if this is a GraphRAG entity extraction prompt.

    Entity extraction prompts contain specific markers like "-Real Data-"
    or example entity tuples. Other prompts (summarization, community reports)
    should be passed through without conversion.
    """
    all_content = ""
    for msg in messages:
        all_content += msg.get("content", "") + " "

    # Entity extraction markers
    entity_markers = [
        "-Real Data-",
        "Entity_types:",
        '("entity"<|>',
        "extract entities",
        "entity extraction",
    ]

    return any(marker.lower() in all_content.lower() for marker in entity_markers)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Chat completion endpoint - handles entity extraction and passthrough."""
    body = await request.json()
    messages = body.get("messages", [])

    # Check for GraphRAG follow-up prompts ("did you miss anything?")
    # These should return empty to avoid hallucination
    if is_followup_prompt(messages):
        print("[ADAPTER] Returning empty result for follow-up prompt")
        return {
            "id": "followup-empty",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "<|COMPLETE|>"},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

    # Check if this is an entity extraction prompt
    if not is_entity_extraction_prompt(messages):
        # Non-entity prompt (e.g., summarization) - pass through to LFM2 directly
        print("[ADAPTER] Non-entity prompt - passing through to LFM2")
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(VLLM_LFM2_URL, json=body)
            return response.json()

    # Entity extraction - convert prompt and format response
    adapted_messages = convert_prompt_for_lfm2(messages)
    # Extract the original text for scope post-processing
    original_text = ""
    for msg in adapted_messages:
        if msg.get("role") == "user":
            original_text = msg.get("content", "")
            break
    body["messages"] = adapted_messages

    # Call LFM2 for entity extraction
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(VLLM_LFM2_URL, json=body)
        result = response.json()

    # Extract and convert the response
    if "choices" in result and result["choices"]:
        content = result["choices"][0].get("message", {}).get("content", "")
        json_data = extract_json_from_response(content)
        graphrag_format = convert_json_to_graphrag(json_data, original_text)

        # Log for debugging
        print(f"[ADAPTER] Raw LFM2 output: {content[:500]}")
        print(f"[ADAPTER] Parsed JSON: {json_data}")
        print(f"[ADAPTER] GraphRAG format: {graphrag_format[:500]}")

        # Replace content with GraphRAG format
        result["choices"][0]["message"]["content"] = graphrag_format

    return result


@app.get("/v1/models")
async def list_models():
    """Proxy models endpoint."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get("http://vllm-llm:8000/v1/models")
        return response.json()


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
