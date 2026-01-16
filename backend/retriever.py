"""GraphRAG Retriever - PostgreSQL-based retrieval for document Q&A.

Replaces Kotaemon's GraphRAGRetrieverPipeline with direct PostgreSQL queries.
Uses pgvector for similarity search and joins for graph traversal.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RetrievalConfig:
    """Configuration for retrieval parameters."""
    top_k_text_units: int = 10
    top_k_entities: int = 10
    top_k_relationships: int = 20
    top_k_community_reports: int = 3


@dataclass
class RetrievedContext:
    """Container for all retrieved context."""
    entities: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    text_units: list[dict] = field(default_factory=list)
    community_reports: list[dict] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Format context for LLM prompt."""
        parts = []

        if self.community_reports:
            parts.append("## Community Summaries\n")
            for cr in self.community_reports:
                title = cr.get("title", "Untitled")
                content = cr.get("full_content") or cr.get("summary") or ""
                parts.append(f"### {title}\n{content}\n\n")

        if self.entities:
            parts.append("## Entities\n")
            for e in self.entities:
                name = e.get("name", "")
                etype = e.get("type", "")
                desc = e.get("description", "")
                if desc:
                    parts.append(f"- **{name}** ({etype}): {desc}\n")
                else:
                    parts.append(f"- **{name}** ({etype})\n")

        if self.relationships:
            parts.append("\n## Relationships\n")
            for r in self.relationships:
                source = r.get("source", "")
                target = r.get("target", "")
                desc = r.get("description", "")
                parts.append(f"- {source} → {target}: {desc}\n")

        if self.text_units:
            parts.append("\n## Source Texts\n")
            for i, tu in enumerate(self.text_units, 1):
                text_content = tu.get("text", "")
                parts.append(f"[{i}] {text_content}\n\n")

        return "".join(parts)


class EmbeddingService:
    """Service for generating embeddings via vLLM."""

    def __init__(self):
        self.vllm_url = os.getenv("VLLM_EMBED_URL", "http://vllm-embed:8000/v1")
        self.model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        response = await self._client.post(
            f"{self.vllm_url}/embeddings",
            json={"model": self.model, "input": text}
        )
        if response.status_code != 200:
            raise RuntimeError(f"Embedding failed: {response.status_code} {response.text}")
        data = response.json()
        return data["data"][0]["embedding"]


class GraphRAGRetriever:
    """PostgreSQL-based GraphRAG retriever.

    Retrieval strategy (pure GraphRAG):
    1. Embed query using BGE-M3
    2. Vector search on entity description embeddings
    3. Get text_units linked to found entities via text_unit_ids
    4. Get relationships for found entities
    5. Get community reports for high-level summaries
    6. Assemble context for LLM
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Optional[RetrievalConfig] = None,
    ):
        self.db = db
        self.config = config or RetrievalConfig()
        self.embedding_service = EmbeddingService()

    async def retrieve(
        self,
        query: str,
        collection_id: int,
    ) -> RetrievedContext:
        """Main retrieval entry point.

        Args:
            query: User's question
            collection_id: Which collection to search

        Returns:
            RetrievedContext with all retrieved information

        Retrieval strategy (standard GraphRAG local search):
        1. Embed query using BGE-M3
        2. Vector search on entity description embeddings
        3. Get text_units linked to found entities
        4. Re-rank text_units by query similarity
        5. Get relationships for found entities
        6. Get community reports connected to found entities
        """
        # Step 1: Embed the query
        query_embedding = await self.embedding_service.embed(query)

        # Step 2: Vector search on entities
        entities = await self._search_entities(
            collection_id, query_embedding, self.config.top_k_entities
        )

        # Step 3: Get text_units linked to found entities
        candidate_text_units = await self._get_text_units_for_entities(
            collection_id, entities, top_k=100
        )

        # Step 4: Re-rank text_units by query similarity
        text_units = await self._rank_text_units_by_query(
            candidate_text_units, query_embedding, max_tokens=4000
        )

        # Step 5: Get relationships for found entities
        entity_names = [e["name"] for e in entities]
        relationships = await self._get_relationships(
            collection_id, entity_names, self.config.top_k_relationships
        )

        # Step 6: Get community reports connected to found entities
        entity_ids = [e["id"] for e in entities]
        entity_communities = await self._get_communities_for_entities(
            collection_id, entity_ids
        )
        community_reports = await self._get_community_reports_for_communities(
            collection_id, entity_communities, self.config.top_k_community_reports
        )

        return RetrievedContext(
            entities=entities,
            relationships=relationships,
            text_units=text_units,
            community_reports=community_reports,
        )

    async def _search_entities(
        self,
        collection_id: int,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict]:
        """Vector similarity search on entity embeddings."""
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        result = await self.db.execute(
            text("""
                SELECT
                    id, name, type, description, text_unit_ids,
                    1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
                FROM entities
                WHERE collection_id = :collection_id
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
            """),
            {
                "collection_id": collection_id,
                "query_embedding": embedding_str,
                "top_k": top_k,
            }
        )

        return [dict(row._mapping) for row in result.fetchall()]

    async def _get_text_units_for_entities(
        self,
        collection_id: int,
        entities: list[dict],
        top_k: int,
    ) -> list[dict]:
        """Get text_units linked to the given entities via text_unit_ids."""
        # Collect all text_unit_ids from entities
        all_text_unit_ids = set()
        for e in entities:
            text_unit_ids = e.get("text_unit_ids") or []
            if isinstance(text_unit_ids, str):
                text_unit_ids = [text_unit_ids]
            all_text_unit_ids.update(text_unit_ids)

        if not all_text_unit_ids:
            return []

        result = await self.db.execute(
            text("""
                SELECT id, text, n_tokens, page_start, page_end, source_file, document_ids
                FROM text_units
                WHERE collection_id = :collection_id
                  AND id = ANY(:text_unit_ids)
                LIMIT :top_k
            """),
            {
                "collection_id": collection_id,
                "text_unit_ids": list(all_text_unit_ids),
                "top_k": top_k,
            }
        )

        return [dict(row._mapping) for row in result.fetchall()]

    async def _get_relationships(
        self,
        collection_id: int,
        entity_names: list[str],
        top_k: int,
    ) -> list[dict]:
        """Get relationships involving the given entities."""
        if not entity_names:
            return []

        result = await self.db.execute(
            text("""
                SELECT
                    id, source, target, description, weight
                FROM relationships
                WHERE collection_id = :collection_id
                  AND (source = ANY(:entity_names) OR target = ANY(:entity_names))
                ORDER BY weight DESC
                LIMIT :top_k
            """),
            {
                "collection_id": collection_id,
                "entity_names": entity_names,
                "top_k": top_k,
            }
        )

        return [dict(row._mapping) for row in result.fetchall()]

    async def _get_community_reports(
        self,
        collection_id: int,
        top_k: int,
    ) -> list[dict]:
        """Get top community reports by rank."""
        result = await self.db.execute(
            text("""
                SELECT
                    id, title, summary, full_content, rank, level
                FROM community_reports
                WHERE collection_id = :collection_id
                ORDER BY rank DESC
                LIMIT :top_k
            """),
            {
                "collection_id": collection_id,
                "top_k": top_k,
            }
        )

        return [dict(row._mapping) for row in result.fetchall()]

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    async def _rank_text_units_by_query(
        self,
        candidates: list[dict],
        query_embedding: list[float],
        max_tokens: int = 4000,
    ) -> list[dict]:
        """Embed each text unit and rank by similarity to query.

        This is the key difference from the broken implementation.
        Kotaemon does this at query time to filter irrelevant linked chunks.
        """
        if not candidates:
            return []

        scored = []
        for tu in candidates:
            text_content = tu.get("text", "")
            if not text_content:
                continue
            # Embed text unit at query time
            tu_embedding = await self.embedding_service.embed(text_content)
            # Cosine similarity
            similarity = self._cosine_similarity(query_embedding, tu_embedding)
            scored.append((similarity, tu))

        # Sort by similarity descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Select top units within token budget
        selected = []
        total_tokens = 0
        for similarity, tu in scored:
            tokens = tu.get("n_tokens") or len(tu.get("text", "")) // 4
            if total_tokens + tokens > max_tokens:
                break
            selected.append(tu)
            total_tokens += tokens

        return selected

    async def _get_communities_for_entities(
        self,
        collection_id: int,
        entity_ids: list[str],
    ) -> list[int]:
        """Look up community assignments for entities via nodes table."""
        if not entity_ids:
            return []

        result = await self.db.execute(
            text("""
                SELECT DISTINCT community FROM nodes
                WHERE collection_id = :collection_id
                  AND id = ANY(:entity_ids)
                  AND community IS NOT NULL
            """),
            {
                "collection_id": collection_id,
                "entity_ids": entity_ids,
            }
        )

        return [row.community for row in result.fetchall()]

    async def _get_community_reports_for_communities(
        self,
        collection_id: int,
        community_ids: list[int],
        top_k: int,
    ) -> list[dict]:
        """Get reports for communities that contain found entities.

        This connects community reports to the query via entities,
        rather than just returning top-ranked reports globally.
        """
        if not community_ids:
            # Fallback to global top-k if no community links
            return await self._get_community_reports(collection_id, top_k)

        result = await self.db.execute(
            text("""
                SELECT id, title, summary, full_content, rank, level
                FROM community_reports
                WHERE collection_id = :collection_id
                  AND community = ANY(:community_ids)
                ORDER BY rank DESC
                LIMIT :top_k
            """),
            {
                "collection_id": collection_id,
                "community_ids": community_ids,
                "top_k": top_k,
            }
        )

        return [dict(row._mapping) for row in result.fetchall()]
