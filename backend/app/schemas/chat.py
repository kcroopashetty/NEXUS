"""Pydantic schemas for chat queries, Evidence Passport, and Query Trace."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChatQueryRequest(BaseModel):
    """User inquiry payload for grounded knowledge assistant."""

    question: str = Field(..., min_length=2, max_length=1500, description="User question")


class VerifiedClaimResponse(BaseModel):
    """Claim-to-source grounding proof."""

    claim_text: str
    citation_id: str
    supported: bool
    document_title: str
    version_number: int
    page_number: int
    authority_level: str
    grounding_score: float


class EvidenceItemResponse(BaseModel):
    """Historical passage snapshot with page-level provenance."""

    chunk_id: str
    document_id: str
    document_title: str
    version_id: str
    version_number: int
    authority_level: str
    page_start: int
    page_end: int
    exact_passage: str
    content_sha256: str
    retrieval_score: float


class EvidencePassportResponse(BaseModel):
    """Evidence Passport certifying factual grounding."""

    passport_id: str
    grounding_verified: bool
    grounding_score: float
    status: str
    claims: List[VerifiedClaimResponse] = Field(default_factory=list)
    evidence_items: List[EvidenceItemResponse] = Field(default_factory=list)
    conflicts_detected: List[str] = Field(default_factory=list)
    uncertainty_note: Optional[str] = None


class ChatQueryResponse(BaseModel):
    """Response returned to user with grounded answer and Evidence Passport."""

    query_id: uuid.UUID
    status: str
    answer: str
    evidence_passport: EvidencePassportResponse
    latency_ms: int


class QueryTraceResponse(BaseModel):
    """Diagnostic pipeline timeline for debugging and observability."""

    query_id: uuid.UUID
    tenant_id: uuid.UUID
    question_text: str
    status: str
    total_latency_ms: int
    stages: List[Dict[str, Any]]
    created_at: datetime

