"""
Pipeline Stages

Each stage runs a specific part of the indexing pipeline:
- ocr: PDF extraction with Docling (runs in subprocess for GPU isolation)
- entity: Entity extraction with LFM2 via GraphRAG
- community: Community report generation with Qwen via GraphRAG
- embeddings: Vector embeddings with BGE-M3 via GraphRAG
"""

from .ocr import run_ocr_stage
from .graphrag import run_graphrag_stage

__all__ = ["run_ocr_stage", "run_graphrag_stage"]
