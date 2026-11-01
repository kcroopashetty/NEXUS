"""PostgreSQL + pgvector implementation of the VectorStore interface."""

import logging
import math
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, update

from app.db.session import SessionLocal
from app.models import DocumentChunk
from app.services.vector_store.base import VectorStore, VectorSearchResult

logger = logging.getLogger("nexus.vector_store.pgvector")


class PgVectorStore(VectorStore):
    """
    PostgreSQL vector store storing dense embeddings directly in `document_chunks.embedding`.
    Eliminates secondary vector-database synchronization overhead.
    """

    def __init__(self, db_session_factory=SessionLocal):
        self._session_factory = db_session_factory

    def index_chunks(
        self,
        tenant_id: uuid.UUID,
        vectors: List[List[float]],
        vector_ids: List[str],
        metadatas: List[Dict[str, Any]],
        documents: List[str],
    ) -> None:
        """
        Update the `embedding` column for the specified document chunks.
        """
        if not vector_ids:
            return

        with self._session_factory() as db:
            for vec_id, emb, meta in zip(vector_ids, vectors, metadatas):
                chunk_id_str = meta.get("chunk_id")
                if not chunk_id_str:
                    continue
                try:
                    c_id = uuid.UUID(chunk_id_str)
                    db.execute(
                        update(DocumentChunk)
                        .where(DocumentChunk.id == c_id, DocumentChunk.tenant_id == tenant_id)
                        .values(embedding=emb, vector_id=vec_id)
                    )
                except Exception as exc:
                    logger.warning("PgVectorStore failed to index chunk %s: %s", chunk_id_str, exc)
            db.commit()

    def search_candidates(
        self,
        tenant_id: uuid.UUID,
        query_vector: List[float],
        top_k: int = 10,
    ) -> List[VectorSearchResult]:
        """
        Query top-k candidate chunks from the PostgreSQL vector store for a tenant.
        """
        with self._session_factory() as db:
            bind = db.get_bind()
            is_postgres = bind is not None and bind.dialect.name == "postgresql"

            if is_postgres:
                # PostgreSQL native HNSW / cosine distance query
                query = (
                    select(
                        DocumentChunk.id,
                        DocumentChunk.version_id,
                        DocumentChunk.vector_id,
                        DocumentChunk.allowed_roles,
                        DocumentChunk.page_start,
                        DocumentChunk.page_end,
                        DocumentChunk.embedding.cosine_distance(query_vector).label("dist"),
                    )
                    .where(
                        and_(
                            DocumentChunk.tenant_id == tenant_id,
                            DocumentChunk.embedding.isnot(None),
                        )
                    )
                    .order_by(DocumentChunk.embedding.cosine_distance(query_vector).asc())
                    .limit(top_k)
                )
                rows = db.execute(query).fetchall()
                results = []
                for r in rows:
                    dist = float(r.dist) if r.dist is not None else 1.0
                    similarity = round(max(0.0, 1.0 - dist), 4)
                    results.append(
                        VectorSearchResult(
                            vector_id=r.vector_id,
                            chunk_id=r.id,
                            version_id=r.version_id,
                            score=similarity,
                            metadata={
                                "chunk_id": str(r.id),
                                "version_id": str(r.version_id),
                                "allowed_roles": r.allowed_roles,
                                "page_start": r.page_start,
                                "page_end": r.page_end,
                            },
                        )
                    )
                return results

            else:
                # SQLite fallback: calculate cosine similarity in Python
                query = select(DocumentChunk).where(
                    and_(
                        DocumentChunk.tenant_id == tenant_id,
                        DocumentChunk.embedding.isnot(None),
                    )
                )
                chunks = db.execute(query).scalars().all()
                scored = []
                for c in chunks:
                    score = 0.5
                    if c.embedding and len(c.embedding) == len(query_vector):
                        dot = sum(a * b for a, b in zip(c.embedding, query_vector))
                        norm_a = math.sqrt(sum(a * a for a in c.embedding)) or 1.0
                        norm_b = math.sqrt(sum(b * b for b in query_vector)) or 1.0
                        score = round(max(0.0, dot / (norm_a * norm_b)), 4)
                    scored.append((score, c))

                scored.sort(key=lambda x: x[0], reverse=True)
                results = []
                for s, c in scored[:top_k]:
                    results.append(
                        VectorSearchResult(
                            vector_id=c.vector_id,
                            chunk_id=c.id,
                            version_id=c.version_id,
                            score=s,
                            metadata={
                                "chunk_id": str(c.id),
                                "version_id": str(c.version_id),
                                "allowed_roles": c.allowed_roles,
                                "page_start": c.page_start,
                                "page_end": c.page_end,
                            },
                        )
                    )
                return results

    def delete_version_vectors(
        self,
        tenant_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> None:
        """Clear embeddings for a specific document version."""
        with self._session_factory() as db:
            db.execute(
                update(DocumentChunk)
                .where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.version_id == version_id)
                .values(embedding=None)
            )
            db.commit()


pgvector_store = PgVectorStore()

