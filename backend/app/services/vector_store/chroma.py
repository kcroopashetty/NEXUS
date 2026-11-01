"""ChromaDB implementation of the VectorStore interface with tenant collection isolation."""

import os
import uuid
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.services.vector_store.base import VectorStore, VectorSearchResult


class ChromaVectorStore(VectorStore):
    """Manages persistent tenant-isolated Chroma collections."""

    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = os.path.abspath(persist_dir or settings.CHROMA_PERSIST_DIR)
        os.makedirs(self.persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
        )

    def _get_tenant_collection_name(self, tenant_id: uuid.UUID) -> str:
        """Derive private, server-controlled Chroma collection name from tenant UUID."""
        # Chroma collection names must be 3-63 characters, start/end with letter or number
        clean_uuid = str(tenant_id).replace("-", "")
        return f"nexus_t_{clean_uuid}"

    def index_chunks(
        self,
        tenant_id: uuid.UUID,
        vectors: List[List[float]],
        vector_ids: List[str],
        metadatas: List[Dict[str, Any]],
        documents: List[str],
    ) -> None:
        """Upsert vectors into the tenant's private collection."""
        if not vector_ids:
            return

        coll_name = self._get_tenant_collection_name(tenant_id)
        collection = self.client.get_or_create_collection(
            name=coll_name,
            metadata={"tenant_id": str(tenant_id)},
        )

        # Sanitize metadata for Chroma (Chroma accepts str, int, float, bool)
        clean_metadatas = []
        for m in metadatas:
            clean_m = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_m[k] = v
                else:
                    clean_m[k] = str(v)
            clean_metadatas.append(clean_m)

        collection.upsert(
            ids=vector_ids,
            embeddings=vectors,
            metadatas=clean_metadatas,
            documents=documents,
        )

    def search_candidates(
        self,
        tenant_id: uuid.UUID,
        query_vector: List[float],
        top_k: int = 10,
    ) -> List[VectorSearchResult]:
        """Search tenant collection for candidate chunks."""
        coll_name = self._get_tenant_collection_name(tenant_id)
        try:
            collection = self.client.get_collection(name=coll_name)
        except Exception:
            # Collection does not exist yet (no indexed documents)
            return []

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
        )

        candidates: List[VectorSearchResult] = []
        if not results or not results["ids"] or not results["ids"][0]:
            return candidates

        ids_list = results["ids"][0]
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids_list)
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids_list)

        for v_id, dist, meta in zip(ids_list, distances, metas):
            # Chroma returns L2/cosine distance; convert to approximate similarity score
            similarity = 1.0 / (1.0 + max(0.0, float(dist)))
            chunk_id_str = meta.get("chunk_id")
            version_id_str = meta.get("version_id")

            candidates.append(
                VectorSearchResult(
                    vector_id=v_id,
                    chunk_id=uuid.UUID(chunk_id_str) if chunk_id_str else None,
                    version_id=uuid.UUID(version_id_str) if version_id_str else None,
                    score=round(similarity, 4),
                    metadata=meta,
                )
            )
        return candidates

    def delete_version_vectors(
        self,
        tenant_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> None:
        """Purge vectors belonging to a specific version."""
        coll_name = self._get_tenant_collection_name(tenant_id)
        try:
            collection = self.client.get_collection(name=coll_name)
            collection.delete(where={"version_id": str(version_id)})
        except Exception:
            pass


vector_store = ChromaVectorStore()

