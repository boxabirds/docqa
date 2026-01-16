"""
GraphRAG Stage Runner

Runs GraphRAG indexing stages:
- Entity extraction
- Community reports
- Embeddings

Uses GraphRAG's CLI with selective workflow execution.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

import yaml

logger = logging.getLogger(__name__)

WorkflowName = Literal[
    "create_base_text_units",
    "create_base_extracted_entities",
    "create_summarized_entities",
    "create_base_entity_graph",
    "create_final_entities",
    "create_final_nodes",
    "create_final_communities",
    "create_final_relationships",
    "create_final_text_units",
    "create_final_community_reports",
    "create_base_documents",
    "create_final_documents",
]

# GraphRAG workflow dependencies
# To run a workflow, all its dependencies must have completed
WORKFLOW_DEPS: dict[WorkflowName, list[WorkflowName]] = {
    "create_base_text_units": [],
    "create_base_extracted_entities": ["create_base_text_units"],
    "create_summarized_entities": ["create_base_extracted_entities"],
    "create_base_entity_graph": ["create_summarized_entities"],
    "create_final_entities": ["create_base_entity_graph"],
    "create_final_nodes": ["create_final_entities"],
    "create_final_communities": ["create_final_nodes"],
    "create_final_relationships": ["create_base_entity_graph"],
    "create_final_text_units": ["create_final_entities", "create_final_relationships"],
    "create_final_community_reports": ["create_final_nodes", "create_final_relationships"],
    "create_base_documents": ["create_final_text_units"],
    "create_final_documents": ["create_base_documents"],
}

# Workflows for each pipeline stage
ENTITY_WORKFLOWS = [
    "create_base_text_units",
    "create_base_extracted_entities",
    "create_summarized_entities",
    "create_base_entity_graph",
    "create_final_entities",
    "create_final_nodes",
    "create_final_communities",
    "create_final_relationships",
    "create_final_text_units",
]

COMMUNITY_WORKFLOWS = [
    "create_final_community_reports",
]

EMBEDDING_WORKFLOWS = [
    # Embeddings are computed as part of create_final_entities
    # If we need standalone embedding, we'd need to modify GraphRAG
]

DOCUMENT_WORKFLOWS = [
    "create_base_documents",
    "create_final_documents",
]


def create_graphrag_settings(
    output_dir: Path,
    stage: Literal["entity", "community", "embedding"],
    api_key: str = "ollama",
) -> Path:
    """Create GraphRAG settings.yaml for a specific stage.

    Args:
        output_dir: Directory for GraphRAG output
        stage: Which stage we're running
        api_key: API key for LLM services

    Returns:
        Path to settings.yaml file
    """
    # Base settings - all stages share these
    settings = {
        "encoding_model": "cl100k_base",
        "skip_workflows": [],
        "chunks": {
            "size": 256,
            "overlap": 50,
            "group_by_columns": ["id"],
            "strategy": {
                "type": "sentence",
                "chunk_size": 256,
                "chunk_overlap": 50,
            },
        },
        "input": {
            "type": "file",
            "file_type": "text",
            "base_dir": "input",
            "file_pattern": ".*\\.txt$",
        },
        "parallelization": {
            "stagger": 0.1,
            "num_threads": 50,
        },
        "async_mode": "threaded",
    }

    # Stage-specific LLM configuration
    if stage == "entity":
        # Entity extraction uses LFM2 via adapter
        settings["llm"] = {
            "api_key": api_key,
            "type": "openai_chat",
            "api_base": "http://lfm2-adapter:8002/v1",
            "model": "LiquidAI/LFM2-1.2B-Extract",
            "model_supports_json": True,
            "request_timeout": 300.0,
            "concurrent_requests": 50,
            "max_tokens": 2000,
            "tokens_per_minute": 0,
            "requests_per_minute": 0,
        }
        settings["entity_extraction"] = {
            "llm": settings["llm"].copy(),
            "parallelization": {"stagger": 0.1, "num_threads": 50},
        }
        # Summarization during entity stage uses Qwen
        settings["summarize_descriptions"] = {
            "llm": {
                "api_key": api_key,
                "type": "openai_chat",
                "api_base": "http://vllm-chat:8000/v1",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "model_supports_json": True,
                "request_timeout": 300.0,
                "concurrent_requests": 25,
                "max_tokens": 1000,
            },
        }

    elif stage == "community":
        # Community reports use Qwen directly
        settings["llm"] = {
            "api_key": api_key,
            "type": "openai_chat",
            "api_base": "http://vllm-chat:8000/v1",
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "model_supports_json": True,
            "request_timeout": 300.0,
            "concurrent_requests": 25,
            "max_tokens": 2000,
            "tokens_per_minute": 0,
            "requests_per_minute": 0,
        }
        settings["community_reports"] = {
            "llm": settings["llm"].copy(),
        }

    elif stage == "embedding":
        # Embeddings use BGE-M3
        settings["llm"] = {
            "api_key": api_key,
            "type": "openai_chat",
            "api_base": "http://vllm-chat:8000/v1",  # Fallback
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "model_supports_json": True,
            "request_timeout": 300.0,
            "concurrent_requests": 25,
            "max_tokens": 1500,
        }

    # Embeddings config for all stages
    settings["embeddings"] = {
        "async_mode": "threaded",
        "llm": {
            "api_base": "http://vllm-embed:8000/v1",
            "api_key": api_key,
            "model": "BAAI/bge-m3",
            "type": "openai_embedding",
            "concurrent_requests": 25,
        },
    }

    # Write settings
    settings_file = output_dir / "settings.yaml"
    with open(settings_file, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)

    return settings_file


def run_graphrag_stage(
    stage: Literal["entity", "community", "embedding"],
    input_dir: Path,
    output_dir: Path,
    timeout: float = 7200.0,
) -> dict[str, Any]:
    """Run a GraphRAG indexing stage.

    Args:
        stage: Which stage to run
        input_dir: Directory containing input .txt files
        output_dir: Directory for GraphRAG output
        timeout: Max time for stage (seconds)

    Returns:
        Dict with stage results and stats
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up GraphRAG directory structure
    graphrag_dir = output_dir / "graphrag"
    graphrag_input = graphrag_dir / "input"
    graphrag_output = graphrag_dir / "output"

    graphrag_dir.mkdir(parents=True, exist_ok=True)
    graphrag_input.mkdir(parents=True, exist_ok=True)
    graphrag_output.mkdir(parents=True, exist_ok=True)

    # Copy/link input files
    input_dir = Path(input_dir)
    for txt_file in input_dir.glob("*.txt"):
        dest = graphrag_input / txt_file.name
        if not dest.exists():
            shutil.copy(txt_file, dest)

    # Determine which workflows to run
    if stage == "entity":
        workflows = ENTITY_WORKFLOWS
    elif stage == "community":
        workflows = COMMUNITY_WORKFLOWS
    elif stage == "embedding":
        workflows = EMBEDDING_WORKFLOWS
    else:
        workflows = []

    if not workflows:
        logger.warning(f"[GraphRAG] No workflows defined for stage: {stage}")
        return {"workflows": [], "stats": {}}

    logger.info(f"[GraphRAG] Running {stage} stage with {len(workflows)} workflows")

    # Set up environment
    env = os.environ.copy()
    env["GRAPHRAG_API_KEY"] = "ollama"

    # Step 1: Initialize GraphRAG project structure (only if not already done)
    settings_file = graphrag_dir / "settings.yaml"
    if not settings_file.exists():
        logger.info("[GraphRAG] Initializing project structure...")
        init_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "graphrag.index",
                "--root",
                str(graphrag_dir),
                "--init",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(graphrag_dir),
            env=env,
        )
        if init_result.returncode != 0:
            logger.error(f"[GraphRAG] Init failed: {init_result.stderr}")

        # Step 2: Copy the master settings.yaml (has all per-stage LLM configs)
        master_settings = Path("/app/graphrag_settings.yaml")
        if not master_settings.exists():
            # Fallback to local copy
            master_settings = Path(__file__).parent.parent.parent / "graphrag_settings.yaml"

        if master_settings.exists():
            logger.info(f"[GraphRAG] Copying settings from {master_settings}")
            shutil.copy(master_settings, settings_file)
        else:
            logger.warning("[GraphRAG] Master settings.yaml not found, using generated settings")
            create_graphrag_settings(graphrag_dir, stage)

    # Step 3: Run the actual indexing
    logger.info("[GraphRAG] Running indexing pipeline...")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphrag.index",
            "--root",
            str(graphrag_dir),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(graphrag_dir),
        env=env,
    )

    # Log output
    if result.stdout:
        for line in result.stdout.strip().split("\n")[-30:]:  # Last 30 lines
            logger.info(f"[GraphRAG] {line}")

    if result.stderr:
        for line in result.stderr.strip().split("\n")[-15:]:
            logger.warning(f"[GraphRAG] {line}")

    # Check for errors
    success = result.returncode == 0

    # Gather stats from output files
    stats = gather_graphrag_stats(graphrag_output)

    return {
        "success": success,
        "return_code": result.returncode,
        "workflows": workflows,
        "stats": stats,
        "output_dir": str(graphrag_output),
    }


def gather_graphrag_stats(output_dir: Path) -> dict[str, Any]:
    """Gather statistics from GraphRAG output files.

    Args:
        output_dir: GraphRAG output directory

    Returns:
        Dict with counts of entities, relationships, etc.
    """
    stats = {}

    # Check for parquet files and count rows
    # Include both final and intermediate files for better visibility
    parquet_files = {
        "entities": ["create_final_entities.parquet", "create_base_extracted_entities.parquet"],
        "relationships": ["create_final_relationships.parquet"],
        "text_units": ["create_final_text_units.parquet", "create_base_text_units.parquet"],
        "communities": ["create_final_communities.parquet"],
        "community_reports": ["create_final_community_reports.parquet"],
    }

    for name, filenames in parquet_files.items():
        found = False
        for filename in filenames:
            filepath = output_dir / filename
            if filepath.exists():
                try:
                    import pandas as pd
                    df = pd.read_parquet(filepath)
                    # Special handling for entity_graph column (GraphML)
                    if "entity_graph" in df.columns:
                        # Count nodes in GraphML
                        import re
                        graph_xml = df["entity_graph"].iloc[0]
                        node_count = len(re.findall(r'<node id="', str(graph_xml)))
                        stats[name] = node_count
                    else:
                        stats[name] = len(df)
                    found = True
                    break
                except Exception as e:
                    logger.warning(f"[GraphRAG] Could not read {filename}: {e}")
                    stats[name] = "error"
                    found = True
                    break
        if not found:
            stats[name] = 0

    return stats
