"""Abstract embedding service interface."""

import abc
from typing import List


class EmbeddingService(abc.ABC):
    """Interface for generating dense vector representations locally."""

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """Name or identifier of the active embedding model."""
        pass

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality."""
        pass

    @abc.abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of text passages."""
        pass

    @abc.abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """Generate an embedding vector for a search query."""
        pass

