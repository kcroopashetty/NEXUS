"""Unit tests for Stage C: PostgreSQL + pgvector single-query consolidated retrieval."""

import io
import uuid
import pytest
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Tenant, User, TenantMembership, Document, DocumentVersion, DocumentChunk
from app.services.authorization.context import AuthorizedTenantContext
from app.services.embeddings.local import embedding_service
from app.services.retrieval.pgvector_retrieval import PgVectorRetrievalService
from app.services.retrieval.migration import benchmark_retrieval_comparison, migrate_chroma_to_pgvector


@pytest.fixture
def pgvector_test_env(client: TestClient, db_session: Session):
    """Provisions isolated tenant with indexed document chunks carrying pgvector embeddings."""
    pw_hash = hash_password("PgVectorPass123!")
    tag = uuid.uuid4().hex[:6]

    tenant_a = Tenant(slug=f"pgv-a-{tag}", name=f"PgVector Alpha {tag}")
    tenant_b = Tenant(slug=f"pgv-b-{tag}", name=f"PgVector Beta {tag}")
    user_admin = User(email=f"admin@{tag}-pgv.corp", display_name="PGV Admin", password_hash=pw_hash)
    user_emp = User(email=f"emp@{tag}-pgv.corp", display_name="PGV Emp", password_hash=pw_hash)

    db_session.add_all([tenant_a, tenant_b, user_admin, user_emp])
    db_session.commit()

    mem_admin = TenantMembership(tenant_id=tenant_a.id, user_id=user_admin.id, role="CLIENT_ADMIN")
    mem_emp = TenantMembership(tenant_id=tenant_a.id, user_id=user_emp.id, role="EMPLOYEE")
    db_session.add_all([mem_admin, mem_emp])
    db_session.commit()

    tok_admin = client.post("/api/v1/auth/login", json={"email": user_admin.email, "password": "PgVectorPass123!"}).json()["access_token"]

    # Upload document with standard policy content
    doc_text = (
        b"CLAUSE 4.1 EMERGENCY TRAVEL EXPENSES:\n"
        b"Employees traveling on international assignments are entitled to $120 USD daily meal stipend.\n"
        b"All claims must be submitted within 14 calendar days of travel completion."
    )
    files = {"file": ("travel_policy.txt", io.BytesIO(doc_text), "text/plain")}
    resp = client.post(
        f"/api/v1/tenants/{tenant_a.id}/documents",
        headers={"Authorization": f"Bearer {tok_admin}"},
        data={"title": "Corporate Travel Policy", "authority_level": "OFFICIAL_POLICY"},
        files=files,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]
    ver_id = resp.json()["version_id"]

    # Activate version 1
    v1 = db_session.query(DocumentVersion).filter(DocumentVersion.id == uuid.UUID(ver_id)).first()
    v1.status = "ACTIVE"
    db_session.commit()

    # Upload candidate v2 (REVIEW status) with modified stipend
    v2_text = b"CLAUSE 4.1 CANDIDATE: Emergency travel stipend increased to $200 USD."
    files_v2 = {"file": ("travel_v2.txt", io.BytesIO(v2_text), "text/plain")}
    resp_v2 = client.post(
        f"/api/v1/tenants/{tenant_a.id}/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {tok_admin}"},
        files=files_v2,
    )
    ver_v2_id = resp_v2.json()["version_id"]

    ctx_emp = AuthorizedTenantContext(
        tenant_id=tenant_a.id,
        tenant_slug=tenant_a.slug,
        tenant_name=tenant_a.name,
        user_id=user_emp.id,
        user_email=user_emp.email,
        user_display_name=user_emp.display_name,
        membership_role="EMPLOYEE",
        platform_role="USER",
        last_permission_change_at=mem_emp.last_permission_change_at,
    )

    ctx_admin = AuthorizedTenantContext(
        tenant_id=tenant_a.id,
        tenant_slug=tenant_a.slug,
        tenant_name=tenant_a.name,
        user_id=user_admin.id,
        user_email=user_admin.email,
        user_display_name=user_admin.display_name,
        membership_role="CLIENT_ADMIN",
        platform_role="USER",
        last_permission_change_at=mem_admin.last_permission_change_at,
    )

    ctx_beta = AuthorizedTenantContext(
        tenant_id=tenant_b.id,
        tenant_slug=tenant_b.slug,
        tenant_name=tenant_b.name,
        user_id=user_emp.id,
        user_email=user_emp.email,
        user_display_name=user_emp.display_name,
        membership_role="EMPLOYEE",
        platform_role="USER",
        last_permission_change_at=mem_emp.last_permission_change_at,
    )

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "doc_id": doc_id,
        "ver_id": ver_id,
        "ver_v2_id": ver_v2_id,
        "ctx_emp": ctx_emp,
        "ctx_admin": ctx_admin,
        "ctx_beta": ctx_beta,
    }


def test_pgvector_single_query_grounded_retrieval(db_session: Session, pgvector_test_env: dict):
    """Single-query pgvector retrieval retrieves active evidence with correct metadata and ranking."""
    env = pgvector_test_env
    query = "What is the emergency travel meal stipend amount?"
    query_vector = embedding_service.embed_query(query)

    passages = PgVectorRetrievalService.retrieve_grounded_candidates(
        query_vector=query_vector,
        ctx=env["ctx_emp"],
        db=db_session,
        top_k=5,
    )

    assert len(passages) >= 1
    top_p = passages[0]
    assert "$120 USD" in top_p["chunk_text"]
    assert top_p["version_id"] == env["ver_id"]
    assert top_p["authority_level"] == "OFFICIAL_POLICY"
    assert top_p["authority_rank"] == 4
    assert top_p["retrieval_score"] > 0.0


def test_pgvector_excludes_candidate_review_version(db_session: Session, pgvector_test_env: dict):
    """Candidate version (REVIEW status) must be excluded from pgvector retrieval."""
    env = pgvector_test_env
    query = "What is the candidate emergency travel stipend?"
    query_vector = embedding_service.embed_query(query)

    passages = PgVectorRetrievalService.retrieve_grounded_candidates(
        query_vector=query_vector,
        ctx=env["ctx_emp"],
        db=db_session,
        top_k=5,
    )

    # v2 stipend ($200) must NEVER be returned
    assert not any("$200 USD" in p["chunk_text"] for p in passages)
    assert not any(p["version_id"] == env["ver_v2_id"] for p in passages)


def test_pgvector_role_clearance_filtering(db_session: Session, pgvector_test_env: dict):
    """Chunks with restricted allowed_roles are excluded for unauthorized callers."""
    env = pgvector_test_env
    # Restrict chunk to CLIENT_ADMIN only
    chunk = db_session.query(DocumentChunk).filter(DocumentChunk.version_id == uuid.UUID(env["ver_id"])).first()
    chunk.allowed_roles = "CLIENT_ADMIN"
    db_session.commit()

    query_vector = embedding_service.embed_query("travel expense claims")

    # Regular employee query -> 0 chunks returned
    passages_emp = PgVectorRetrievalService.retrieve_grounded_candidates(
        query_vector=query_vector,
        ctx=env["ctx_emp"],
        db=db_session,
    )
    assert len(passages_emp) == 0

    # Client admin query -> chunk is returned
    passages_admin = PgVectorRetrievalService.retrieve_grounded_candidates(
        query_vector=query_vector,
        ctx=env["ctx_admin"],
        db=db_session,
    )
    assert len(passages_admin) >= 1
    assert "$120 USD" in passages_admin[0]["chunk_text"]


def test_pgvector_cross_tenant_isolation(db_session: Session, pgvector_test_env: dict):
    """Tenant Beta executing pgvector search retrieves zero chunks from Tenant Alpha."""
    env = pgvector_test_env
    query_vector = embedding_service.embed_query("travel meal stipend claims")

    passages_beta = PgVectorRetrievalService.retrieve_grounded_candidates(
        query_vector=query_vector,
        ctx=env["ctx_beta"],
        db=db_session,
    )
    assert len(passages_beta) == 0


def test_pgvector_migration_and_benchmark(db_session: Session, pgvector_test_env: dict):
    """Verify migration of unindexed chunks and benchmark equivalence between Chroma and pgvector."""
    env = pgvector_test_env
    # 1. Test migration utility
    mig_result = migrate_chroma_to_pgvector(db=db_session)
    assert "migrated_count" in mig_result
    assert mig_result["dimension"] == 384

    # 2. Benchmark retrieval comparison
    bench = benchmark_retrieval_comparison(
        db=db_session,
        ctx=env["ctx_admin"],
        test_queries=["What is the emergency travel meal stipend?", "How many days to submit travel claims?"],
    )
    assert bench["queries_tested"] == 2
    assert "average_pgvector_latency_ms" in bench
    assert "average_chroma_latency_ms" in bench
    for comp in bench["query_comparisons"]:
        assert comp["isolation_preserved"] is True
        assert comp["pgvector_chunk_count"] >= 1

