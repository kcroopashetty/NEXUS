"""Local filesystem implementation of DocumentStorage."""

import os
import shutil
from typing import BinaryIO, Optional
from pathlib import Path

from app.core.config import settings
from app.core.errors import DocumentProcessingError
from app.services.storage.base import DocumentStorage


class LocalDocumentStorage(DocumentStorage):
    """Local filesystem storage adapter adhering to tenant path isolation."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = os.path.abspath(base_dir or settings.NEXUS_STORAGE_DIR)
        os.makedirs(self.base_dir, exist_ok=True)
        self.quarantine_dir = os.path.join(self.base_dir, "quarantine")
        os.makedirs(self.quarantine_dir, exist_ok=True)

    def _resolve_safe_path(self, relative_key: str) -> str:
        """Resolve a storage key and verify it stays strictly within base_dir."""
        # Normalize separators
        clean_key = relative_key.replace("\\", "/").strip("/")
        full_path = os.path.abspath(os.path.join(self.base_dir, clean_key))
        if not full_path.startswith(self.base_dir):
            raise DocumentProcessingError(
                message="Illegal storage path traversal detected.",
                code="STORAGE_PATH_TRAVERSAL",
            )
        return full_path

    def save_quarantine(self, file_stream: BinaryIO, upload_id: str) -> str:
        """Stream an unverified file into quarantine/<upload_id>."""
        relative_key = f"quarantine/{upload_id}"
        full_path = self._resolve_safe_path(relative_key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "wb") as dest:
            shutil.copyfileobj(file_stream, dest)

        return relative_key

    def promote_from_quarantine(
        self,
        quarantine_key: str,
        tenant_id: str,
        document_id: str,
        version_id: str,
    ) -> str:
        """Move from quarantine into tenants/<tenant_id>/documents/<document_id>/<version_id>/original."""
        src_path = self._resolve_safe_path(quarantine_key)
        if not os.path.exists(src_path):
            raise DocumentProcessingError(
                message="Quarantined file not found.",
                code="FILE_NOT_FOUND",
            )

        relative_dest_key = f"tenants/{tenant_id}/documents/{document_id}/{version_id}/original"
        dest_path = self._resolve_safe_path(relative_dest_key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        shutil.move(src_path, dest_path)
        return relative_dest_key

    def get_file_stream(self, storage_key: str) -> BinaryIO:
        """Return an open file handle in read-binary mode."""
        full_path = self._resolve_safe_path(storage_key)
        if not os.path.exists(full_path):
            raise DocumentProcessingError(
                message="Stored file does not exist.",
                code="FILE_NOT_FOUND",
            )
        return open(full_path, "rb")

    def get_file_bytes(self, storage_key: str) -> bytes:
        """Read all bytes from stored file."""
        with self.get_file_stream(storage_key) as f:
            return f.read()

    def delete_file(self, storage_key: str) -> bool:
        """Delete file if it exists."""
        full_path = self._resolve_safe_path(storage_key)
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False


# Global default instance
storage_service = LocalDocumentStorage()
