"""Tests for extraction, Document Quality Inspector, chunking, and Chroma indexing."""

import io
import uuid
from sqlalchemy.orm import Session

from app.models import Tenant, User, TenantMembership, Document, DocumentVersion, DocumentPage, DocumentChunk
from app.services.ingestion.extractor import DocumentExtractor
from app.services.ingestion.quality_inspector import DocumentQualityInspector
from app.services.ingestion.chunker import DocumentChunker
from app.services.embeddings.local import embedding_service
from app.services.vector_store.chroma import vector_store
from app.services.storage.local import storage_service
from app.services.ingestion.pipeline import ingestion_pipeline


def test_extractor_txt_file():
    """Verify safe text extraction and heading detection."""
    sample_text = b"# Customer Service Policy\n\nAll customer issues must be logged within 2 hours.\nResolution SLA is 24 hours."
    pages = DocumentExtractor.extract(sample_text, "policy.txt")
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "Resolution SLA is 24 hours." in pages[0].text
    assert "Customer Service Policy" in pages[0].headings


def test_quality_inspector_high_quality():
    """Verify Quality Inspector scores clean text highly with no OCR needed."""
    sample_text = b"Section 1: General Provisions\n\nEmployees are entitled to 20 days paid leave.\n| Role | Days |\n| Staff | 20 |\n| Lead | 25 |"
    pages = DocumentExtractor.extract(sample_text, "doc.txt")
    report = DocumentQualityInspector.inspect(pages)

    assert report.quality_score >= 0.85
    assert report.ocr_needed is False
    assert report.detected_tables_count >= 1
    assert len(report.recommendations) > 0


def test_quality_inspector_scanned_low_density():
    """Verify Quality Inspector flags near-empty/scanned pages with ocr_needed = True."""
    pages = DocumentExtractor.extract(b"  \n  ", "scanned.txt")
    report = DocumentQualityInspector.inspect(pages)

    assert report.ocr_needed is True
    assert report.quality_score < 0.70
    assert any("OCR recommended" in r for r in report.recommendations)


def test_chunker_attaches_permission_metadata():
    """Verify chunker attaches allowed_roles, classification, and page provenance."""
    sample_text = b"Clause 1: Confidential salary scales.\nClause 2: Severance guidelines."
    pages = DocumentExtractor.extract(sample_text, "confidential.txt")
    chunker = DocumentChunker()

    version_id = uuid.uuid4()
    chunks = chunker.chunk_pages(
        pages=pages,
        version_id=version_id,
        allowed_roles="CLIENT_ADMIN",
        classification="CONFIDENTIAL",
    )

    assert len(chunks) >= 1
    c = chunks[0]
    assert c.allowed_roles == "CLIENT_ADMIN"
    assert c.classification == "CONFIDENTIAL"
    assert c.page_start == 1
    assert c.page_end == 1
    assert c.vector_id.startswith(f"chunk_{version_id}")


def test_vector_store_tenant_isolation():
    """Verify Chroma vector store stores and searches candidates per tenant."""
    tenant_1 = uuid.uuid4()
    tenant_2 = uuid.uuid4()

    vector_store.index_chunks(
        tenant_id=tenant_1,
        vectors=[[0.1] * 384],
        vector_ids=["vec_t1_1"],
        metadatas=[{"tenant_id": str(tenant_1), "version_id": str(uuid.uuid4()), "doc": "T1 Doc"}],
        documents=["Tenant 1 secret text"],
    )

    # Search in Tenant 1 returns match
    results_t1 = vector_store.search_candidates(tenant_id=tenant_1, query_vector=[0.1] * 384, top_k=5)
    assert len(results_t1) >= 1
    assert results_t1[0].vector_id == "vec_t1_1"

    # Search in Tenant 2 finds nothing (tenant isolated collection)
    results_t2 = vector_store.search_candidates(tenant_id=tenant_2, query_vector=[0.1] * 384, top_k=5)
    assert len(results_t2) == 0


def test_end_to_end_ingestion_pipeline(db_session: Session):
    """Verify IngestionPipeline extracts, scores, chunks, and puts version into REVIEW."""
    tenant = Tenant(slug="ingest-corp", name="Ingest Corp")
    user = User(email="user@ingest.corp", display_name="User", password_hash="hash")
    db_session.add_all([tenant, user])
    db_session.commit()

    doc = Document(tenant_id=tenant.id, title="Test SOP", created_by=user.id)
    db_session.add(doc)
    db_session.commit()

    content = b"# Standard Operating Procedure\n\n1. All requests processed within 24 hours.\n2. Escalations to manager."
    upload_id = str(uuid.uuid4())
    quarantine_key = storage_service.save_quarantine(io.BytesIO(content), upload_id)
    version_id = uuid.uuid4()
    storage_key = storage_service.promote_from_quarantine(
        quarantine_key=quarantine_key,
        tenant_id=str(tenant.id),
        document_id=str(doc.id),
        version_id=str(version_id),
    )

    version = DocumentVersion(
        id=version_id,
        tenant_id=tenant.id,
        document_id=doc.id,
        version_number=1,
        original_filename="sop.txt",
        storage_key=storage_key,
        sha256="fake_sha",
        mime_type="text/plain",
        file_size_bytes=len(content),
        status="UPLOADED",
        uploaded_by=user.id,
    )
    db_session.add(version)
    db_session.commit()

    # Run ingestion pipeline
    success = ingestion_pipeline.process_version(version.id, db_session)
    assert success is True

    db_session.refresh(version)
    assert version.status == "REVIEW"
    assert version.quality_score is not None
    assert version.quality_score >= 0.80

    # Verify pages and chunks in DB
    pages = db_session.query(DocumentPage).filter(DocumentPage.version_id == version.id).all()
    assert len(pages) == 1
    assert "within 24 hours" in pages[0].extracted_text

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.version_id == version.id).all()
    assert len(chunks) >= 1
    assert chunks[0].allowed_roles == "EMPLOYEE,CLIENT_ADMIN"
