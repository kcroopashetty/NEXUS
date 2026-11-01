"""Abstract interface for document and artifact storage."""

import abc
from typing import BinaryIO, Optional


class DocumentStorage(abc.ABC):
    """Abstract storage interface allowing local or private cloud object storage."""

    @abc.abstractmethod
    def save_quarantine(self, file_stream: BinaryIO, upload_id: str) -> str:
        """Stream an unverified uploaded file into the private quarantine area."""
        pass

    @abc.abstractmethod
    def promote_from_quarantine(
        self,
        quarantine_key: str,
        tenant_id: str,
        document_id: str,
        version_id: str,
    ) -> str:
        """Move a validated file from quarantine into its permanent tenant storage path."""
        pass

    @abc.abstractmethod
    def get_file_stream(self, storage_key: str) -> BinaryIO:
        """Retrieve a readable binary stream for a stored file."""
        pass

    @abc.abstractmethod
    def delete_file(self, storage_key: str) -> bool:
        """Delete a file by its storage key."""
        pass

    @abc.abstractmethod
    def get_file_bytes(self, storage_key: str) -> bytes:
        """Read full bytes for small files or parsers."""
        pass

