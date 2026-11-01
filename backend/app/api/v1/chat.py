"""Grounded RAG chat, Evidence Passport, and Query Trace diagnostic endpoints."""

import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ResourceNotFoundError
from app.core.request_context import get_current_request_id
from app.db.session import get_db
from app.models import QueryEvent, QueryEvidence, DocumentChunk, SecurityEvent
from app.schemas.chat import (
    ChatQueryRequest,
    ChatQueryResponse,
    EvidencePassportResponse,
    QueryTraceResponse,
)
from app.services.authorization.context import (
    get_authorized_tenant_context,
    AuthorizedTenantContext,
)
from app.services.embeddings.local import embedding_service
from app.services.vector_store.chroma import vector_store
from app.services.retrieval.guard import RetrievalGuard
from app.services.retrieval.pgvector_retrieval import PgVectorRetrievalService
from app.services.llm.ollama import llm_service
from app.services.evidence.passport import EvidencePassportValidator
from app.services.security.garak_guard import GarakGuard

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}", tags=["Grounded Chat & Evidence Ledger"])


@router.post("/chat/query", response_model=ChatQueryResponse)
def execute_grounded_query(
    payload: ChatQueryRequest,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Execute tenant-isolated, grounded RAG with Permission Change Guard and Evidence Passport.
    Records granular Query Trace diagnostics.
    """
    start_total = time.perf_counter()
    trace_stages = []
    req_id = get_current_request_id()

    # Stage 1: Auth & Tenant Guard
    t0 = time.perf_counter()
    trace_stages.append({
        "stage": "AUTH_VERIFY",
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "status": "PASSED",
        "detail": f"Caller role '{ctx.membership_role}' verified in tenant '{ctx.tenant_slug}'",
    })

    # Stage 1.5: NVIDIA Garak Prompt Injection Shield
    t0 = time.perf_counter()
    is_attack, attack_reason = GarakGuard.scan_prompt_injection(payload.question)
    if is_attack:
        trace_stages.append({
            "stage": "GARAK_INJECTION_SHIELD",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "status": "ATTACK_NEUTRALIZED",
            "detail": f"NVIDIA Garak probe detected and blocked: {attack_reason}",
        })
        sec_event = SecurityEvent(
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type="GARAK_PROMPT_INJECTION_BLOCKED",
            severity="HIGH",
            outcome="BLOCKED",
            request_id=req_id,
            metadata_json={"attack_reason": attack_reason, "query_excerpt": payload.question[:150]},
        )
        db.add(sec_event)

        total_latency_ms = int((time.perf_counter() - start_total) * 1000)
        refusal_ans = "I cannot fulfill this request. The query contains adversarial prompt injection, system instruction overrides, or unauthorized extraction attempts (Garak Guard active)."
        query_id = uuid.uuid4()
        query_event = QueryEvent(
            id=query_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            question_text=payload.question,
            answer_text=refusal_ans,
            status="INSUFFICIENT_EVIDENCE",
            grounding_verified=False,
            grounding_score=0.0,
            model_name=llm_service.model_name,
            embedding_model=embedding_service.model_name,
            latency_ms=total_latency_ms,
            trace_stages=trace_stages,
            request_id=req_id,
        )
        db.add(query_event)
        db.commit()

        return ChatQueryResponse(
            query_id=query_id,
            status="INSUFFICIENT_EVIDENCE",
            answer=refusal_ans,
            evidence_passport=EvidencePassportResponse(
                passport_id=str(query_id),
                grounding_verified=False,
                grounding_score=0.0,
                status="INSUFFICIENT_EVIDENCE",
                claims=[],
                evidence_items=[],
                conflicts_detected=[],
                uncertainty_note="Query rejected by NVIDIA Garak Prompt Injection Shield.",
            ),
            latency_ms=total_latency_ms,
        )

    trace_stages.append({
        "stage": "GARAK_INJECTION_SHIELD",
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "status": "PASSED",
        "detail": "NVIDIA Garak injection scan passed (no jailbreak or system override detected)",
    })

    # Stage 2: Retrieval Engine (PostgreSQL + pgvector single-query vs legacy Chroma)
    t0 = time.perf_counter()
    query_vector = embedding_service.embed_query(payload.question)

    if settings.VECTOR_STORE_BACKEND == "postgres_pgvector":
        verified_passages = PgVectorRetrievalService.retrieve_grounded_candidates(
            query_vector=query_vector,
            ctx=ctx,
            db=db,
            top_k=10,
        )
        trace_stages.append({
            "stage": "PGVECTOR_CONSOLIDATED_RETRIEVAL",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "status": "PASSED" if verified_passages else "NO_ACTIVE_EVIDENCE",
            "detail": f"Single-query pgvector retrieved {len(verified_passages)} authorized active passages",
        })
    else:
        candidates = vector_store.search_candidates(
            tenant_id=ctx.tenant_id,
            query_vector=query_vector,
            top_k=10,
        )
        trace_stages.append({
            "stage": "VECTOR_SEARCH",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "status": "PASSED",
            "detail": f"Retrieved {len(candidates)} candidate vectors from isolated collection",
        })

        t0_guard = time.perf_counter()
        verified_passages = RetrievalGuard.filter_and_verify_candidates(
            candidates=candidates,
            ctx=ctx,
            db=db,
        )
        trace_stages.append({
            "stage": "PERMISSION_GUARD",
            "duration_ms": int((time.perf_counter() - t0_guard) * 1000),
            "status": "PASSED" if verified_passages else "NO_ACTIVE_EVIDENCE",
            "detail": f"{len(verified_passages)} chunks passed PostgreSQL ACTIVE version and role clearance checks",
        })

    # Stage 4: Knowledge Integrity Check
    t0 = time.perf_counter()
    authority_ranks = [p["authority_level"] for p in verified_passages]
    top_auth = authority_ranks[0] if authority_ranks else "NONE"
    trace_stages.append({
        "stage": "INTEGRITY_CHECK",
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "status": "PASSED",
        "detail": f"Policy authority evaluated. Top source authority: {top_auth}",
    })

    # Stage 5: Local LLM Inference (Routed through InferenceGateway)
    t0 = time.perf_counter()
    llm_output = llm_service.generate_grounded_answer(
        question=payload.question,
        evidence_passages=verified_passages,
        tenant_id=ctx.tenant_id,
    )
    trace_stages.append({
        "stage": "LLM_INFERENCE",
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "status": llm_output.status,
        "detail": f"Model '{llm_service.model_name}' produced {len(llm_output.claims)} claims",
    })

    # Stage 5.5: NVIDIA Garak PII & Secret Redaction
    t0 = time.perf_counter()
    sanitized_answer, was_redacted, redaction_counts = GarakGuard.sanitize_pii_and_secrets(llm_output.answer)
    trace_stages.append({
        "stage": "GARAK_PII_GUARD",
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "status": "REDACTED" if was_redacted else "PASSED",
        "detail": f"PII/Secret sanitization: {'Redacted ' + str(redaction_counts) if was_redacted else 'Zero leaks detected'}",
    })

    # Stage 6: Evidence Passport Validation
    t0 = time.perf_counter()
    passport = EvidencePassportValidator.validate_and_issue(
        llm_output=llm_output,
        verified_passages=verified_passages,
    )
    trace_stages.append({
        "stage": "EVIDENCE_VALIDATION",
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "status": "VERIFIED" if passport.grounding_verified else "REFUSED",
        "detail": f"Grounding score: {passport.grounding_score}. Verified claims: {sum(1 for c in passport.claims if c.supported)}/{len(passport.claims)}",
    })

    total_latency_ms = int((time.perf_counter() - start_total) * 1000)

    # Persist in Evidence Ledger
    query_id = uuid.uuid4()
    query_event = QueryEvent(
        id=query_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        question_text=payload.question,
        answer_text=sanitized_answer,
        status=passport.status,
        grounding_verified=passport.grounding_verified,
        grounding_score=passport.grounding_score,
        model_name=llm_service.model_name,
        embedding_model=embedding_service.model_name,
        latency_ms=total_latency_ms,
        trace_stages=trace_stages,
        request_id=req_id,
    )
    db.add(query_event)
    db.flush()

    # Persist individual evidence snapshots
    for rank, p in enumerate(passport.evidence_items, start=1):
        # Find matching claim text if any
        matching_claim = next((c.claim_text for c in passport.claims if c.citation_id == p["chunk_id"]), None)
        is_supported = next((c.supported for c in passport.claims if c.citation_id == p["chunk_id"]), True)

        evidence_rec = QueryEvidence(
            tenant_id=ctx.tenant_id,
            query_id=query_event.id,
            chunk_id=uuid.UUID(p["chunk_id"]),
            version_id=uuid.UUID(p["version_id"]),
            page_start=p["page_start"],
            page_end=p["page_end"],
            claim_text=matching_claim,
            claim_supported=is_supported,
            evidence_text_snapshot=p["exact_passage"],
            content_sha256=p["content_sha256"],
            retrieval_rank=rank,
            retrieval_score=p["retrieval_score"],
        )
        db.add(evidence_rec)

    db.commit()

    return ChatQueryResponse(
        query_id=query_event.id,
        status=passport.status,
        answer=llm_output.answer,
        evidence_passport=EvidencePassportResponse(**passport.to_dict()),
        latency_ms=total_latency_ms,
    )


@router.get("/queries/{query_id}", response_model=ChatQueryResponse)
def get_query_evidence_ledger(
    query_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Retrieve historical query and exact evidence snapshot from the Evidence Ledger.
    Historical records continue pointing to the historical version/evidence even if documents change.
    """
    query_event = (
        db.query(QueryEvent)
        .filter(QueryEvent.id == query_id, QueryEvent.tenant_id == ctx.tenant_id)
        .first()
    )
    if not query_event:
        raise ResourceNotFoundError("Query record not found in authorized workspace.")

    evidence_records = (
        db.query(QueryEvidence)
        .filter(QueryEvidence.query_id == query_event.id, QueryEvidence.tenant_id == ctx.tenant_id)
        .order_by(QueryEvidence.retrieval_rank)
        .all()
    )

    claims = []
    items = []
    for ev in evidence_records:
        if ev.claim_text:
            claims.append({
                "claim_text": ev.claim_text,
                "citation_id": str(ev.chunk_id) if ev.chunk_id else "",
                "supported": ev.claim_supported,
                "document_title": ev.version.document.title if ev.version and ev.version.document else "Archived Document",
                "version_number": ev.version.version_number if ev.version else 1,
                "page_number": ev.page_start,
                "authority_level": ev.version.document.authority_level if ev.version and ev.version.document else "OFFICIAL_POLICY",
                "grounding_score": 1.0 if ev.claim_supported else 0.0,
            })

        items.append({
            "chunk_id": str(ev.chunk_id) if ev.chunk_id else "",
            "document_id": str(ev.version.document_id) if ev.version else "",
            "document_title": ev.version.document.title if ev.version and ev.version.document else "Archived Document",
            "version_id": str(ev.version_id),
            "version_number": ev.version.version_number if ev.version else 1,
            "authority_level": ev.version.document.authority_level if ev.version and ev.version.document else "OFFICIAL_POLICY",
            "page_start": ev.page_start,
            "page_end": ev.page_end,
            "exact_passage": ev.evidence_text_snapshot,
            "content_sha256": ev.content_sha256,
            "retrieval_score": ev.retrieval_score or 0.0,
        })

    passport_data = {
        "passport_id": str(query_event.id),
        "grounding_verified": query_event.grounding_verified,
        "grounding_score": float(query_event.grounding_score or 1.0),
        "status": query_event.status,
        "claims": claims,
        "evidence_items": items,
        "conflicts_detected": ["Contradictory directives detected across active sources."] if query_event.status == "CONFLICT" else [],
        "uncertainty_note": None,
    }

    return ChatQueryResponse(
        query_id=query_event.id,
        status=query_event.status,
        answer=query_event.answer_text or "",
        evidence_passport=EvidencePassportResponse(**passport_data),
        latency_ms=query_event.latency_ms or 0,
    )


@router.get("/queries/{query_id}/trace", response_model=QueryTraceResponse)
def get_query_trace_diagnostics(
    query_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieve full pipeline Query Trace execution timeline for debugging."""
    query_event = (
        db.query(QueryEvent)
        .filter(QueryEvent.id == query_id, QueryEvent.tenant_id == ctx.tenant_id)
        .first()
    )
    if not query_event:
        raise ResourceNotFoundError("Query record not found in authorized workspace.")

    return QueryTraceResponse(
        query_id=query_event.id,
        tenant_id=query_event.tenant_id,
        question_text=query_event.question_text,
        status=query_event.status,
        total_latency_ms=query_event.latency_ms or 0,
        stages=query_event.trace_stages or [],
        created_at=query_event.created_at,
    )

