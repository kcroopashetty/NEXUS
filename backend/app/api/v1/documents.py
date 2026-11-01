"""Document management and version upload endpoints."""

import hashlib
import os
import uuid
from datetime import datetime, date, timezone
from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.errors import (
    DocumentProcessingError,
    ResourceNotFoundError,
    ValidationPayloadError,
)
from app.db.session import get_db
from app.models import (
    Document,
    DocumentVersion,
    ProcessingJob,
    AuditEvent,
    DocumentImpactSuggestion,
    DocumentChange,
    DocumentChangeItem,
    QueryEvidence,
)
from app.schemas.document import (
    DocumentResponse,
    DocumentVersionResponse,
    DocumentUploadResponse,
)
from app.services.authorization.context import (
    get_authorized_tenant_context,
    require_client_admin_context,
    AuthorizedTenantContext,
)
from app.services.storage.local import storage_service
from app.services.ingestion.pipeline import ingestion_pipeline
from app.services.change_intelligence.diff import compute_version_diff

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/documents", tags=["Documents & Versions"])


def _validate_file_upload(file: UploadFile) -> str:
    """
    Strict file upload validation:
    1. Blocks path traversal sequences (.., /, \\, \\0).
    2. Enforces allowed extension whitelist.
    3. Validates file header / magic byte signatures.
    """
    if not file.filename:
        raise DocumentProcessingError(message="Uploaded file must have a filename.", code="INVALID_FILENAME")

    # 1. Path traversal defense
    filename_raw = file.filename
    if ".." in filename_raw or "/" in filename_raw or "\\" in filename_raw or "\0" in filename_raw:
        raise DocumentProcessingError(
            message="Invalid filename: Path traversal sequences are strictly prohibited.",
            code="PATH_TRAVERSAL_DETECTED",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Extension whitelist
    ext = filename_raw.rsplit(".", 1)[-1].lower() if "." in filename_raw else ""
    if ext not in settings.allowed_extensions_list:
        raise DocumentProcessingError(
            message=f"File extension '.{ext}' is not permitted. Allowed: {settings.ALLOWED_EXTENSIONS}",
            code="UNSUPPORTED_FILE_TYPE",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    # 3. Magic Bytes / File Signature Inspection
    try:
        header = file.file.read(16)
        file.file.seek(0)
    except Exception as exc:
        raise DocumentProcessingError(
            message=f"Failed to inspect uploaded file stream: {exc}",
            code="UNREADABLE_FILE",
        )

    if ext == "pdf":
        if not header.startswith(b"%PDF-"):
            raise DocumentProcessingError(
                message="File signature mismatch: File declared as PDF lacks valid %PDF- magic header.",
                code="FILE_SIGNATURE_MISMATCH",
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
    elif ext == "docx":
        if not header.startswith(b"PK\x03\x04"):
            raise DocumentProcessingError(
                message="File signature mismatch: File declared as DOCX lacks valid PK archive header.",
                code="FILE_SIGNATURE_MISMATCH",
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
    elif ext == "txt":
        # Disallow disguised binary executables (MZ, ELF, Mach-O, Java class)
        disallowed_signatures = [b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe"]
        for sig in disallowed_signatures:
            if header.startswith(sig):
                raise DocumentProcessingError(
                    message="Executable binary file disguised as text document is strictly blocked.",
                    code="MALICIOUS_PAYLOAD_DETECTED",
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                )

    return ext


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_new_document(
    title: str = Form(..., min_length=2, max_length=300),
    category: Optional[str] = Form(None, max_length=100),
    description: Optional[str] = Form(None),
    external_ref: Optional[str] = Form(None, max_length=200),
    authority_level: str = Form("OFFICIAL_POLICY"),
    effective_date: Optional[date] = Form(None),
    allowed_roles: str = Form("EMPLOYEE,CLIENT_ADMIN"),
    classification: str = Form("INTERNAL"),
    file: UploadFile = File(...),
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client Admin endpoint to upload a new logical document along with its version 1 file.
    Streams to quarantine, validates hash/size, promotes to tenant storage, and enqueues job.
    """
    ext = _validate_file_upload(file)

    # 1. Stream into quarantine area
    upload_id = str(uuid.uuid4())
    quarantine_key = storage_service.save_quarantine(file.file, upload_id)

    # 2. Compute SHA-256 and verify file size
    sha256_hash = hashlib.sha256()
    file_size_bytes = 0

    with storage_service.get_file_stream(quarantine_key) as f:
        for chunk in iter(lambda: f.read(65536), b""):
            file_size_bytes += len(chunk)
            sha256_hash.update(chunk)

    if file_size_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
        storage_service.delete_file(quarantine_key)
        raise DocumentProcessingError(
            message=f"File size {file_size_bytes} exceeds limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes.",
            code="FILE_TOO_LARGE",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    calculated_sha256 = sha256_hash.hexdigest()

    # 3. Create Document container
    document = Document(
        tenant_id=ctx.tenant_id,
        title=title.strip(),
        category=category.strip() if category else None,
        description=description.strip() if description else None,
        external_ref=external_ref.strip() if external_ref else None,
        authority_level=authority_level,
        effective_date=effective_date,
        created_by=ctx.user_id,
    )
    db.add(document)
    db.flush()

    # 4. Generate Version 1
    version_id = uuid.uuid4()
    storage_key = storage_service.promote_from_quarantine(
        quarantine_key=quarantine_key,
        tenant_id=str(ctx.tenant_id),
        document_id=str(document.id),
        version_id=str(version_id),
    )

    mime_type = file.content_type or f"application/{ext}"
    version = DocumentVersion(
        id=version_id,
        tenant_id=ctx.tenant_id,
        document_id=document.id,
        version_number=1,
        original_filename=os.path.basename(file.filename),
        storage_key=storage_key,
        sha256=calculated_sha256,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        status="UPLOADED",
        uploaded_by=ctx.user_id,
    )
    db.add(version)
    db.flush()

    # 5. Create background ProcessingJob
    job = ProcessingJob(
        tenant_id=ctx.tenant_id,
        version_id=version.id,
        status="QUEUED",
        stage="EXTRACTION",
    )
    db.add(job)

    # 6. Audit log
    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="DOCUMENT_UPLOAD_V1",
        resource_type="DOCUMENT",
        resource_id=document.id,
        outcome="SUCCESS",
        metadata_json={
            "filename": version.original_filename,
            "version_number": 1,
            "sha256": calculated_sha256,
        },
    )
    db.add(audit)
    db.commit()

    # 7. Execute ingestion pipeline (Extraction -> Quality Inspection -> Chunking -> Vector Indexing)
    ingestion_pipeline.process_version(
        version.id,
        db,
        allowed_roles=allowed_roles,
        classification=classification,
    )
    db.refresh(version)

    return DocumentUploadResponse(
        document_id=document.id,
        version_id=version.id,
        version_number=1,
        status=version.status,
        job_id=job.id,
        message=f"Document processed successfully. Status: {version.status}.",
    )


@router.post("/{document_id}/versions", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_candidate_version(
    document_id: uuid.UUID,
    allowed_roles: str = Form("EMPLOYEE,CLIENT_ADMIN"),
    classification: str = Form("INTERNAL"),
    file: UploadFile = File(...),
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Client Admin endpoint to upload a candidate version (v2, v3, etc.) for the same logical document.
    Enforces same-tenant ownership and auto-increments version number.
    """
    ext = _validate_file_upload(file)

    # 1. Verify document exists in this tenant
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == ctx.tenant_id)
        .first()
    )
    if not document:
        raise ResourceNotFoundError("Logical document not found in authorized workspace.")

    # 2. Get next version number
    max_ver = (
        db.query(func.max(DocumentVersion.version_number))
        .filter(DocumentVersion.document_id == document.id, DocumentVersion.tenant_id == ctx.tenant_id)
        .scalar()
        or 0
    )
    next_ver = max_ver + 1

    # 3. Stream into quarantine
    upload_id = str(uuid.uuid4())
    quarantine_key = storage_service.save_quarantine(file.file, upload_id)

    # 4. Compute SHA-256 and size
    sha256_hash = hashlib.sha256()
    file_size_bytes = 0
    with storage_service.get_file_stream(quarantine_key) as f:
        for chunk in iter(lambda: f.read(65536), b""):
            file_size_bytes += len(chunk)
            sha256_hash.update(chunk)

    if file_size_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
        storage_service.delete_file(quarantine_key)
        raise DocumentProcessingError(
            message=f"File size exceeds limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes.",
            code="FILE_TOO_LARGE",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    calculated_sha256 = sha256_hash.hexdigest()

    # 5. Promote to permanent storage
    version_id = uuid.uuid4()
    storage_key = storage_service.promote_from_quarantine(
        quarantine_key=quarantine_key,
        tenant_id=str(ctx.tenant_id),
        document_id=str(document.id),
        version_id=str(version_id),
    )

    mime_type = file.content_type or f"application/{ext}"
    version = DocumentVersion(
        id=version_id,
        tenant_id=ctx.tenant_id,
        document_id=document.id,
        version_number=next_ver,
        original_filename=os.path.basename(file.filename),
        storage_key=storage_key,
        sha256=calculated_sha256,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        status="UPLOADED",
        uploaded_by=ctx.user_id,
    )
    db.add(version)
    db.flush()

    # 6. Create background processing job
    job = ProcessingJob(
        tenant_id=ctx.tenant_id,
        version_id=version.id,
        status="QUEUED",
        stage="EXTRACTION",
    )
    db.add(job)

    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="DOCUMENT_VERSION_UPLOAD",
        resource_type="DOCUMENT_VERSION",
        resource_id=version.id,
        outcome="SUCCESS",
        metadata_json={
            "document_id": str(document.id),
            "version_number": next_ver,
            "filename": version.original_filename,
        },
    )
    db.add(audit)
    db.commit()

    # 7. Execute ingestion pipeline (Extraction -> Quality Inspection -> Chunking -> Vector Indexing)
    ingestion_pipeline.process_version(
        version.id,
        db,
        allowed_roles=allowed_roles,
        classification=classification,
    )
    db.refresh(version)

    return DocumentUploadResponse(
        document_id=document.id,
        version_id=version.id,
        version_number=next_ver,
        status=version.status,
        job_id=job.id,
        message=f"Version {next_ver} processed successfully. Status: {version.status}.",
    )


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """List all documents belonging to the caller's authorized tenant."""
    documents = (
        db.query(Document)
        .filter(Document.tenant_id == ctx.tenant_id)
        .order_by(Document.updated_at.desc())
        .all()
    )

    responses = []
    for doc in documents:
        # Find active version if any
        active_ver = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.tenant_id == ctx.tenant_id,
                DocumentVersion.status == "ACTIVE",
            )
            .first()
        )
        total_ver = (
            db.query(func.count(DocumentVersion.id))
            .filter(DocumentVersion.document_id == doc.id, DocumentVersion.tenant_id == ctx.tenant_id)
            .scalar()
            or 0
        )
        doc_versions = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.tenant_id == ctx.tenant_id,
            )
            .order_by(DocumentVersion.version_number.desc())
            .all()
        )

        responses.append(
            DocumentResponse(
                id=doc.id,
                tenant_id=doc.tenant_id,
                title=doc.title,
                category=doc.category,
                description=doc.description,
                external_ref=doc.external_ref,
                authority_level=doc.authority_level,
                effective_date=doc.effective_date,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                active_version=DocumentVersionResponse.model_validate(active_ver) if active_ver else None,
                total_versions=total_ver,
                versions=[DocumentVersionResponse.model_validate(v) for v in doc_versions],
            )
        )
    return responses


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document_detail(
    document_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieve details for a single logical document in the authorized workspace."""
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == ctx.tenant_id)
        .first()
    )
    if not doc:
        raise ResourceNotFoundError("Document not found.")

    active_ver = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.tenant_id == ctx.tenant_id,
            DocumentVersion.status == "ACTIVE",
        )
        .first()
    )
    total_ver = (
        db.query(func.count(DocumentVersion.id))
        .filter(DocumentVersion.document_id == doc.id, DocumentVersion.tenant_id == ctx.tenant_id)
        .scalar()
        or 0
    )
    doc_versions = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.tenant_id == ctx.tenant_id,
        )
        .order_by(DocumentVersion.version_number.desc())
        .all()
    )

    return DocumentResponse(
        id=doc.id,
        tenant_id=doc.tenant_id,
        title=doc.title,
        category=doc.category,
        description=doc.description,
        external_ref=doc.external_ref,
        authority_level=doc.authority_level,
        effective_date=doc.effective_date,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        active_version=DocumentVersionResponse.model_validate(active_ver) if active_ver else None,
        total_versions=total_ver,
        versions=[DocumentVersionResponse.model_validate(v) for v in doc_versions],
    )


@router.get("/{document_id}/versions", response_model=List[DocumentVersionResponse])
def list_document_versions(
    document_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """List full version history for a logical document."""
    # Ensure document exists in this tenant
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == ctx.tenant_id)
        .first()
    )
    if not doc:
        raise ResourceNotFoundError("Document not found.")

    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id, DocumentVersion.tenant_id == ctx.tenant_id)
        .order_by(DocumentVersion.version_number.desc())
        .all()
    )
    return [DocumentVersionResponse.model_validate(v) for v in versions]


@router.get("/{document_id}/versions/{version_id}/download")
def download_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Download original document file.
    Enforces strict tenant boundary: callers can only download versions within their authorized tenant.
    """
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
            DocumentVersion.tenant_id == ctx.tenant_id,
        )
        .first()
    )
    if not version:
        raise ResourceNotFoundError("Document version not found.")

    full_path = storage_service._resolve_safe_path(version.storage_key)
    if not os.path.exists(full_path):
        raise ResourceNotFoundError("Physical file for this version is missing.")

    # Audit file download
    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="DOCUMENT_DOWNLOAD",
        resource_type="DOCUMENT_VERSION",
        resource_id=version.id,
        outcome="SUCCESS",
        metadata_json={"filename": version.original_filename},
    )
    db.add(audit)
    db.commit()

    return FileResponse(
        path=full_path,
        media_type=version.mime_type,
        filename=version.original_filename,
    )


@router.get("/{document_id}/versions/{version_id}/quality-report")
def get_version_quality_report(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieve Document Quality Inspector extraction report and diagnostics."""
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
            DocumentVersion.tenant_id == ctx.tenant_id,
        )
        .first()
    )
    if not version:
        raise ResourceNotFoundError("Document version not found.")

    return {
        "version_id": str(version.id),
        "version_number": version.version_number,
        "quality_score": float(version.quality_score or 1.0),
        "ocr_needed": version.ocr_needed,
        "quality_report": version.quality_report or {},
    }


@router.get("/{document_id}/changes")
@router.get("/{document_id}/diff")
def get_document_changes(
    document_id: uuid.UUID,
    to_version_id: Optional[uuid.UUID] = None,
    from_version_id: Optional[uuid.UUID] = None,
    ctx: AuthorizedTenantContext = Depends(get_authorized_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Knowledge Change Intelligence: Computes or retrieves deterministic version diff.
    Highlights clause additions, removals, modifications, and policy impact suggestions.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == ctx.tenant_id)
        .first()
    )
    if not doc:
        raise ResourceNotFoundError("Document not found.")

    target_to_ver_id = to_version_id
    if not target_to_ver_id:
        # Default to latest version in REVIEW or highest version_number
        review_ver = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.tenant_id == ctx.tenant_id,
                DocumentVersion.status == "REVIEW",
            )
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )
        if review_ver:
            target_to_ver_id = review_ver.id
        else:
            latest_ver = (
                db.query(DocumentVersion)
                .filter(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.tenant_id == ctx.tenant_id,
                )
                .order_by(DocumentVersion.version_number.desc())
                .first()
            )
            if not latest_ver:
                raise ResourceNotFoundError("No versions found for document.")
            target_to_ver_id = latest_ver.id

    change = compute_version_diff(
        tenant_id=ctx.tenant_id,
        to_version_id=target_to_ver_id,
        user_id=ctx.user_id,
        db_session=db,
        from_version_id=from_version_id,
    )

    return {
        "change_id": str(change.id),
        "document_id": str(doc.id),
        "document_title": doc.title,
        "from_version_id": str(change.from_version_id) if change.from_version_id else None,
        "to_version_id": str(change.to_version_id),
        "status": change.status,
        "summary": change.summary,
        "items": [
            {
                "id": str(item.id),
                "change_type": item.change_type,
                "section_heading": item.section_heading,
                "old_text": item.old_text,
                "new_text": item.new_text,
                "old_page": item.old_page,
                "new_page": item.new_page,
                "classification": item.classification,
                "confidence": float(item.confidence) if item.confidence is not None else 1.0,
            }
            for item in change.items
        ],
        "impact_suggestions": [
            {
                "id": str(s.id),
                "related_document_id": str(s.related_document_id),
                "rationale": s.rationale,
                "basis": s.basis,
                "review_status": s.review_status,
            }
            for s in change.suggestions
        ],
    }


@router.delete("/{document_id}")
def delete_document(
    document_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Permanently delete an entire policy document and all its versions, chunks, and vector embeddings.

    Security & Access Control:
    - Enforces live PostgreSQL Permission Change Guard via require_client_admin_context.
    - Restricted exclusively to CLIENT_ADMIN and PLATFORM_ADMIN roles. Regular employees receive 403 Forbidden.
    - Strictly scoped to ctx.tenant_id to prevent cross-tenant deletion attacks.
    - Purges stored binary files from disk and vector embeddings from vector index.
    - Records an immutable audit log entry in AuditEvent ledger.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == ctx.tenant_id)
        .first()
    )
    if not doc:
        raise ResourceNotFoundError("Document not found in authorized workspace.")

    # 1. Fetch versions to purge storage files and vector store
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc.id, DocumentVersion.tenant_id == ctx.tenant_id)
        .all()
    )
    version_ids = [v.id for v in versions]

    for v in versions:
        try:
            from app.services.vector_store.chroma import vector_store
            vector_store.delete_version_vectors(ctx.tenant_id, v.id)
        except Exception:
            pass

        try:
            storage_service.delete_file(v.storage_key)
        except Exception:
            pass

    # 2. Clean up relational references
    try:
        db.query(DocumentImpactSuggestion).filter(
            DocumentImpactSuggestion.tenant_id == ctx.tenant_id,
            DocumentImpactSuggestion.related_document_id == doc.id,
        ).delete(synchronize_session=False)

        changes = (
            db.query(DocumentChange)
            .filter(
                DocumentChange.tenant_id == ctx.tenant_id,
                DocumentChange.document_id == doc.id,
            )
            .all()
        )
        for change in changes:
            db.query(DocumentImpactSuggestion).filter(
                DocumentImpactSuggestion.tenant_id == ctx.tenant_id,
                DocumentImpactSuggestion.change_id == change.id,
            ).delete(synchronize_session=False)
            db.query(DocumentChangeItem).filter(
                DocumentChangeItem.tenant_id == ctx.tenant_id,
                DocumentChangeItem.change_id == change.id,
            ).delete(synchronize_session=False)
            db.delete(change)

        if version_ids:
            db.query(QueryEvidence).filter(
                QueryEvidence.tenant_id == ctx.tenant_id,
                QueryEvidence.version_id.in_(version_ids),
            ).delete(synchronize_session=False)
    except Exception:
        pass

    doc_title = doc.title

    # 3. Record audit event
    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="DOCUMENT_DELETED",
        resource_type="DOCUMENT",
        resource_id=doc.id,
        outcome="SUCCESS",
        metadata_json={
            "document_id": str(doc.id),
            "title": doc_title,
            "category": doc.category,
            "deleted_versions_count": len(versions),
        },
    )
    db.add(audit)

    # 4. Delete document (cascades to versions, pages, chunks, processing jobs)
    db.delete(doc)
    db.commit()

    return {
        "status": "success",
        "message": f"Policy document '{doc_title}' was permanently deleted.",
        "document_id": str(document_id),
    }


@router.delete("/{document_id}/versions/{version_id}")
def delete_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    ctx: AuthorizedTenantContext = Depends(require_client_admin_context),
    db: Session = Depends(get_db),
):
    """
    Delete a specific version of a document.

    Security & Access Control:
    - Restricted exclusively to CLIENT_ADMIN or PLATFORM_ADMIN roles.
    - If the deleted version is the only version of the document, the entire document is removed.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == ctx.tenant_id)
        .first()
    )
    if not doc:
        raise ResourceNotFoundError("Document not found in authorized workspace.")

    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
            DocumentVersion.tenant_id == ctx.tenant_id,
        )
        .first()
    )
    if not version:
        raise ResourceNotFoundError("Document version not found.")

    total_versions = (
        db.query(func.count(DocumentVersion.id))
        .filter(DocumentVersion.document_id == document_id, DocumentVersion.tenant_id == ctx.tenant_id)
        .scalar()
        or 0
    )

    try:
        from app.services.vector_store.chroma import vector_store
        vector_store.delete_version_vectors(ctx.tenant_id, version.id)
    except Exception:
        pass

    try:
        storage_service.delete_file(version.storage_key)
    except Exception:
        pass

    try:
        db.query(QueryEvidence).filter(
            QueryEvidence.tenant_id == ctx.tenant_id,
            QueryEvidence.version_id == version.id,
        ).delete(synchronize_session=False)

        changes = (
            db.query(DocumentChange)
            .filter(
                DocumentChange.tenant_id == ctx.tenant_id,
                (DocumentChange.to_version_id == version.id) | (DocumentChange.from_version_id == version.id),
            )
            .all()
        )
        for change in changes:
            db.query(DocumentImpactSuggestion).filter(
                DocumentImpactSuggestion.tenant_id == ctx.tenant_id,
                DocumentImpactSuggestion.change_id == change.id,
            ).delete(synchronize_session=False)
            db.query(DocumentChangeItem).filter(
                DocumentChangeItem.tenant_id == ctx.tenant_id,
                DocumentChangeItem.change_id == change.id,
            ).delete(synchronize_session=False)
            db.delete(change)
    except Exception:
        pass

    audit = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        action="DOCUMENT_VERSION_DELETED",
        resource_type="DOCUMENT_VERSION",
        resource_id=version.id,
        outcome="SUCCESS",
        metadata_json={
            "document_id": str(doc.id),
            "version_number": version.version_number,
            "filename": version.original_filename,
        },
    )
    db.add(audit)

    if total_versions <= 1:
        db.delete(doc)
    else:
        db.delete(version)

    db.commit()

    return {
        "status": "success",
        "message": f"Version v{version.version_number} was successfully deleted.",
        "version_id": str(version_id),
    }


