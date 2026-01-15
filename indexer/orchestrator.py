"""
Pipeline Orchestrator

Coordinates the execution of indexing stages:
1. OCR - PDF extraction with Docling (subprocess for GPU isolation)
2. Entity Extraction - LFM2 via GraphRAG
3. Community Reports - Qwen via GraphRAG
4. Embeddings - BGE-M3 via GraphRAG

Manages vLLM sleep/wake transitions between stages to optimize GPU usage.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .job import (
    DEFAULT_JOBS_DIR,
    STAGE_ORDER,
    JobStatus,
    StageName,
    create_job,
    find_resume_point,
    format_job_status,
    load_job,
    save_job,
    update_stage,
)
from .stages.graphrag import run_graphrag_stage
from .stages.ocr import get_text_files, run_ocr_stage
from .vllm_controller import VLLMController

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the document indexing pipeline."""

    def __init__(self, jobs_dir: Path = DEFAULT_JOBS_DIR):
        """Initialize orchestrator.

        Args:
            jobs_dir: Directory to store job state files
        """
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.vllm = VLLMController()

    def create_job(self, name: str, input_files: list[str | Path]) -> dict[str, Any]:
        """Create a new indexing job.

        Args:
            name: Human-readable job name
            input_files: List of PDF files to process

        Returns:
            Job dict
        """
        return create_job(name, input_files, jobs_dir=self.jobs_dir)

    def load_job(self, job_id: str) -> dict[str, Any]:
        """Load an existing job.

        Args:
            job_id: Job identifier

        Returns:
            Job dict
        """
        return load_job(job_id, jobs_dir=self.jobs_dir)

    def get_job_status(self, job_id: str) -> str:
        """Get formatted job status.

        Args:
            job_id: Job identifier

        Returns:
            Formatted status string
        """
        job = self.load_job(job_id)
        return format_job_status(job)

    async def run_job(
        self,
        job_id: str,
        resume_from: StageName | None = None,
        stop_after: StageName | None = None,
    ) -> dict[str, Any]:
        """Run or resume a job.

        Args:
            job_id: Job identifier
            resume_from: Stage to resume from (default: auto-detect)
            stop_after: Stage to stop after (default: run all)

        Returns:
            Final job dict
        """
        job = self.load_job(job_id)

        # Determine starting point
        if resume_from:
            start_idx = STAGE_ORDER.index(resume_from)
            logger.info(f"[Orchestrator] Resuming from {resume_from}")
        else:
            resume_stage = find_resume_point(job)
            if resume_stage is None:
                logger.info("[Orchestrator] Job already complete")
                return job
            start_idx = STAGE_ORDER.index(resume_stage)
            logger.info(f"[Orchestrator] Auto-resuming from {resume_stage}")

        # Determine stopping point
        if stop_after:
            stop_idx = STAGE_ORDER.index(stop_after)
        else:
            stop_idx = len(STAGE_ORDER) - 1

        # Update job status
        job["status"] = "running"
        save_job(job, self.jobs_dir)

        # Run stages
        try:
            for i in range(start_idx, stop_idx + 1):
                stage = STAGE_ORDER[i]
                logger.info(f"[Orchestrator] Starting stage: {stage}")

                update_stage(job, stage, "running", jobs_dir=self.jobs_dir)

                try:
                    stats = await self._run_stage(job, stage)
                    update_stage(
                        job, stage, "completed",
                        stats=stats,
                        jobs_dir=self.jobs_dir
                    )
                    logger.info(f"[Orchestrator] Completed stage: {stage}")

                except Exception as e:
                    logger.error(f"[Orchestrator] Stage {stage} failed: {e}")
                    update_stage(
                        job, stage, "failed",
                        error=str(e),
                        jobs_dir=self.jobs_dir
                    )
                    job["status"] = "failed"
                    job["error"] = f"Stage {stage} failed: {e}"
                    save_job(job, self.jobs_dir)
                    raise

            # All stages complete
            job["status"] = "completed"
            save_job(job, self.jobs_dir)
            logger.info("[Orchestrator] Job completed successfully")

        except Exception:
            # Job failed - status already updated
            pass

        return job

    async def _run_stage(self, job: dict[str, Any], stage: StageName) -> dict[str, Any]:
        """Run a single pipeline stage.

        Args:
            job: Job dict
            stage: Stage to run

        Returns:
            Stage stats dict
        """
        output_dir = Path(job["output_dir"])

        if stage == "ocr":
            return await self._run_ocr(job, output_dir)
        elif stage == "entity_extraction":
            return await self._run_entity_extraction(job, output_dir)
        elif stage == "community_reports":
            return await self._run_community_reports(job, output_dir)
        elif stage == "embeddings":
            return await self._run_embeddings(job, output_dir)
        else:
            raise ValueError(f"Unknown stage: {stage}")

    async def _run_ocr(self, job: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        """Run OCR stage.

        Stops all vLLM containers to free GPU memory for Docling.
        Note: Sleep mode does NOT release GPU memory - must actually stop containers.
        """
        logger.info("[OCR] Stopping all vLLM containers to free GPU...")
        self.vllm.stop_all_containers()

        # Small delay to ensure GPU memory is freed
        await asyncio.sleep(3.0)

        # Run OCR in subprocess (GPU isolated)
        text_output_dir = output_dir / "text"
        results = run_ocr_stage(
            input_files=job["input_files"],
            output_dir=text_output_dir,
        )

        return results.get("stats", {})

    async def _run_entity_extraction(
        self, job: dict[str, Any], output_dir: Path
    ) -> dict[str, Any]:
        """Run entity extraction stage.

        Starts LFM2 and embed containers (chat stays stopped), runs GraphRAG entity workflows.
        Entity extraction needs embeddings for create_final_entities workflow.
        LFM2 1.2B (~3GB) + BGE-M3 (~2.5GB) fit together in 24GB GPU.
        """
        logger.info("[Entity] Starting LFM2 and BGE-M3 containers...")
        self.vllm.stop_all_containers()

        # Start both entity extraction and embedding models
        await self.vllm.start_container("entity", wait_healthy=True, timeout=120.0)
        await self.vllm.start_container("embed", wait_healthy=True, timeout=60.0)

        # Small delay for models to be fully ready
        await asyncio.sleep(2.0)

        # Run GraphRAG entity extraction
        text_dir = output_dir / "text"
        results = run_graphrag_stage(
            stage="entity",
            input_dir=text_dir,
            output_dir=output_dir,
        )

        return results.get("stats", {})

    async def _run_community_reports(
        self, job: dict[str, Any], output_dir: Path
    ) -> dict[str, Any]:
        """Run community reports stage.

        Starts Qwen container (stops others), runs GraphRAG community workflows.
        """
        logger.info("[Community] Starting Qwen container...")
        await self.vllm.start_only("chat", timeout=120.0)

        # Small delay for model to be fully ready
        await asyncio.sleep(2.0)

        # Run GraphRAG community reports
        text_dir = output_dir / "text"
        results = run_graphrag_stage(
            stage="community",
            input_dir=text_dir,
            output_dir=output_dir,
        )

        return results.get("stats", {})

    async def _run_embeddings(
        self, job: dict[str, Any], output_dir: Path
    ) -> dict[str, Any]:
        """Run embeddings stage.

        Starts BGE-M3 (embed) container, stops others.
        Note: Embeddings are currently computed during entity extraction.
        """
        logger.info("[Embeddings] Starting BGE-M3 container...")
        await self.vllm.start_only("embed", timeout=60.0)

        # Embeddings are computed as part of entity extraction in current GraphRAG
        # This stage is a placeholder for potential standalone embedding computation
        logger.info("[Embeddings] Embeddings computed during entity extraction")

        return {"note": "embeddings_computed_in_entity_stage"}


async def run_pipeline(
    job_id: str,
    jobs_dir: Path = DEFAULT_JOBS_DIR,
    resume_from: StageName | None = None,
) -> dict[str, Any]:
    """Convenience function to run a pipeline.

    Args:
        job_id: Job identifier
        jobs_dir: Directory containing job files
        resume_from: Stage to resume from

    Returns:
        Final job dict
    """
    orchestrator = PipelineOrchestrator(jobs_dir)
    return await orchestrator.run_job(job_id, resume_from=resume_from)
