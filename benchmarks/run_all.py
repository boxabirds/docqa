#!/usr/bin/env python3
"""
Run entity extraction benchmarks across multiple models.

Usage (from host):
  docker exec kotaemon python /app/benchmarks/run_all.py
  docker exec kotaemon python /app/benchmarks/run_all.py --models gemma2:2b qwen2.5:3b
  docker exec kotaemon python /app/benchmarks/run_all.py --pull  # Download missing models

Or via shell script:
  ./benchmarks/run.sh --all
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BENCHMARKS_DIR = Path("/app/benchmarks")
MODELS_FILE = BENCHMARKS_DIR / "models.json"
RUNS_DIR = Path("/app/benchmark_runs")


def load_models() -> list[dict]:
    """Load models from JSON file."""
    if MODELS_FILE.exists():
        with open(MODELS_FILE) as f:
            data = json.load(f)
            return data.get("models", [])
    return []


def check_model_available(model_name: str) -> bool:
    """Check if model is available in Ollama."""
    try:
        import requests
        response = requests.get("http://ollama:11434/api/tags", timeout=5)
        if response.ok:
            tags = response.json().get("models", [])
            available = [t.get("name", "") for t in tags]
            # Check exact match or base name match
            for name in available:
                if name == model_name or name.startswith(f"{model_name.split(':')[0]}:"):
                    return True
        return False
    except Exception:
        return False


def pull_ollama_model(model_name: str) -> bool:
    """Pull model from Ollama registry."""
    print(f"  Pulling {model_name} from Ollama...")
    try:
        import requests
        response = requests.post(
            "http://ollama:11434/api/pull",
            json={"name": model_name},
            timeout=600,
            stream=True,
        )
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                status = data.get("status", "")
                if "pulling" in status or "downloading" in status:
                    print(f"    {status}", end="\r")
        print()
        return response.ok
    except Exception as e:
        print(f"    Error: {e}")
        return False


def import_gguf_model(model_info: dict) -> bool:
    """Import GGUF model from HuggingFace into Ollama."""
    name = model_info["name"]
    hf_url = model_info.get("huggingface")

    if not hf_url:
        print(f"  No HuggingFace URL for {name}")
        return False

    print(f"  Importing {name} from HuggingFace...")
    print(f"    URL: {hf_url}")

    # Create Modelfile
    # For GGUF imports, we need to download the file first
    # This is a simplified approach - full implementation would download and create
    print(f"    NOTE: Manual import required for HuggingFace GGUF models")
    print(f"    Run: ollama create {name} -f <Modelfile>")
    print(f"    See: {hf_url}")
    return False


def check_vllm_available() -> bool:
    """Check if vLLM service is running."""
    try:
        import requests
        response = requests.get("http://vllm:8000/health", timeout=5)
        return response.ok
    except Exception:
        return False


def ensure_model(model_info: dict, pull: bool = False) -> bool:
    """Ensure model is available, optionally pulling/importing it."""
    name = model_info["name"]
    backend = model_info.get("backend", "ollama")
    ollama_name = model_info.get("ollama")
    hf_url = model_info.get("huggingface")

    # For vLLM models, just check if vLLM is running
    if backend == "vllm":
        if check_vllm_available():
            print(f"  ✓ {name} (vLLM)")
            return True
        else:
            print(f"  ✗ {name} - vLLM not running (start with: docker compose --profile vllm up -d vllm)")
            return False

    # Check if already available in Ollama
    check_name = ollama_name or name
    if check_model_available(check_name):
        print(f"  ✓ {name}")
        return True

    if not pull:
        print(f"  ✗ {name} - not available (use --pull)")
        return False

    # Try to pull/import
    if ollama_name:
        if pull_ollama_model(ollama_name):
            return True

    if hf_url:
        return import_gguf_model(model_info)

    print(f"  ✗ {name} - failed to obtain")
    return False


def run_benchmark(model_info: dict, num_files: int) -> dict:
    """Run benchmark for a single model."""
    name = model_info["name"]
    backend = model_info.get("backend", "ollama")

    # Get model name for the backend
    if backend == "vllm":
        model_name = model_info.get("vllm") or name
    else:
        model_name = model_info.get("ollama") or name

    print(f"\n{'='*60}")
    print(f"Benchmarking: {name} ({model_info.get('params', '?')})")
    print(f"  Backend: {backend}")
    print(f"  {model_info.get('description', '')}")
    print(f"{'='*60}")

    start_time = datetime.now()

    result = subprocess.run(
        [
            sys.executable,
            "/app/benchmarks/benchmark.py",
            "--model", model_name,
            "--num-files", str(num_files),
            "--backend", backend,
            "--force",  # Always fresh run for benchmarking
        ],
        capture_output=False,
    )

    elapsed = (datetime.now() - start_time).total_seconds()

    return {
        "name": name,
        "model": model_name,
        "backend": backend,
        "success": result.returncode == 0,
        "elapsed_seconds": elapsed,
    }


def generate_comparison_report() -> str:
    """Generate comparison report from all runs."""
    lines = []
    lines.append("# GraphRAG Entity Extraction Benchmark Comparison")
    lines.append(f"\nGenerated: {datetime.now().isoformat()}\n")

    # Collect summaries from all runs
    summaries = []
    for model_dir in sorted(RUNS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue

        # Get most recent run
        run_dirs = sorted(model_dir.iterdir(), reverse=True)
        for run_dir in run_dirs:
            summary_file = run_dir / "summary.json"
            if summary_file.exists():
                with open(summary_file) as f:
                    summary = json.load(f)
                    summary["run_dir"] = str(run_dir)
                    summaries.append(summary)
                break

    if not summaries:
        return "No benchmark results found."

    # Sort by total LLM time
    summaries.sort(key=lambda x: x.get("total_llm_time", float("inf")))

    # Generate table
    lines.append("## Results (sorted by extraction time)\n")
    lines.append("| Model | LLM Calls | Total Time | Avg/Call | Entities | Relationships | Speedup |")
    lines.append("|-------|-----------|------------|----------|----------|---------------|---------|")

    baseline_time = max(s.get("total_llm_time", 1) for s in summaries)

    for s in summaries:
        total_time = s.get("total_llm_time", 0)
        avg_time = s.get("avg_llm_time", 0)
        speedup = baseline_time / total_time if total_time > 0 else 0

        lines.append(
            f"| {s.get('model', 'unknown')} "
            f"| {s.get('llm_call_count', 0)} "
            f"| {total_time:.1f}s "
            f"| {avg_time:.2f}s "
            f"| {s.get('entities', 0)} "
            f"| {s.get('relationships', 0)} "
            f"| {speedup:.1f}x |"
        )

    # Quality comparison
    lines.append("\n## Quality Test Answers\n")
    for s in summaries:
        run_dir = Path(s.get("run_dir", ""))
        answer_file = run_dir / "answers" / "1.txt"
        if answer_file.exists():
            lines.append(f"### {s.get('model', 'unknown')}\n")
            lines.append("```")
            with open(answer_file) as f:
                lines.append(f.read().strip())
            lines.append("```\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run benchmarks across multiple models")
    parser.add_argument("--models", nargs="+", help="Specific model names to benchmark")
    parser.add_argument("--num-files", type=int, default=1, help="Number of PDF files")
    parser.add_argument("--pull", action="store_true", help="Pull/import missing models")
    parser.add_argument("--report-only", action="store_true", help="Generate report only")
    parser.add_argument("--list", action="store_true", help="List available models")

    args = parser.parse_args()

    # Load models from JSON
    all_models = load_models()

    if args.list:
        print("Available models in models.json:\n")
        for m in all_models:
            status = "✓" if check_model_available(m.get("ollama") or m["name"]) else "✗"
            print(f"  {status} {m['name']} ({m.get('params', '?')})")
            print(f"      {m.get('description', '')}")
            if m.get("huggingface"):
                print(f"      HF: {m['huggingface']}")
        return

    # Report only mode
    if args.report_only:
        report = generate_comparison_report()
        report_file = RUNS_DIR / "comparison.md"
        report_file.parent.mkdir(exist_ok=True)
        with open(report_file, "w") as f:
            f.write(report)
        print(report)
        print(f"\nReport saved to: {report_file}")
        return

    # Filter models if specific ones requested
    if args.models:
        models = [m for m in all_models if m["name"] in args.models]
        if not models:
            print(f"No matching models found. Available: {[m['name'] for m in all_models]}")
            sys.exit(1)
    else:
        models = all_models

    print(f"Models to benchmark: {len(models)}")

    # Check/pull models
    available = []
    for model in models:
        if ensure_model(model, pull=args.pull):
            available.append(model)

    if not available:
        print("\nNo models available! Use --pull to download.")
        sys.exit(1)

    # Run benchmarks
    results = []
    for model in available:
        result = run_benchmark(model, args.num_files)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("ALL BENCHMARKS COMPLETE")
    print(f"{'='*60}")
    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} {r['name']}: {r['elapsed_seconds']:.1f}s")

    # Generate report
    report = generate_comparison_report()
    report_file = RUNS_DIR / "comparison.md"
    with open(report_file, "w") as f:
        f.write(report)
    print(f"\nComparison report: {report_file}")


if __name__ == "__main__":
    main()
