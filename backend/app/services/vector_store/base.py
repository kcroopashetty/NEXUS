"""Abstract vector store interface."""

import abc
import uuid
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class VectorSearchResult:
    """Candidate match returned by vector similarity search."""

    vector_id: str
    chunk_id: Optional[uuid.UUID]
    version_id: Optional[uuid.UUID]
    score: float
    metadata: Dict[str, Any]


class VectorStore(abc.ABC):
    """Abstract interface for tenant-isolated vector indexing and retrieval."""

    @abc.abstractmethod
    def index_chunks(
        self,
        tenant_id: uuid.UUID,
        vectors: List[List[float]],
        vector_ids: List[str],
        metadatas: List[Dict[str, Any]],
        documents: List[str],
    ) -> None:
        """Store chunk vectors and metadata into the tenant's isolated collection."""
        pass

    @abc.abstractmethod
    def search_candidates(
        self,
        tenant_id: uuid.UUID,
        query_vector: List[float],
        top_k: int = 10,
    ) -> List[VectorSearchResult]:
        """Search for top-k candidate chunks within the server-selected tenant collection."""
        pass

    @abc.abstractmethod
    def delete_version_vectors(
        self,
        tenant_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> None:
        """Purge vectors belonging to a specific version if required."""
        pass

