"""
Pipeline Orchestrator CLI

Command-line interface for managing document indexing jobs.

Usage:
    python -m indexer.cli create --name "My Job" /path/to/*.pdf
    python -m indexer.cli run <job_id>
    python -m indexer.cli run <job_id> --from-stage entity_extraction
    python -m indexer.cli status <job_id>
    python -m indexer.cli list
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from .job import (
    DEFAULT_JOBS_DIR,
    STAGE_ORDER,
    StageName,
    create_job,
    format_job_status,
    list_jobs,
    load_job,
)
from .orchestrator import PipelineOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--jobs-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_JOBS_DIR,
    help="Directory for job state files",
)
@click.pass_context
def cli(ctx: click.Context, jobs_dir: Path) -> None:
    """Document indexing pipeline orchestrator.

    Manages GPU-aware document processing through stages:
    OCR → Entity Extraction → Community Reports → Embeddings
    """
    ctx.ensure_object(dict)
    ctx.obj["jobs_dir"] = jobs_dir


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--name", "-n", required=True, help="Human-readable job name")
@click.pass_context
def create(ctx: click.Context, files: tuple[Path, ...], name: str) -> None:
    """Create a new indexing job.

    FILES: One or more PDF files to process.

    Example:
        indexer create --name "CReDO Collection" /data/pdfs/*.pdf
    """
    if not files:
        click.echo("Error: At least one input file is required", err=True)
        sys.exit(1)

    # Validate all files are PDFs
    pdf_files = []
    for f in files:
        if f.suffix.lower() != ".pdf":
            click.echo(f"Warning: Skipping non-PDF file: {f}", err=True)
        else:
            pdf_files.append(f)

    if not pdf_files:
        click.echo("Error: No valid PDF files provided", err=True)
        sys.exit(1)

    jobs_dir = ctx.obj["jobs_dir"]
    job = create_job(name=name, input_files=pdf_files, jobs_dir=jobs_dir)

    click.echo(f"Created job: {job['job_id']}")
    click.echo(f"  Name: {job['name']}")
    click.echo(f"  Files: {len(pdf_files)}")
    click.echo(f"  Output: {job['output_dir']}")
    click.echo()
    click.echo(f"Run with: python -m indexer.cli run {job['job_id']}")


@cli.command()
@click.argument("job_id")
@click.option(
    "--from-stage",
    type=click.Choice(STAGE_ORDER),
    help="Resume from specific stage (default: auto-detect)",
)
@click.option(
    "--stop-after",
    type=click.Choice(STAGE_ORDER),
    help="Stop after specific stage",
)
@click.pass_context
def run(
    ctx: click.Context,
    job_id: str,
    from_stage: StageName | None,
    stop_after: StageName | None,
) -> None:
    """Run or resume an indexing job.

    JOB_ID: The job identifier from 'create' command.

    Examples:
        indexer run abc123
        indexer run abc123 --from-stage entity_extraction
        indexer run abc123 --stop-after ocr
    """
    jobs_dir = ctx.obj["jobs_dir"]

    try:
        job = load_job(job_id, jobs_dir=jobs_dir)
    except FileNotFoundError:
        click.echo(f"Error: Job not found: {job_id}", err=True)
        sys.exit(1)

    click.echo(f"Starting job: {job['job_id']} - {job['name']}")
    click.echo(f"  Input files: {len(job['input_files'])}")
    click.echo(f"  Output dir: {job['output_dir']}")
    click.echo()

    orchestrator = PipelineOrchestrator(jobs_dir=jobs_dir)

    try:
        final_job = asyncio.run(
            orchestrator.run_job(
                job_id=job_id,
                resume_from=from_stage,
                stop_after=stop_after,
            )
        )

        if final_job["status"] == "completed":
            click.echo()
            click.echo("Job completed successfully!")
            _print_job_stats(final_job)
        else:
            click.echo()
            click.echo(f"Job status: {final_job['status']}")
            if final_job.get("error"):
                click.echo(f"Error: {final_job['error']}", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("job_id")
@click.pass_context
def status(ctx: click.Context, job_id: str) -> None:
    """Show job status.

    JOB_ID: The job identifier.
    """
    jobs_dir = ctx.obj["jobs_dir"]

    try:
        job = load_job(job_id, jobs_dir=jobs_dir)
    except FileNotFoundError:
        click.echo(f"Error: Job not found: {job_id}", err=True)
        sys.exit(1)

    click.echo(format_job_status(job))


@cli.command("list")
@click.option("--limit", "-l", default=10, help="Maximum jobs to show")
@click.pass_context
def list_cmd(ctx: click.Context, limit: int) -> None:
    """List all jobs."""
    jobs_dir = ctx.obj["jobs_dir"]

    jobs = list_jobs(jobs_dir=jobs_dir)

    if not jobs:
        click.echo("No jobs found")
        return

    click.echo(f"Jobs ({len(jobs)} total):\n")

    status_icons = {
        "pending": "○",
        "running": "◐",
        "completed": "●",
        "failed": "✗",
    }

    for job in jobs[:limit]:
        icon = status_icons.get(job["status"], "?")
        stage = job.get("current_stage") or "-"
        click.echo(f"  {icon} {job['job_id']}  {job['name'][:30]:<30}  {job['status']:<10}  {stage}")

    if len(jobs) > limit:
        click.echo(f"\n  ... and {len(jobs) - limit} more")


@cli.command()
@click.argument("job_id")
@click.pass_context
def stats(ctx: click.Context, job_id: str) -> None:
    """Show detailed job statistics.

    JOB_ID: The job identifier.
    """
    jobs_dir = ctx.obj["jobs_dir"]

    try:
        job = load_job(job_id, jobs_dir=jobs_dir)
    except FileNotFoundError:
        click.echo(f"Error: Job not found: {job_id}", err=True)
        sys.exit(1)

    _print_job_stats(job)


def _print_job_stats(job: dict) -> None:
    """Print detailed job statistics."""
    click.echo(f"\nJob Statistics: {job['job_id']}")
    click.echo("=" * 50)

    for stage in STAGE_ORDER:
        stage_data = job["stages"][stage]
        click.echo(f"\n{stage}:")
        click.echo(f"  Status: {stage_data['status']}")

        if stage_data.get("started_at"):
            click.echo(f"  Started: {stage_data['started_at']}")
        if stage_data.get("completed_at"):
            click.echo(f"  Completed: {stage_data['completed_at']}")

        if stage_data.get("stats"):
            click.echo("  Stats:")
            for key, value in stage_data["stats"].items():
                click.echo(f"    {key}: {value}")

        if stage_data.get("error"):
            click.echo(f"  Error: {stage_data['error']}")


def main() -> None:
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
