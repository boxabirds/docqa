#!/usr/bin/env python3
"""
GraphRAG Entity Extraction Benchmark

Benchmarks different LLM models using the actual GraphRAG indexing pipeline.
Runs INSIDE the kotaemon container.

Usage (from host):
  docker exec kotaemon python /app/benchmarks/benchmark.py --model qwen2.5:14b --num-files 1
  docker exec kotaemon python /app/benchmarks/benchmark.py --model gemma2:2b --num-files 3
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

# Paths inside container
APP_DIR = Path("/app")
DATA_DIR = APP_DIR / "tests" / "data" / "credo"
RUNS_DIR = APP_DIR / "benchmark_runs"
SETTINGS_TEMPLATE = APP_DIR / "settings.yaml.example"


def get_pdf_files(num_files: int) -> list[Path]:
    """Get PDF files from test data, sorted alphabetically."""
    pdf_files = sorted(DATA_DIR.glob("*.pdf"))
    return pdf_files[:num_files]


def create_run_directory(model: str) -> Path:
    """Create timestamped run directory."""
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    model_safe = model.replace(":", "-").replace("/", "-")
    run_dir = RUNS_DIR / model_safe / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def extract_text_with_docling(pdf_path: Path, output_dir: Path) -> Path:
    """Extract text from PDF using Docling (the actual loader)."""
    sys.path.insert(0, str(APP_DIR))

    from kotaemon.loaders.docling_loader import DoclingReader

    reader = DoclingReader()
    docs = reader.load_data(pdf_path)

    # Combine text from all pages
    text_parts = []
    for doc in docs:
        if doc.metadata.get("type", "text") == "text":
            text_parts.append(doc.text)

    # Write to txt file for GraphRAG
    txt_file = output_dir / f"{pdf_path.stem}.txt"
    with open(txt_file, "w") as f:
        f.write("\n\n".join(text_parts))

    return txt_file


def get_api_base(backend: str) -> str:
    """Get API base URL for the specified backend."""
    if backend == "vllm":
        # Use LFM2 adapter which converts between GraphRAG and LFM2-Extract formats
        return os.getenv("VLLM_API_BASE", "http://lfm2-adapter:8002/v1")
    return os.getenv("GRAPHRAG_API_BASE", "http://ollama:11434/v1")


def create_graphrag_settings(run_dir: Path, model: str, backend: str = "ollama") -> Path:
    """Create GraphRAG settings.yaml with specified model."""
    api_base = get_api_base(backend)

    # Smaller chunks for vLLM (4K context) vs Ollama models (larger context)
    # vLLM supports high concurrency (89x with LFM2), Ollama is single-threaded
    if backend == "vllm":
        chunk_size = 256
        max_tokens = 500
        concurrent_requests = 32  # vLLM can handle 89, use 32 to be safe
    else:
        chunk_size = 512
        max_tokens = 1500
        concurrent_requests = 1  # Ollama doesn't benefit from concurrency

    # With adapter routing, LFM2 handles extraction, Qwen2.5-7B handles community reports
    skip_workflows = []

    settings = {
        "encoding_model": "cl100k_base",
        "skip_workflows": skip_workflows,
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
        "llm": {
            "api_key": os.getenv("GRAPHRAG_API_KEY", "ollama"),
            "type": "openai_chat",
            "api_base": api_base,
            "model": model,
            "model_supports_json": True,
            "request_timeout": 300.0,
            "concurrent_requests": concurrent_requests,
            "max_tokens": max_tokens,
            "tokens_per_minute": 0,
            "requests_per_minute": 0,
        },
        "parallelization": {
            "stagger": 0.05 if backend == "vllm" else 0.3,
        },
        "async_mode": "threaded",
        "embeddings": {
            "async_mode": "threaded",
            "llm": {
                # Use vLLM for embeddings when using vllm backend, otherwise Ollama
                "api_base": "http://vllm-embed:8000/v1" if backend == "vllm" else os.getenv("GRAPHRAG_API_BASE", "http://ollama:11434/v1"),
                "api_key": os.getenv("GRAPHRAG_API_KEY", "ollama"),
                "model": "BAAI/bge-m3" if backend == "vllm" else os.getenv("GRAPHRAG_EMBEDDING_MODEL", "bge-m3"),
                "type": "openai_embedding",
            }
        },
    }

    settings_file = run_dir / "settings.yaml"
    with open(settings_file, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)

    return settings_file


def run_graphrag_index(run_dir: Path) -> tuple[bool, float]:
    """Run GraphRAG indexing and return success status and elapsed time."""
    start_time = time.time()

    # Initialize
    init_cmd = [
        "python", "-m", "graphrag.index",
        "--root", str(run_dir),
        "--init",
    ]
    subprocess.run(init_cmd, capture_output=True)

    # Settings already created by create_graphrag_settings()

    # Run indexing
    index_cmd = [
        "python", "-m", "graphrag.index",
        "--root", str(run_dir),
        "--reporter", "rich",
    ]

    result = subprocess.run(index_cmd, capture_output=True, text=True)

    elapsed = time.time() - start_time
    success = result.returncode == 0

    # Save output
    with open(run_dir / "stdout.log", "w") as f:
        f.write(result.stdout)
    with open(run_dir / "stderr.log", "w") as f:
        f.write(result.stderr)

    return success, elapsed


def parse_indexing_log(run_dir: Path) -> dict:
    """Parse indexing-engine.log for timing data, separating entity extraction from community reports."""
    log_file = run_dir / "output" / "indexing-engine.log"
    if not log_file.exists():
        return {}

    timings = {
        "llm_calls": [],
        "embedding_calls": [],
        "total_llm_time": 0,
        "total_embedding_time": 0,
        # Separate entity extraction from community reports
        "entity_extraction_calls": [],
        "community_report_calls": [],
        "total_entity_extraction_time": 0,
        "total_community_report_time": 0,
    }

    current_phase = "entity_extraction"  # Default phase

    with open(log_file) as f:
        for line in f:
            # Track which workflow phase we're in
            if "executing verb" in line:
                if "community_report" in line.lower():
                    current_phase = "community_reports"
                elif "extract_graph" in line.lower() or "entity" in line.lower():
                    current_phase = "entity_extraction"

            # Parse LLM timing: perf - llm.chat ... took X.XXs
            if "perf - llm.chat" in line:
                match = re.search(r"took (\d+\.?\d*)", line)
                if match:
                    t = float(match.group(1))
                    timings["llm_calls"].append(t)
                    timings["total_llm_time"] += t

                    # Categorize by phase
                    if current_phase == "community_reports":
                        timings["community_report_calls"].append(t)
                        timings["total_community_report_time"] += t
                    else:
                        timings["entity_extraction_calls"].append(t)
                        timings["total_entity_extraction_time"] += t

            # Parse embedding timing
            elif "perf - llm.embedding" in line:
                match = re.search(r"took (\d+\.?\d*)", line)
                if match:
                    t = float(match.group(1))
                    timings["embedding_calls"].append(t)
                    timings["total_embedding_time"] += t

    timings["llm_call_count"] = len(timings["llm_calls"])
    timings["embedding_call_count"] = len(timings["embedding_calls"])
    timings["entity_extraction_call_count"] = len(timings["entity_extraction_calls"])
    timings["community_report_call_count"] = len(timings["community_report_calls"])

    if timings["llm_calls"]:
        timings["avg_llm_time"] = timings["total_llm_time"] / len(timings["llm_calls"])
    else:
        timings["avg_llm_time"] = 0

    if timings["entity_extraction_calls"]:
        timings["avg_entity_extraction_time"] = timings["total_entity_extraction_time"] / len(timings["entity_extraction_calls"])
    else:
        timings["avg_entity_extraction_time"] = 0

    if timings["community_report_calls"]:
        timings["avg_community_report_time"] = timings["total_community_report_time"] / len(timings["community_report_calls"])
    else:
        timings["avg_community_report_time"] = 0

    return timings


def count_entities(run_dir: Path) -> dict:
    """Count entities and relationships from output parquet files."""
    import pandas as pd

    output_dir = run_dir / "output"
    counts = {"entities": 0, "relationships": 0, "text_units": 0}

    entities_file = output_dir / "create_final_entities.parquet"
    if entities_file.exists():
        df = pd.read_parquet(entities_file)
        counts["entities"] = len(df)

    relationships_file = output_dir / "create_final_relationships.parquet"
    if relationships_file.exists():
        df = pd.read_parquet(relationships_file)
        counts["relationships"] = len(df)

    text_units_file = output_dir / "create_final_text_units.parquet"
    if text_units_file.exists():
        df = pd.read_parquet(text_units_file)
        counts["text_units"] = len(df)

    return counts


def run_quality_test(run_dir: Path, model: str, question: str, question_id: int = 1, backend: str = "ollama"):
    """Run quality test using the indexed data.

    Note: Always uses Ollama for Q&A since extraction models (like LFM2-Extract)
    can't do general chat. The 'model' param is only used if backend is ollama.
    """
    sys.path.insert(0, str(APP_DIR))

    from openai import OpenAI
    import pandas as pd

    # Load entities for context
    output_dir = run_dir / "output"
    context_parts = []

    # Load community reports if available
    reports_file = output_dir / "create_final_community_reports.parquet"
    if reports_file.exists():
        df = pd.read_parquet(reports_file)
        for _, row in df.head(5).iterrows():
            context_parts.append(f"Report: {row.get('title', '')}\n{row.get('content', '')[:1000]}")

    # Load text units for context - use keyword matching for relevance
    text_units_file = output_dir / "create_final_text_units.parquet"
    if text_units_file.exists():
        df = pd.read_parquet(text_units_file)

        # Extract keywords from question for basic retrieval
        question_lower = question.lower()
        keywords = [w for w in question_lower.split() if len(w) > 3 and w not in ("what", "which", "where", "when", "does", "have", "with", "from", "that", "this", "there")]

        # Score text units by keyword matches
        scored_units = []
        for idx, row in df.iterrows():
            text = row.get("text", "")
            text_lower = text.lower()
            score = sum(1 for kw in keywords if kw in text_lower)
            scored_units.append((score, idx, text))

        # Sort by score descending, take top 15
        scored_units.sort(key=lambda x: -x[0])
        for score, idx, text in scored_units[:15]:
            context_parts.append(text[:800])

    context = "\n\n".join(context_parts)[:8000]

    # Save question
    questions_dir = run_dir / "questions"
    questions_dir.mkdir(exist_ok=True)
    with open(questions_dir / f"{question_id}.txt", "w") as f:
        f.write(question)

    # Query LLM - use appropriate chat model (extraction models can't chat)
    if backend == "vllm":
        # Use vLLM chat service for Q&A (7B model for better quality)
        query_api_base = "http://vllm-chat:8000/v1"
        query_model = "Qwen/Qwen2.5-7B-Instruct"
    else:
        # Use Ollama
        query_api_base = os.getenv("GRAPHRAG_API_BASE", "http://ollama:11434/v1")
        query_model = model

    client = OpenAI(
        base_url=query_api_base,
        api_key="ollama"
    )

    start_time = time.time()
    response = client.chat.completions.create(
        model=query_model,
        messages=[
            {"role": "system", "content": "Answer based on the context. Be concise."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
        max_tokens=500,
    )
    elapsed = time.time() - start_time
    answer = response.choices[0].message.content

    # Save answer
    answers_dir = run_dir / "answers"
    answers_dir.mkdir(exist_ok=True)
    with open(answers_dir / f"{question_id}.txt", "w") as f:
        f.write(f"Question: {question}\n")
        f.write(f"Query Model: {query_model}\n")
        f.write(f"Time: {elapsed:.2f}s\n")
        f.write(f"\nAnswer:\n{answer}\n")

    return answer


def main():
    parser = argparse.ArgumentParser(description="GraphRAG Entity Extraction Benchmark")
    parser.add_argument("--model", default="qwen2.5:14b", help="Model for entity extraction")
    parser.add_argument("--num-files", type=int, default=1, help="Number of PDF files (1-6)")
    parser.add_argument("--force", action="store_true", help="Force fresh indexing (don't reuse cached chunks)")
    parser.add_argument("--backend", choices=["ollama", "vllm"], default="ollama", help="Inference backend")

    args = parser.parse_args()

    print(f"=" * 60)
    print(f"GraphRAG Entity Extraction Benchmark")
    print(f"=" * 60)
    print(f"Model: {args.model}")
    print(f"Backend: {args.backend}")
    print(f"Files: {args.num_files}")

    # Get PDF files
    pdf_files = get_pdf_files(args.num_files)
    if not pdf_files:
        print(f"Error: No PDF files found in {DATA_DIR}")
        sys.exit(1)

    print(f"\nProcessing files:")
    for f in pdf_files:
        print(f"  - {f.name}")

    # Create run directory
    run_dir = create_run_directory(args.model)
    print(f"\nRun directory: {run_dir}")

    # Create input directory and extract text
    input_dir = run_dir / "input"
    input_dir.mkdir(exist_ok=True)

    # Check for cached extracted text
    cache_dir = RUNS_DIR / "extracted_text"

    print(f"\n[Step 1] Extracting text with Docling...")
    for pdf_file in pdf_files:
        txt_file = input_dir / f"{pdf_file.stem}.txt"
        cached_file = cache_dir / f"{pdf_file.stem}.txt"

        # Use cached extraction if available
        if cached_file.exists():
            print(f"  Using cached: {pdf_file.name}")
            shutil.copy(cached_file, txt_file)
            continue

        print(f"  Processing: {pdf_file.name}")
        try:
            txt_file = extract_text_with_docling(pdf_file, input_dir)
            print(f"    → {txt_file.name}")
            # Cache for future runs
            cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(txt_file, cached_file)
        except Exception as e:
            print(f"    Error: {e}")
            # Fallback: just copy as txt (for testing)
            txt_file.write_text(f"[Docling extraction failed for {pdf_file.name}]")

    # Create settings
    print(f"\n[Step 2] Creating GraphRAG settings...")
    create_graphrag_settings(run_dir, args.model, args.backend)

    # Check for cached results
    output_dir = run_dir / "output"
    has_cache = (output_dir / "create_final_entities.parquet").exists()

    if has_cache and not args.force:
        print(f"\n[Step 3] Using cached indexing results (use --force to re-run)")
        timings = parse_indexing_log(run_dir)
        counts = count_entities(run_dir)
    else:
        print(f"\n[Step 3] Running GraphRAG indexing...")
        print(f"  This may take several minutes...")
        success, elapsed = run_graphrag_index(run_dir)

        if success:
            print(f"  ✓ Indexing completed in {elapsed:.1f}s")
        else:
            print(f"  ✗ Indexing failed after {elapsed:.1f}s")
            print(f"    Check {run_dir}/stderr.log for details")

        # Parse timing
        timings = parse_indexing_log(run_dir)
        counts = count_entities(run_dir)

        # Save timings
        timings_file = run_dir / "timings.json"
        with open(timings_file, "w") as f:
            json.dump({**timings, **counts, "total_elapsed": elapsed}, f, indent=2)

        # Also save as CSV for the entity extraction calls
        if timings.get("llm_calls"):
            csv_file = run_dir / "entity_timings.csv"
            with open(csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["call_index", "elapsed_seconds"])
                for i, t in enumerate(timings["llm_calls"]):
                    writer.writerow([i, t])

    # Quality test
    print(f"\n[Step 4] Running quality test...")
    question = "Is Cadent cost of heat failures in the MVP?"
    answer = run_quality_test(run_dir, args.model, question, question_id=1, backend=args.backend)
    print(f"  Q: {question}")
    print(f"  A: {answer[:200]}...")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"BENCHMARK SUMMARY")
    print(f"{'=' * 60}")
    print(f"Model: {args.model}")
    print(f"Backend: {args.backend}")
    print(f"Files processed: {len(pdf_files)}")
    if timings:
        # Entity extraction metrics (primary benchmark)
        print(f"\n--- Entity Extraction ---")
        print(f"  Calls: {timings.get('entity_extraction_call_count', 'N/A')}")
        print(f"  Total time: {timings.get('total_entity_extraction_time', 0):.1f}s")
        print(f"  Avg time/call: {timings.get('avg_entity_extraction_time', 0):.2f}s")

        # Community report metrics (if any)
        if timings.get('community_report_call_count', 0) > 0:
            print(f"\n--- Community Reports ---")
            print(f"  Calls: {timings.get('community_report_call_count', 'N/A')}")
            print(f"  Total time: {timings.get('total_community_report_time', 0):.1f}s")
            print(f"  Avg time/call: {timings.get('avg_community_report_time', 0):.2f}s")

        # Overall
        print(f"\n--- Overall ---")
        print(f"  Total LLM calls: {timings.get('llm_call_count', 'N/A')}")
        print(f"  Total LLM time: {timings.get('total_llm_time', 0):.1f}s")
    if counts:
        print(f"\n--- Output ---")
        print(f"  Entities: {counts.get('entities', 'N/A')}")
        print(f"  Relationships: {counts.get('relationships', 'N/A')}")
    print(f"\nResults: {run_dir}")
    print(f"{'=' * 60}")

    # Save summary
    summary = {
        "model": args.model,
        "num_files": len(pdf_files),
        "files": [f.name for f in pdf_files],
        **timings,
        **counts,
    }
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
