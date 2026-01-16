#!/usr/bin/env python3
"""
Collection Indexing Benchmark

Benchmarks the full document indexing pipeline as used by Kotaemon:
1. PDF → text extraction (Docling)
2. Text → chunks
3. Chunks → embeddings (BGE-M3)
4. Chunks → entities (LFM2 / GraphRAG)
5. Entities → community reports (Qwen2.5-7B)

Creates a real collection and indexes files, timing each step.

Usage (from host):
  docker exec kotaemon python /app/benchmarks/index_collection.py \
    --name "Benchmark Collection" \
    --files /app/tests/data/credo/*.pdf \
    --backend vllm
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml

# Paths inside container
APP_DIR = Path("/app")
DATA_DIR = APP_DIR / "ktem_app_data"
GRAPHRAG_DIR = DATA_DIR / "user_data" / "files" / "graphrag"
RUNS_DIR = APP_DIR / "benchmark_runs" / "collections"


def get_pdf_files(file_patterns: list[str]) -> list[Path]:
    """Expand file patterns and return list of PDF files."""
    from glob import glob

    files = []
    for pattern in file_patterns:
        matched = glob(pattern)
        for f in matched:
            if f.endswith('.pdf'):
                files.append(Path(f))
    return sorted(files)


def create_run_directory(name: str) -> Path:
    """Create timestamped run directory."""
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    safe_name = name.replace(" ", "_").replace("/", "-")[:30]
    run_dir = RUNS_DIR / f"{safe_name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


class Timer:
    """Simple timer for measuring step durations."""

    def __init__(self):
        self.steps = {}
        self.current_step = None
        self.start_time = None

    def start(self, step_name: str):
        self.current_step = step_name
        self.start_time = time.time()
        print(f"\n[{step_name}] Starting...")

    def stop(self):
        if self.current_step and self.start_time:
            elapsed = time.time() - self.start_time
            self.steps[self.current_step] = elapsed
            print(f"[{self.current_step}] Completed in {elapsed:.1f}s")
            self.current_step = None
            self.start_time = None
            return elapsed
        return 0

    def summary(self) -> dict:
        return {
            "steps": self.steps,
            "total": sum(self.steps.values())
        }


def extract_text_with_docling(pdf_files: list[Path], timer: Timer) -> dict[Path, list]:
    """Extract text from PDFs using Docling."""
    timer.start("PDF Extraction (Docling)")

    sys.path.insert(0, str(APP_DIR))
    from kotaemon.loaders.docling_loader import DoclingReader

    reader = DoclingReader()
    all_docs = {}

    for pdf_file in pdf_files:
        print(f"  Processing: {pdf_file.name}")
        try:
            docs = reader.load_data(pdf_file)
            all_docs[pdf_file] = docs

            # Count content types
            text_count = sum(1 for d in docs if d.metadata.get("type") == "text")
            table_count = sum(1 for d in docs if d.metadata.get("type") == "table")
            image_count = sum(1 for d in docs if d.metadata.get("type") == "image")
            print(f"    → {text_count} text, {table_count} tables, {image_count} images")
        except Exception as e:
            print(f"    Error: {e}")
            all_docs[pdf_file] = []

    timer.stop()
    return all_docs


def create_graphrag_settings(run_dir: Path, backend: str = "vllm") -> Path:
    """Create GraphRAG settings.yaml with per-stage LLM configuration."""

    api_key = os.getenv("GRAPHRAG_API_KEY", "ollama")

    if backend == "vllm":
        # Entity extraction: LFM2 via adapter
        entity_api_base = "http://lfm2-adapter:8002/v1"
        entity_model = "LiquidAI/LFM2-1.2B-Extract"
        entity_concurrent = 50

        # Community reports & summarization: Qwen-7B direct
        chat_api_base = "http://vllm-chat:8000/v1"
        chat_model = "Qwen/Qwen2.5-7B-Instruct"
        chat_concurrent = 25

        # Embeddings: BGE-M3 via vLLM
        embed_api_base = "http://vllm-embed:8000/v1"
        embed_model = "BAAI/bge-m3"

        chunk_size = 256
    else:
        # Ollama: single endpoint for everything
        entity_api_base = os.getenv("GRAPHRAG_API_BASE", "http://ollama:11434/v1")
        entity_model = os.getenv("LOCAL_MODEL", "qwen2.5:14b")
        entity_concurrent = 1

        chat_api_base = entity_api_base
        chat_model = entity_model
        chat_concurrent = 1

        embed_api_base = entity_api_base
        embed_model = os.getenv("GRAPHRAG_EMBEDDING_MODEL", "bge-m3")

        chunk_size = 512

    settings = {
        "encoding_model": "cl100k_base",
        "skip_workflows": [],
        "chunks": {
            "size": chunk_size,
            "overlap": 50,
            "group_by_columns": ["id"],
            "strategy": {
                "type": "sentence",
                "chunk_size": chunk_size,
                "chunk_overlap": 50,
            }
        },
        "input": {
            "type": "file",
            "file_type": "text",
            "base_dir": "input",
            "file_pattern": ".*\\.txt$",
        },
        # Default LLM (fallback)
        "llm": {
            "api_key": api_key,
            "type": "openai_chat",
            "api_base": chat_api_base,
            "model": chat_model,
            "model_supports_json": True,
            "request_timeout": 300.0,
            "concurrent_requests": chat_concurrent,
            "max_tokens": 1500,
            "tokens_per_minute": 0,
            "requests_per_minute": 0,
        },
        "parallelization": {
            "stagger": 0.1 if backend == "vllm" else 0.3,
            "num_threads": 50 if backend == "vllm" else 1,
        },
        "async_mode": "threaded",
        # Entity extraction: LFM2 via adapter
        "entity_extraction": {
            "llm": {
                "api_key": api_key,
                "type": "openai_chat",
                "api_base": entity_api_base,
                "model": entity_model,
                "model_supports_json": True,
                "request_timeout": 300.0,
                "concurrent_requests": entity_concurrent,
                "max_tokens": 2000,
                "tokens_per_minute": 0,
                "requests_per_minute": 0,
            },
            "parallelization": {
                "stagger": 0.1,
                "num_threads": entity_concurrent,
            },
        },
        # Entity description summarization: Qwen-7B direct
        "summarize_descriptions": {
            "llm": {
                "api_key": api_key,
                "type": "openai_chat",
                "api_base": chat_api_base,
                "model": chat_model,
                "model_supports_json": True,
                "request_timeout": 300.0,
                "concurrent_requests": chat_concurrent,
                "max_tokens": 1000,
                "tokens_per_minute": 0,
                "requests_per_minute": 0,
            },
        },
        # Community reports: Qwen-7B direct
        "community_reports": {
            "llm": {
                "api_key": api_key,
                "type": "openai_chat",
                "api_base": chat_api_base,
                "model": chat_model,
                "model_supports_json": True,
                "request_timeout": 300.0,
                "concurrent_requests": chat_concurrent,
                "max_tokens": 2000,
                "tokens_per_minute": 0,
                "requests_per_minute": 0,
            },
        },
        "embeddings": {
            "async_mode": "threaded",
            "llm": {
                "api_base": embed_api_base,
                "api_key": api_key,
                "model": embed_model,
                "type": "openai_embedding",
                "concurrent_requests": 25 if backend == "vllm" else 1,
            }
        },
    }

    settings_file = run_dir / "settings.yaml"
    with open(settings_file, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)

    return settings_file


def write_docs_to_graphrag(docs_by_file: dict[Path, list], run_dir: Path, timer: Timer) -> int:
    """Write extracted documents to GraphRAG input directory."""
    timer.start("Write to GraphRAG Input")

    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    doc_count = 0
    for pdf_file, docs in docs_by_file.items():
        # Combine all text content from this PDF
        text_parts = []
        for doc in docs:
            if doc.metadata.get("type", "text") == "text":
                text_parts.append(doc.text)

        if text_parts:
            txt_file = input_dir / f"{pdf_file.stem}.txt"
            with open(txt_file, "w") as f:
                f.write("\n\n".join(text_parts))
            doc_count += 1
            print(f"  Wrote: {txt_file.name} ({len(text_parts)} sections)")

    timer.stop()
    return doc_count


def run_graphrag_indexing(run_dir: Path, timer: Timer) -> tuple[bool, dict]:
    """Run GraphRAG indexing pipeline."""
    timer.start("GraphRAG Indexing")

    # Initialize
    init_cmd = [
        "python", "-m", "graphrag.index",
        "--root", str(run_dir),
        "--init",
    ]
    subprocess.run(init_cmd, capture_output=True)

    # Run indexing
    index_cmd = [
        "python", "-m", "graphrag.index",
        "--root", str(run_dir),
        "--reporter", "rich",
    ]

    result = subprocess.run(index_cmd, capture_output=True, text=True)
    elapsed = timer.stop()

    success = result.returncode == 0

    # Save logs
    with open(run_dir / "stdout.log", "w") as f:
        f.write(result.stdout)
    with open(run_dir / "stderr.log", "w") as f:
        f.write(result.stderr)

    # Parse timing from logs
    timing_data = parse_indexing_log(run_dir)
    timing_data["total_elapsed"] = elapsed

    return success, timing_data


def parse_indexing_log(run_dir: Path) -> dict:
    """Parse indexing-engine.log for detailed timing."""
    import re

    log_file = run_dir / "output" / "indexing-engine.log"
    if not log_file.exists():
        return {}

    timings = {
        "entity_extraction_calls": 0,
        "entity_extraction_time": 0,
        "community_report_calls": 0,
        "community_report_time": 0,
        "embedding_calls": 0,
        "embedding_time": 0,
    }

    current_phase = "entity_extraction"

    with open(log_file) as f:
        for line in f:
            # Track workflow phase
            if "executing verb" in line:
                if "community_report" in line.lower():
                    current_phase = "community_reports"
                elif "extract_graph" in line.lower() or "entity" in line.lower():
                    current_phase = "entity_extraction"

            # Parse LLM timing
            if "perf - llm.chat" in line:
                match = re.search(r"took (\d+\.?\d*)", line)
                if match:
                    t = float(match.group(1))
                    if current_phase == "community_reports":
                        timings["community_report_calls"] += 1
                        timings["community_report_time"] += t
                    else:
                        timings["entity_extraction_calls"] += 1
                        timings["entity_extraction_time"] += t

            # Parse embedding timing
            elif "perf - llm.embedding" in line:
                match = re.search(r"took (\d+\.?\d*)", line)
                if match:
                    t = float(match.group(1))
                    timings["embedding_calls"] += 1
                    timings["embedding_time"] += t

    # Calculate averages
    if timings["entity_extraction_calls"] > 0:
        timings["entity_extraction_avg"] = timings["entity_extraction_time"] / timings["entity_extraction_calls"]
    if timings["community_report_calls"] > 0:
        timings["community_report_avg"] = timings["community_report_time"] / timings["community_report_calls"]
    if timings["embedding_calls"] > 0:
        timings["embedding_avg"] = timings["embedding_time"] / timings["embedding_calls"]

    return timings


def count_output(run_dir: Path) -> dict:
    """Count entities and relationships from output."""
    import pandas as pd

    output_dir = run_dir / "output"
    counts = {
        "entities": 0,
        "relationships": 0,
        "text_units": 0,
        "communities": 0,
    }

    files = {
        "entities": "create_final_entities.parquet",
        "relationships": "create_final_relationships.parquet",
        "text_units": "create_final_text_units.parquet",
        "communities": "create_final_communities.parquet",
    }

    for key, filename in files.items():
        filepath = output_dir / filename
        if filepath.exists():
            df = pd.read_parquet(filepath)
            counts[key] = len(df)

    return counts


def run_quality_test(run_dir: Path, question: str, backend: str, timer: Timer) -> str:
    """Run a quality test query."""
    timer.start("Quality Test Query")

    from openai import OpenAI
    import pandas as pd

    output_dir = run_dir / "output"
    context_parts = []

    # Load community reports if available
    reports_file = output_dir / "create_final_community_reports.parquet"
    if reports_file.exists():
        df = pd.read_parquet(reports_file)
        for _, row in df.head(5).iterrows():
            context_parts.append(f"Report: {row.get('title', '')}\n{row.get('content', '')[:1000]}")

    # Load text units for context
    text_units_file = output_dir / "create_final_text_units.parquet"
    if text_units_file.exists():
        df = pd.read_parquet(text_units_file)

        # Keyword-based retrieval
        question_lower = question.lower()
        keywords = [w for w in question_lower.split() if len(w) > 3]

        scored_units = []
        for idx, row in df.iterrows():
            text = row.get("text", "")
            text_lower = text.lower()
            score = sum(1 for kw in keywords if kw in text_lower)
            scored_units.append((score, idx, text))

        scored_units.sort(key=lambda x: -x[0])
        for score, idx, text in scored_units[:15]:
            context_parts.append(text[:800])

    context = "\n\n".join(context_parts)[:8000]

    # Query LLM
    if backend == "vllm":
        api_base = "http://vllm-chat:8000/v1"
        model = "Qwen/Qwen2.5-7B-Instruct"
    else:
        api_base = os.getenv("GRAPHRAG_API_BASE", "http://ollama:11434/v1")
        model = os.getenv("LOCAL_MODEL", "qwen2.5:14b")

    client = OpenAI(base_url=api_base, api_key="ollama")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Answer based on the context. Be concise."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
        max_tokens=500,
    )

    timer.stop()
    return response.choices[0].message.content


def main():
    parser = argparse.ArgumentParser(description="Collection Indexing Benchmark")
    parser.add_argument("--name", default="Benchmark", help="Collection name")
    parser.add_argument("--files", nargs="+", required=True, help="PDF files or glob patterns")
    parser.add_argument("--backend", choices=["ollama", "vllm"], default="vllm", help="Inference backend")
    parser.add_argument("--question", default="Is Cadent cost of heat failures in the MVP?", help="Quality test question")

    args = parser.parse_args()

    print("=" * 70)
    print("COLLECTION INDEXING BENCHMARK")
    print("=" * 70)
    print(f"Collection: {args.name}")
    print(f"Backend: {args.backend}")
    print(f"Files: {args.files}")

    # Get PDF files
    pdf_files = get_pdf_files(args.files)
    if not pdf_files:
        print(f"Error: No PDF files found matching: {args.files}")
        sys.exit(1)

    print(f"\nFound {len(pdf_files)} PDF files:")
    for f in pdf_files:
        print(f"  - {f.name}")

    # Create run directory
    run_dir = create_run_directory(args.name)
    print(f"\nRun directory: {run_dir}")

    # Initialize timer
    timer = Timer()

    # Step 1: Extract text from PDFs
    docs_by_file = extract_text_with_docling(pdf_files, timer)
    total_docs = sum(len(docs) for docs in docs_by_file.values())
    print(f"  Total documents extracted: {total_docs}")

    # Step 2: Create GraphRAG settings
    timer.start("Create Settings")
    create_graphrag_settings(run_dir, args.backend)
    timer.stop()

    # Step 3: Write documents to GraphRAG input
    doc_count = write_docs_to_graphrag(docs_by_file, run_dir, timer)

    # Step 4: Run GraphRAG indexing
    success, timing_data = run_graphrag_indexing(run_dir, timer)

    if success:
        print("  ✓ GraphRAG indexing completed")
    else:
        print("  ✗ GraphRAG indexing failed (partial results may exist)")
        print(f"    Check {run_dir}/stderr.log for details")

    # Step 5: Count output
    counts = count_output(run_dir)

    # Step 6: Quality test
    answer = run_quality_test(run_dir, args.question, args.backend, timer)

    # Summary
    summary = timer.summary()

    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)

    print(f"\n--- Input ---")
    print(f"  PDF files: {len(pdf_files)}")
    print(f"  Documents extracted: {total_docs}")
    print(f"  Text files for GraphRAG: {doc_count}")

    print(f"\n--- Timing ---")
    for step, elapsed in summary["steps"].items():
        print(f"  {step}: {elapsed:.1f}s")
    print(f"  TOTAL: {summary['total']:.1f}s")

    if timing_data:
        print(f"\n--- GraphRAG Details ---")
        print(f"  Entity extraction calls: {timing_data.get('entity_extraction_calls', 'N/A')}")
        print(f"  Entity extraction time: {timing_data.get('entity_extraction_time', 0):.1f}s")
        if timing_data.get('entity_extraction_avg'):
            print(f"  Entity extraction avg: {timing_data.get('entity_extraction_avg', 0):.2f}s/call")
        print(f"  Community report calls: {timing_data.get('community_report_calls', 'N/A')}")
        print(f"  Community report time: {timing_data.get('community_report_time', 0):.1f}s")
        print(f"  Embedding calls: {timing_data.get('embedding_calls', 'N/A')}")
        print(f"  Embedding time: {timing_data.get('embedding_time', 0):.1f}s")

    print(f"\n--- Output ---")
    print(f"  Entities: {counts['entities']}")
    print(f"  Relationships: {counts['relationships']}")
    print(f"  Text units: {counts['text_units']}")
    print(f"  Communities: {counts['communities']}")

    print(f"\n--- Quality Test ---")
    print(f"  Q: {args.question}")
    print(f"  A: {answer[:300]}...")

    print(f"\nResults saved to: {run_dir}")
    print("=" * 70)

    # Save full results
    results = {
        "name": args.name,
        "backend": args.backend,
        "files": [str(f) for f in pdf_files],
        "timing": summary,
        "graphrag_timing": timing_data,
        "counts": counts,
        "question": args.question,
        "answer": answer,
    }

    with open(run_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
