"""
Allow running the indexer as a module.

Usage:
    python -m indexer create --name "Job" /path/to/files.pdf
    python -m indexer run <job_id>
    python -m indexer status <job_id>
    python -m indexer list
"""

from .cli import main

if __name__ == "__main__":
    main()
