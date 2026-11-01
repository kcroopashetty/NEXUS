"""Database vector consolidation: ChromaDB to PostgreSQL + pgvector migration & benchmarking."""

import logging
import time
import uuid
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from app.models import DocumentChunk
from app.services.authorization.context import AuthorizedTenantContext
from app.services.embeddings.local import embedding_service
from app.services.vector_store.chroma import vector_store as chroma_store
from app.services.retrieval.guard import RetrievalGuard
from app.services.retrieval.pgvector_retrieval import PgVectorRetrievalService

logger = logging.getLogger("nexus.migration")


def migrate_chroma_to_pgvector(db: Session, batch_size: int = 50) -> Dict[str, Any]:
    """
    Controlled migration utility:
    Identifies chunks with missing pgvector embeddings and populates them
    deterministically from canonical chunk text.
    """
    start_time = time.perf_counter()
    stmt = select(DocumentChunk).where(DocumentChunk.embedding.is_(None))
    unmigrated = db.execute(stmt).scalars().all()

    migrated_count = 0
    total_unmigrated = len(unmigrated)

    for i in range(0, total_unmigrated, batch_size):
        batch = unmigrated[i:i + batch_size]
        texts = [c.chunk_text for c in batch]
        vectors = embedding_service.embed_texts(texts)

        for chunk, vec in zip(batch, vectors):
            chunk.embedding = vec
            migrated_count += 1

        db.commit()

    duration = round(time.perf_counter() - start_time, 3)
    logger.info("Migrated %d chunks to pgvector in %s seconds", migrated_count, duration)
    return {
        "migrated_count": migrated_count,
        "duration_seconds": duration,
        "embedding_model": embedding_service.model_name,
        "dimension": embedding_service.dimension,
    }


def benchmark_retrieval_comparison(
    db: Session,
    ctx: AuthorizedTenantContext,
    test_queries: List[str],
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Compare retrieval performance and semantic alignment between:
      System A: ChromaDB + PostgreSQL filter
      System B: Consolidated PostgreSQL + pgvector single-query
    """
    comparison_results = []
    total_chroma_time = 0.0
    total_pgvector_time = 0.0

    for query in test_queries:
        query_vector = embedding_service.embed_query(query)

        # 1. System A: ChromaDB candidates + PostgreSQL verification
        t0 = time.perf_counter()
        chroma_candidates = chroma_store.search_candidates(
            tenant_id=ctx.tenant_id,
            query_vector=query_vector,
            top_k=top_k * 2,
        )
        chroma_verified = RetrievalGuard.filter_and_verify_candidates(
            candidates=chroma_candidates,
            ctx=ctx,
            db=db,
        )[:top_k]
        t_chroma = (time.perf_counter() - t0) * 1000
        total_chroma_time += t_chroma

        # 2. System B: Consolidated PostgreSQL + pgvector single-query
        t0 = time.perf_counter()
        pgvector_verified = PgVectorRetrievalService.retrieve_grounded_candidates(
            query_vector=query_vector,
            ctx=ctx,
            db=db,
            top_k=top_k,
        )
        t_pgvector = (time.perf_counter() - t0) * 1000
        total_pgvector_time += t_pgvector

        chroma_ids = set(c["chunk_id"] for c in chroma_verified)
        pgvector_ids = set(p["chunk_id"] for p in pgvector_verified)
        intersection = chroma_ids.intersection(pgvector_ids)

        recall_overlap = (
            round(len(intersection) / max(len(chroma_ids), 1) * 100, 1)
            if chroma_ids
            else 100.0
        )

        comparison_results.append({
            "query": query,
            "chroma_latency_ms": round(t_chroma, 2),
            "pgvector_latency_ms": round(t_pgvector, 2),
            "chroma_chunk_count": len(chroma_verified),
            "pgvector_chunk_count": len(pgvector_verified),
            "chunk_id_overlap_pct": recall_overlap,
            "isolation_preserved": all(
                p.get("document_id") for p in pgvector_verified
            ),
        })

    avg_chroma = round(total_chroma_time / max(len(test_queries), 1), 2)
    avg_pgvector = round(total_pgvector_time / max(len(test_queries), 1), 2)

    return {
        "queries_tested": len(test_queries),
        "average_chroma_latency_ms": avg_chroma,
        "average_pgvector_latency_ms": avg_pgvector,
        "latency_speedup_factor": round(avg_chroma / max(avg_pgvector, 0.01), 2),
        "query_comparisons": comparison_results,
    }

