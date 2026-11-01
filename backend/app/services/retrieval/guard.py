"""Permission Change Guard & Knowledge Integrity Engine for secure candidate verification."""

import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models import DocumentChunk, DocumentVersion, Document
from app.services.vector_store.base import VectorSearchResult
from app.services.authorization.context import AuthorizedTenantContext

AUTHORITY_RANKS = {
    "OFFICIAL_POLICY": 4,
    "STANDARD_PROCEDURE": 3,
    "GUIDELINE": 2,
    "INFORMAL_NOTE": 1,
}


class RetrievalGuard:
    """
    Enforces real-time PostgreSQL authorization and policy authority on vector search candidates.
    
    Non-negotiable guarantees:
    1. Chunks MUST belong to the authorized tenant.
    2. Chunks MUST belong to an ACTIVE document version (superseded/candidate versions blocked).
    3. Caller's role MUST satisfy chunk allowed_roles.
    4. Ranks active sources by policy authority hierarchy.
    """

    @classmethod
    def filter_and_verify_candidates(
        cls,
        candidates: List[VectorSearchResult],
        ctx: AuthorizedTenantContext,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """Filter Chroma candidates against PostgreSQL authoritative state."""
        if not candidates:
            return []

        # Extract candidate chunk UUIDs
        chunk_ids = [c.chunk_id for c in candidates if c.chunk_id is not None]
        if not chunk_ids:
            return []

        # Join chunks to versions and documents with strict tenant isolation and ACTIVE status
        rows = (
            db.query(DocumentChunk, DocumentVersion, Document)
            .join(DocumentVersion, DocumentChunk.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .filter(
                DocumentChunk.id.in_(chunk_ids),
                DocumentChunk.tenant_id == ctx.tenant_id,
                DocumentVersion.tenant_id == ctx.tenant_id,
                DocumentVersion.status == "ACTIVE",
                Document.tenant_id == ctx.tenant_id,
            )
            .all()
        )

        # Map candidate scores by chunk_id
        score_map = {c.chunk_id: c.score for c in candidates}

        verified_passages: List[Dict[str, Any]] = []

        for chunk, version, doc in rows:
            # 1. Permission-Carrying Knowledge check
            allowed_roles = [r.strip().upper() for r in chunk.allowed_roles.split(",") if r.strip()]
            caller_role = ctx.membership_role.upper()
            if caller_role not in allowed_roles and not ctx.is_platform_admin():
                # Permission Change Guard: Caller does not have sufficient role clearance for this chunk
                continue

            # 2. Knowledge Integrity authority score
            auth_rank = AUTHORITY_RANKS.get(doc.authority_level, 1)
            raw_score = score_map.get(chunk.id, 0.5)

            verified_passages.append({
                "chunk_id": str(chunk.id),
                "document_id": str(doc.id),
                "document_title": doc.title,
                "authority_level": doc.authority_level,
                "authority_rank": auth_rank,
                "effective_date": str(doc.effective_date) if doc.effective_date else None,
                "version_id": str(version.id),
                "version_number": version.version_number,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_heading": chunk.section_heading,
                "chunk_text": chunk.chunk_text,
                "content_sha256": chunk.text_sha256,
                "retrieval_score": raw_score,
                # Composite sort key: authority rank primary, similarity score secondary
                "composite_weight": (auth_rank * 10.0) + raw_score,
            })

        # Sort descending by composite weight (highest authority and highest relevance first)
        verified_passages.sort(key=lambda x: x["composite_weight"], reverse=True)
        return verified_passages

