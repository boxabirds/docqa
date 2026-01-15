"""
Pipeline Orchestrator for GPU-Aware Document Indexing

Manages staged execution of:
1. OCR (Docling) - PDF extraction with GPU
2. Entity Extraction (LFM2) - GraphRAG entities
3. Community Reports (Qwen) - GraphRAG summaries
4. Embeddings (BGE-M3) - Vector representations

Uses vLLM sleep mode to swap models between stages,
with job state tracking for restart capability.
"""

__version__ = "0.1.0"
