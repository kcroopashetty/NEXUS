"""Pydantic schemas for document and version management."""

import uuid
from datetime import datetime, date
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class DocumentVersionResponse(BaseModel):
    """Detailed metadata for an immutable document version."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    original_filename: str
    sha256: str
    mime_type: str
    file_size_bytes: int
    status: str
    quality_score: Optional[float] = None
    ocr_needed: bool = False
    quality_report: Dict[str, Any] = Field(default_factory=dict)
    is_conflicting: bool = False
    conflict_notes: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """Logical document container with its active version information."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    external_ref: Optional[str] = None
    authority_level: str
    effective_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    active_version: Optional[DocumentVersionResponse] = None
    total_versions: int = 0
    versions: List[DocumentVersionResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    """Response after initiating document or version upload."""

    document_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    status: str
    job_id: uuid.UUID
    message: str

