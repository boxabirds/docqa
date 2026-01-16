"""
OCR Stage - PDF Extraction with Docling

Runs Docling in a subprocess for clean GPU memory isolation.
When the subprocess exits, all GPU memory is released.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Script to run in subprocess - extracts text from PDFs using Docling
OCR_SCRIPT = '''
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

def main():
    input_files = json.loads(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create pdfs subdirectory for storing original PDFs
    pdf_storage = output_dir / "pdfs"
    pdf_storage.mkdir(exist_ok=True)

    # Redirect stdout during imports to suppress library output
    old_stdout = sys.stdout
    sys.stdout = sys.stderr  # Redirect to stderr temporarily

    # Suppress verbose logging from libraries
    import logging
    logging.getLogger("docling").setLevel(logging.WARNING)
    logging.getLogger("kotaemon").setLevel(logging.WARNING)

    # Import inside subprocess to load CUDA context here
    from kotaemon.loaders.docling_loader import DoclingReader

    reader = DoclingReader()
    results = {"files": {}, "stats": {"total_pages": 0, "total_tables": 0, "total_sections": 0}}

    for pdf_path in input_files:
        pdf = Path(pdf_path)
        print(f"Processing: {pdf.name}", file=sys.stderr)

        try:
            # Copy original PDF to storage
            stored_pdf = pdf_storage / pdf.name
            shutil.copy(pdf, stored_pdf)
            print(f"  -> Stored PDF: {stored_pdf}", file=sys.stderr)

            docs = reader.load_data(pdf)

            # Separate by type
            text_docs = [d for d in docs if d.metadata.get("type", "text") == "text"]
            table_docs = [d for d in docs if d.metadata.get("type") == "table"]

            # Group text by page number
            page_to_texts = defaultdict(list)
            for d in text_docs:
                page_num = d.metadata.get("page_label", 1)
                page_to_texts[page_num].append(d.text)

            # Write extracted text with page markers
            txt_file = output_dir / f"{pdf.stem}.txt"
            text_parts = []
            sorted_pages = sorted(page_to_texts.keys())
            for page_num in sorted_pages:
                # Insert page marker
                text_parts.append(f"<!-- PAGE {page_num} -->")
                text_parts.extend(page_to_texts[page_num])

            txt_file.write_text("\\n\\n".join(text_parts))

            # Track stats
            file_stats = {
                "output_file": str(txt_file),
                "pdf_stored": str(stored_pdf),
                "sections": sum(len(texts) for texts in page_to_texts.values()),
                "pages": len(sorted_pages),
                "tables": len(table_docs),
                "total_docs": len(docs),
            }
            results["files"][str(pdf)] = file_stats
            results["stats"]["total_sections"] += file_stats["sections"]
            results["stats"]["total_tables"] += len(table_docs)
            results["stats"]["total_pages"] += len(sorted_pages)

            print(f"  -> {file_stats['pages']} pages, {file_stats['sections']} sections, {len(table_docs)} tables", file=sys.stderr)

        except Exception as e:
            results["files"][str(pdf)] = {"error": str(e)}
            print(f"  -> ERROR: {e}", file=sys.stderr)

    # Restore stdout and output JSON
    sys.stdout = old_stdout
    print(json.dumps(results))

if __name__ == "__main__":
    main()
'''


def run_ocr_stage(
    input_files: list[str | Path],
    output_dir: str | Path,
    timeout: float = 3600.0,
) -> dict[str, Any]:
    """Run OCR extraction in subprocess.

    Runs Docling in a separate process to ensure GPU memory is fully
    released when extraction completes. This allows subsequent stages
    to use the full GPU.

    Args:
        input_files: List of PDF file paths
        output_dir: Directory to write extracted text files
        timeout: Max time to wait for extraction (seconds)

    Returns:
        Dict with extraction results:
        {
            "files": {"/path/to.pdf": {"output_file": "...", "sections": N, ...}},
            "stats": {"total_sections": N, "total_tables": N}
        }

    Raises:
        subprocess.TimeoutExpired: If extraction takes too long
        RuntimeError: If subprocess fails
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert paths to strings for JSON serialization
    file_list = [str(f) for f in input_files]

    logger.info(f"[OCR] Starting extraction of {len(file_list)} files")
    logger.info(f"[OCR] Output directory: {output_dir}")

    # Run extraction in subprocess
    result = subprocess.run(
        [
            sys.executable,  # Use same Python interpreter
            "-c",
            OCR_SCRIPT,
            json.dumps(file_list),
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # Log stderr (progress messages)
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            logger.info(f"[OCR] {line}")

    # Check for errors
    if result.returncode != 0:
        error_msg = result.stderr or "Unknown error"
        logger.error(f"[OCR] Subprocess failed: {error_msg}")
        raise RuntimeError(f"OCR extraction failed: {error_msg}")

    # Parse results from stdout
    try:
        results = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.error(f"[OCR] Failed to parse output: {e}")
        logger.error(f"[OCR] stdout: {result.stdout[:500]}")
        raise RuntimeError(f"Failed to parse OCR results: {e}")

    logger.info(f"[OCR] Extraction complete: {results['stats']}")
    return results


def get_text_files(output_dir: str | Path) -> list[Path]:
    """Get list of extracted text files from OCR output directory.

    Args:
        output_dir: Directory containing .txt files from OCR stage

    Returns:
        List of text file paths
    """
    output_dir = Path(output_dir)
    return sorted(output_dir.glob("*.txt"))
