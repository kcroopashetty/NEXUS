"""Document ingestion pipeline orchestrator."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.core.errors import DocumentProcessingError
from app.models import (
    Document,
    DocumentVersion,
    ProcessingJob,
    DocumentPage,
    DocumentChunk,
    AuditEvent,
)
from app.services.storage.local import storage_service
from app.services.ingestion.extractor import DocumentExtractor
from app.services.ingestion.quality_inspector import DocumentQualityInspector
from app.services.ingestion.chunker import DocumentChunker
from app.services.embeddings.local import embedding_service
from app.services.vector_store.chroma import vector_store

logger = logging.getLogger("nexus.ingestion")


class IngestionPipeline:
    """End-to-end processing pipeline: Extraction -> Quality Inspection -> Chunking -> Vector Indexing."""

    def __init__(self):
        self.chunker = DocumentChunker()

    def process_version(
        self,
        version_id: uuid.UUID,
        db: Session,
        allowed_roles: str = "EMPLOYEE,CLIENT_ADMIN",
        classification: str = "INTERNAL",
    ) -> bool:
        """Process an uploaded document version. Idempotent and tenant-safe."""
        version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not version:
            logger.error("Version %s not found for ingestion.", version_id)
            return False

        job = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.version_id == version.id, ProcessingJob.tenant_id == version.tenant_id)
            .order_by(ProcessingJob.created_at.desc())
            .first()
        )
        if not job:
            job = ProcessingJob(
                tenant_id=version.tenant_id,
                version_id=version.id,
                status="RUNNING",
                stage="EXTRACTION",
            )
            db.add(job)
            db.flush()

        now = datetime.now(timezone.utc)
        job.status = "RUNNING"
        job.started_at = now
        version.status = "PROCESSING"
        db.commit()

        try:
            # 1. Fetch file bytes from secure storage
            file_bytes = storage_service.get_file_bytes(version.storage_key)

            # 2. Extract page-aware text
            job.stage = "EXTRACTION"
            db.commit()
            pages = DocumentExtractor.extract(file_bytes, version.original_filename)

            # Persist extracted pages to PostgreSQL (clear prior pages on retry)
            db.query(DocumentPage).filter(DocumentPage.version_id == version.id).delete()
            for p in pages:
                page_record = DocumentPage(
                    tenant_id=version.tenant_id,
                    version_id=version.id,
                    page_number=p.page_number,
                    extracted_text=p.text,
                    text_sha256=p.sha256,
                )
                db.add(page_record)
            db.flush()

            # 3. Document Quality Inspector
            job.stage = "QUALITY_CHECK"
            db.commit()
            inspection = DocumentQualityInspector.inspect(pages)
            version.quality_score = inspection.quality_score
            version.ocr_needed = inspection.ocr_needed
            version.quality_report = inspection.to_dict()
            job.quality_metrics = inspection.to_dict()
            db.flush()

            # 4. Chunking with Permission Metadata
            job.stage = "CHUNKING"
            db.commit()
            chunks = self.chunker.chunk_pages(
                pages=pages,
                version_id=version.id,
                allowed_roles=allowed_roles,
                classification=classification,
            )

            # Persist chunks to PostgreSQL (clear prior chunks on retry)
            db.query(DocumentChunk).filter(DocumentChunk.version_id == version.id).delete()
            db_chunks = []
            for c in chunks:
                chunk_record = DocumentChunk(
                    id=uuid.uuid4(),
                    tenant_id=version.tenant_id,
                    version_id=version.id,
                    chunk_index=c.chunk_index,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    section_heading=c.section_heading,
                    chunk_text=c.chunk_text,
                    text_sha256=c.text_sha256,
                    embedding_model=embedding_service.model_name,
                    vector_id=c.vector_id,
                    allowed_roles=c.allowed_roles,
                    classification=c.classification,
                )
                db.add(chunk_record)
                db_chunks.append(chunk_record)
            db.flush()

            # 5. Local Embedding Generation
            job.stage = "EMBEDDING"
            db.commit()
            chunk_texts = [c.chunk_text for c in db_chunks]
            vectors = embedding_service.embed_texts(chunk_texts)

            # Assign dense embeddings directly to DocumentChunk models (PostgreSQL pgvector)
            for c_obj, vec in zip(db_chunks, vectors):
                c_obj.embedding = vec
            db.flush()

            # 6. Index into isolated tenant Chroma collection (Dual-write for safe migration transition)
            job.stage = "INDEXING"
            db.commit()
            vector_ids = [c.vector_id for c in db_chunks]
            metadatas = [
                {
                    "chunk_id": str(c.id),
                    "tenant_id": str(version.tenant_id),
                    "document_id": str(version.document_id),
                    "version_id": str(version.id),
                    "version_number": version.version_number,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "allowed_roles": c.allowed_roles,
                    "classification": c.classification,
                    "content_sha256": c.text_sha256,
                }
                for c in db_chunks
            ]
            vector_store.index_chunks(
                tenant_id=version.tenant_id,
                vectors=vectors,
                vector_ids=vector_ids,
                metadatas=metadatas,
                documents=chunk_texts,
            )

            # 7. Finalize candidate version for review
            completion_time = datetime.now(timezone.utc)
            version.status = "REVIEW"
            version.processed_at = completion_time
            job.status = "SUCCEEDED"
            job.completed_at = completion_time

            audit = AuditEvent(
                tenant_id=version.tenant_id,
                action="INGESTION_SUCCEEDED",
                resource_type="DOCUMENT_VERSION",
                resource_id=version.id,
                outcome="SUCCESS",
                metadata_json={
                    "version_number": version.version_number,
                    "quality_score": float(version.quality_score or 1.0),
                    "chunk_count": len(db_chunks),
                },
            )
            db.add(audit)
            db.commit()
            logger.info("Version %s successfully indexed and placed in REVIEW.", version.id)
            return True

        except Exception as exc:
            db.rollback()
            logger.exception("Ingestion failed for version %s: %s", version_id, exc)
            fail_time = datetime.now(timezone.utc)

            # Mark version and job as FAILED
            version.status = "FAILED"
            version.error_code = "INGESTION_ERROR"
            version.error_message = str(exc)[:500]

            job.status = "FAILED"
            job.error_code = "INGESTION_ERROR"
            job.error_message = str(exc)[:500]
            job.completed_at = fail_time

            audit = AuditEvent(
                tenant_id=version.tenant_id,
                action="INGESTION_FAILED",
                resource_type="DOCUMENT_VERSION",
                resource_id=version.id,
                outcome="FAILED",
                metadata_json={"error": str(exc)[:200]},
            )
            db.add(audit)
            db.commit()
            return False


ingestion_pipeline = IngestionPipeline()

