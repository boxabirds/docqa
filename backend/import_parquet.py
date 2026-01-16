#!/usr/bin/env python3
"""Import GraphRAG parquet output into PostgreSQL.

Usage:
    python -m backend.import_parquet /path/to/parquet/output "Collection Name"
"""
import argparse
import asyncio
import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Support both module and standalone execution
try:
    from .database import get_db_session
except ImportError:
    from database import get_db_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_page_numbers(text_content: str) -> tuple[int | None, int | None]:
    """Extract page numbers from text containing <!-- PAGE N --> markers.

    Returns:
        Tuple of (page_start, page_end) or (None, None) if no markers found
    """
    if not text_content:
        return None, None

    pages = re.findall(r'<!-- PAGE (\d+) -->', text_content)
    if not pages:
        return None, None

    page_nums = [int(p) for p in pages]
    return min(page_nums), max(page_nums)


async def import_collection(parquet_dir: Path, collection_name: str) -> int:
    """Import GraphRAG parquet output into PostgreSQL.

    Args:
        parquet_dir: Directory containing parquet files
        collection_name: Name for this collection

    Returns:
        Collection ID
    """
    parquet_dir = Path(parquet_dir)
    if not parquet_dir.exists():
        raise ValueError(f"Directory not found: {parquet_dir}")

    async with get_db_session() as db:
        # Create collection
        result = await db.execute(
            text("INSERT INTO collections (name) VALUES (:name) RETURNING id"),
            {"name": collection_name}
        )
        collection_id = result.scalar_one()
        logger.info(f"Created collection '{collection_name}' with ID {collection_id}")

        # Import in dependency order
        await _import_documents(db, collection_id, parquet_dir)
        await _import_text_units(db, collection_id, parquet_dir)
        await _import_entities(db, collection_id, parquet_dir)
        await _import_nodes(db, collection_id, parquet_dir)
        await _import_relationships(db, collection_id, parquet_dir)
        await _import_communities(db, collection_id, parquet_dir)
        await _import_community_reports(db, collection_id, parquet_dir)

        # Post-process: populate source_file in text_units from documents
        await _update_text_unit_source_files(db, collection_id)

        await db.commit()
        logger.info(f"Import complete for collection {collection_id}")
        return collection_id


async def _update_text_unit_source_files(db, collection_id: int):
    """Populate source_file in text_units from linked documents."""
    # Update source_file for text_units where document_ids[1] matches a document
    # PostgreSQL array syntax: document_ids[1] gets the first element
    result = await db.execute(
        text("""
            UPDATE text_units tu
            SET source_file = d.original_filename
            FROM documents d
            WHERE tu.collection_id = :collection_id
              AND tu.document_ids[1] = d.id
              AND tu.source_file IS NULL
        """),
        {"collection_id": collection_id}
    )
    logger.info(f"Updated source_file for text units")


async def _import_documents(db, collection_id: int, parquet_dir: Path):
    """Import documents from create_final_documents.parquet."""
    path = parquet_dir / "create_final_documents.parquet"
    if not path.exists():
        logger.warning("No documents parquet found")
        return

    df = pd.read_parquet(path)
    logger.info(f"Importing {len(df)} documents")

    # Check for stored PDFs directory
    pdf_storage = parquet_dir / "pdfs"

    for _, row in df.iterrows():
        source = row.get("source")
        title = row.get("title", "")

        # Derive original filename and pdf_path
        # Source may be empty - fall back to title and replace .txt with .pdf
        original_filename = None
        pdf_path = None

        # First try source, then title
        text_name = source if source else title
        if text_name:
            # Convert .txt to .pdf
            original_filename = Path(text_name).stem + ".pdf"
            # Check if PDF is stored in the pdfs subdirectory
            if pdf_storage.exists():
                stored_pdf = pdf_storage / original_filename
                if stored_pdf.exists():
                    pdf_path = str(stored_pdf)

        await db.execute(
            text("""
                INSERT INTO documents (id, collection_id, title, source, original_filename, pdf_path, raw_content)
                VALUES (:id, :collection_id, :title, :source, :original_filename, :pdf_path, :raw_content)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(row.get("id", "")),
                "collection_id": collection_id,
                "title": row.get("title"),
                "source": source,
                "original_filename": original_filename,
                "pdf_path": pdf_path,
                "raw_content": row.get("raw_content"),
            }
        )


async def _import_text_units(db, collection_id: int, parquet_dir: Path):
    """Import text units from create_final_text_units.parquet."""
    path = parquet_dir / "create_final_text_units.parquet"
    if not path.exists():
        logger.warning("No text_units parquet found")
        return

    df = pd.read_parquet(path)
    logger.info(f"Importing {len(df)} text units")

    for _, row in df.iterrows():
        # Handle document_ids - could be list or string
        doc_ids = row.get("document_ids", [])
        if isinstance(doc_ids, str):
            doc_ids = [doc_ids]
        elif hasattr(doc_ids, "tolist"):
            doc_ids = doc_ids.tolist()

        # Handle embedding - could be numpy array or list
        embedding = row.get("embedding")
        if embedding is not None:
            if hasattr(embedding, "tolist"):
                embedding = embedding.tolist()
            # Convert to pgvector format string: [1.0, 2.0, 3.0]
            embedding = "[" + ",".join(str(x) for x in embedding) + "]"

        # Extract page numbers from text content (if page markers present)
        text_content = row.get("text", "")
        page_start, page_end = extract_page_numbers(text_content)

        # Get source_file from parquet if available (set during indexing)
        source_file = row.get("source_file")
        if pd.isna(source_file):
            source_file = None

        await db.execute(
            text("""
                INSERT INTO text_units (id, collection_id, document_ids, text, n_tokens, page_start, page_end, source_file, embedding)
                VALUES (:id, :collection_id, :document_ids, :text, :n_tokens, :page_start, :page_end, :source_file, :embedding)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(row.get("id", "")),
                "collection_id": collection_id,
                "document_ids": doc_ids,
                "text": text_content,
                "n_tokens": int(row.get("n_tokens", 0)) if pd.notna(row.get("n_tokens")) else None,
                "page_start": page_start,
                "page_end": page_end,
                "source_file": source_file,
                "embedding": embedding,
            }
        )


async def _import_entities(db, collection_id: int, parquet_dir: Path):
    """Import entities from create_final_entities.parquet."""
    path = parquet_dir / "create_final_entities.parquet"
    if not path.exists():
        logger.warning("No entities parquet found")
        return

    df = pd.read_parquet(path)
    logger.info(f"Importing {len(df)} entities")

    for _, row in df.iterrows():
        # Handle text_unit_ids - could be list or string
        text_unit_ids = row.get("text_unit_ids", [])
        if isinstance(text_unit_ids, str):
            text_unit_ids = [text_unit_ids]
        elif hasattr(text_unit_ids, "tolist"):
            text_unit_ids = text_unit_ids.tolist()

        # Handle embedding - GraphRAG uses 'description_embedding' not 'embedding'
        embedding = row.get("description_embedding")
        if embedding is None or (hasattr(embedding, '__len__') and len(embedding) == 0):
            embedding = row.get("embedding")
        if embedding is not None:
            if hasattr(embedding, "tolist"):
                embedding = embedding.tolist()
            # Convert to pgvector format string: [1.0, 2.0, 3.0]
            embedding = "[" + ",".join(str(x) for x in embedding) + "]"

        # GraphRAG uses different column names in different versions
        name = row.get("name") or row.get("title") or row.get("entity") or ""
        entity_type = row.get("type") or row.get("entity_type") or ""
        description = row.get("description") or row.get("entity_description") or ""

        await db.execute(
            text("""
                INSERT INTO entities (id, collection_id, name, type, description, text_unit_ids, embedding)
                VALUES (:id, :collection_id, :name, :type, :description, :text_unit_ids, :embedding)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(row.get("id", "")),
                "collection_id": collection_id,
                "name": name,
                "type": entity_type,
                "description": description,
                "text_unit_ids": text_unit_ids,
                "embedding": embedding,
            }
        )


async def _import_nodes(db, collection_id: int, parquet_dir: Path):
    """Import nodes from create_final_nodes.parquet."""
    path = parquet_dir / "create_final_nodes.parquet"
    if not path.exists():
        logger.warning("No nodes parquet found")
        return

    df = pd.read_parquet(path)
    logger.info(f"Importing {len(df)} nodes")

    for _, row in df.iterrows():
        community = row.get("community")
        if pd.isna(community):
            community = None
        else:
            community = int(community)

        await db.execute(
            text("""
                INSERT INTO nodes (id, collection_id, community, level, degree)
                VALUES (:id, :collection_id, :community, :level, :degree)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(row.get("id", "")),
                "collection_id": collection_id,
                "community": community,
                "level": int(row.get("level", 0)) if pd.notna(row.get("level")) else 0,
                "degree": int(row.get("degree", 0)) if pd.notna(row.get("degree")) else 0,
            }
        )


async def _import_relationships(db, collection_id: int, parquet_dir: Path):
    """Import relationships from create_final_relationships.parquet."""
    path = parquet_dir / "create_final_relationships.parquet"
    if not path.exists():
        logger.warning("No relationships parquet found")
        return

    df = pd.read_parquet(path)
    logger.info(f"Importing {len(df)} relationships")

    for _, row in df.iterrows():
        # Handle text_unit_ids
        text_unit_ids = row.get("text_unit_ids", [])
        if isinstance(text_unit_ids, str):
            text_unit_ids = [text_unit_ids]
        elif hasattr(text_unit_ids, "tolist"):
            text_unit_ids = text_unit_ids.tolist()

        await db.execute(
            text("""
                INSERT INTO relationships (id, collection_id, source, target, description, weight, text_unit_ids)
                VALUES (:id, :collection_id, :source, :target, :description, :weight, :text_unit_ids)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(row.get("id", "")),
                "collection_id": collection_id,
                "source": row.get("source", ""),
                "target": row.get("target", ""),
                "description": row.get("description", ""),
                "weight": float(row.get("weight", 1.0)) if pd.notna(row.get("weight")) else 1.0,
                "text_unit_ids": text_unit_ids,
            }
        )


async def _import_communities(db, collection_id: int, parquet_dir: Path):
    """Import communities from create_final_communities.parquet."""
    path = parquet_dir / "create_final_communities.parquet"
    if not path.exists():
        logger.warning("No communities parquet found")
        return

    df = pd.read_parquet(path)
    logger.info(f"Importing {len(df)} communities")

    for _, row in df.iterrows():
        await db.execute(
            text("""
                INSERT INTO communities (id, collection_id, community, level, title)
                VALUES (:id, :collection_id, :community, :level, :title)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(row.get("id", "")),
                "collection_id": collection_id,
                "community": int(row.get("community", 0)) if pd.notna(row.get("community")) else 0,
                "level": int(row.get("level", 0)) if pd.notna(row.get("level")) else 0,
                "title": row.get("title"),
            }
        )


async def _import_community_reports(db, collection_id: int, parquet_dir: Path):
    """Import community reports from create_final_community_reports.parquet."""
    path = parquet_dir / "create_final_community_reports.parquet"
    if not path.exists():
        logger.warning("No community_reports parquet found")
        return

    df = pd.read_parquet(path)
    logger.info(f"Importing {len(df)} community reports")

    for _, row in df.iterrows():
        await db.execute(
            text("""
                INSERT INTO community_reports (id, collection_id, community, level, title, summary, full_content, rank)
                VALUES (:id, :collection_id, :community, :level, :title, :summary, :full_content, :rank)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(row.get("id", "")),
                "collection_id": collection_id,
                "community": int(row.get("community", 0)) if pd.notna(row.get("community")) else 0,
                "level": int(row.get("level", 0)) if pd.notna(row.get("level")) else 0,
                "title": row.get("title"),
                "summary": row.get("summary"),
                "full_content": row.get("full_content") or row.get("content"),
                "rank": float(row.get("rank", 0)) if pd.notna(row.get("rank")) else 0,
            }
        )


def main():
    parser = argparse.ArgumentParser(description="Import GraphRAG parquet output into PostgreSQL")
    parser.add_argument("parquet_dir", type=Path, help="Directory containing parquet files")
    parser.add_argument("collection_name", type=str, help="Name for this collection")
    args = parser.parse_args()

    collection_id = asyncio.run(import_collection(args.parquet_dir, args.collection_name))
    print(f"Imported collection ID: {collection_id}")


if __name__ == "__main__":
    main()
