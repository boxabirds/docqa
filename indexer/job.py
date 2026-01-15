"""
Job State Management

Tracks indexing job progress in JSON files for:
- Status monitoring
- Restart capability after failures
- Stage-level progress tracking
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

JobStatus = Literal["pending", "running", "completed", "failed"]
StageStatus = Literal["pending", "running", "completed", "failed", "skipped"]
StageName = Literal["ocr", "entity_extraction", "community_reports", "embeddings"]

# Default jobs directory
DEFAULT_JOBS_DIR = Path("/app/indexer_jobs")

# Stage execution order
STAGE_ORDER: list[StageName] = [
    "ocr",
    "entity_extraction",
    "community_reports",
    "embeddings",
]


def now_iso() -> str:
    """Get current time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def create_job(
    name: str,
    input_files: list[str | Path],
    output_dir: str | Path | None = None,
    jobs_dir: Path = DEFAULT_JOBS_DIR,
) -> dict[str, Any]:
    """Create a new indexing job.

    Args:
        name: Human-readable job name
        input_files: List of PDF files to process
        output_dir: Where to store outputs (default: jobs_dir/<job_id>)
        jobs_dir: Directory to store job state files

    Returns:
        Job dict (also saved to disk)
    """
    job_id = str(uuid.uuid4())[:8]

    if output_dir is None:
        output_dir = jobs_dir / job_id / "output"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "job_id": job_id,
        "name": name,
        "status": "pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "input_files": [str(f) for f in input_files],
        "output_dir": str(output_dir),
        "current_stage": None,
        "stages": {
            stage: {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "progress": None,
                "stats": {},
                "error": None,
            }
            for stage in STAGE_ORDER
        },
        "error": None,
    }

    save_job(job, jobs_dir)
    logger.info(f"Created job {job_id}: {name}")
    return job


def load_job(job_id: str, jobs_dir: Path = DEFAULT_JOBS_DIR) -> dict[str, Any]:
    """Load job state from disk.

    Args:
        job_id: Job identifier
        jobs_dir: Directory containing job files

    Returns:
        Job dict

    Raises:
        FileNotFoundError: If job doesn't exist
    """
    job_file = jobs_dir / job_id / "job.json"

    if not job_file.exists():
        raise FileNotFoundError(f"Job not found: {job_id}")

    with open(job_file) as f:
        return json.load(f)


def save_job(job: dict[str, Any], jobs_dir: Path = DEFAULT_JOBS_DIR) -> None:
    """Save job state to disk.

    Args:
        job: Job dict to save
        jobs_dir: Directory to store job files
    """
    job["updated_at"] = now_iso()

    job_dir = jobs_dir / job["job_id"]
    job_dir.mkdir(parents=True, exist_ok=True)

    job_file = job_dir / "job.json"
    with open(job_file, "w") as f:
        json.dump(job, f, indent=2)


def list_jobs(jobs_dir: Path = DEFAULT_JOBS_DIR) -> list[dict[str, Any]]:
    """List all jobs.

    Args:
        jobs_dir: Directory containing job files

    Returns:
        List of job dicts (summary info only)
    """
    jobs = []

    if not jobs_dir.exists():
        return jobs

    for job_dir in jobs_dir.iterdir():
        if job_dir.is_dir():
            job_file = job_dir / "job.json"
            if job_file.exists():
                try:
                    job = load_job(job_dir.name, jobs_dir)
                    jobs.append({
                        "job_id": job["job_id"],
                        "name": job["name"],
                        "status": job["status"],
                        "current_stage": job["current_stage"],
                        "created_at": job["created_at"],
                        "updated_at": job["updated_at"],
                    })
                except Exception as e:
                    logger.warning(f"Error loading job {job_dir.name}: {e}")

    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)


def update_stage(
    job: dict[str, Any],
    stage: StageName,
    status: StageStatus,
    progress: dict | None = None,
    stats: dict | None = None,
    error: str | None = None,
    jobs_dir: Path = DEFAULT_JOBS_DIR,
) -> None:
    """Update stage status and save job.

    Args:
        job: Job dict to update
        stage: Stage name
        status: New status
        progress: Optional progress info (e.g., {"completed": 50, "total": 100})
        stats: Optional stats to merge
        error: Optional error message
        jobs_dir: Directory containing job files
    """
    stage_data = job["stages"][stage]

    if status == "running" and stage_data["status"] != "running":
        stage_data["started_at"] = now_iso()
    elif status in ("completed", "failed"):
        stage_data["completed_at"] = now_iso()

    stage_data["status"] = status

    if progress is not None:
        stage_data["progress"] = progress

    if stats is not None:
        stage_data["stats"].update(stats)

    if error is not None:
        stage_data["error"] = error

    job["current_stage"] = stage
    save_job(job, jobs_dir)


def find_resume_point(job: dict[str, Any]) -> StageName | None:
    """Find the stage to resume from.

    Returns the first non-completed stage, or None if all complete.

    Args:
        job: Job dict

    Returns:
        Stage name to resume from, or None
    """
    for stage in STAGE_ORDER:
        status = job["stages"][stage]["status"]
        if status in ("pending", "failed", "running"):
            return stage
    return None


def format_job_status(job: dict[str, Any]) -> str:
    """Format job status for display.

    Args:
        job: Job dict

    Returns:
        Formatted status string
    """
    lines = [
        f"Job: {job['job_id']} - {job['name']}",
        f"Status: {job['status']}",
        f"Created: {job['created_at']}",
        f"Updated: {job['updated_at']}",
        "",
        "Stages:",
    ]

    status_icons = {
        "pending": "○",
        "running": "◐",
        "completed": "●",
        "failed": "✗",
        "skipped": "○",
    }

    for stage in STAGE_ORDER:
        stage_data = job["stages"][stage]
        icon = status_icons.get(stage_data["status"], "?")
        line = f"  {icon} {stage}: {stage_data['status']}"

        if stage_data["progress"]:
            p = stage_data["progress"]
            if "completed" in p and "total" in p:
                line += f" ({p['completed']}/{p['total']})"

        if stage_data["error"]:
            line += f" - {stage_data['error'][:50]}"

        lines.append(line)

    if job["error"]:
        lines.append("")
        lines.append(f"Error: {job['error']}")

    return "\n".join(lines)
