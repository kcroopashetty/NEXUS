"""Abstract LLM inference service interface."""

import abc
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class LLMStructuredResponse(BaseModel):
    """Raw structured output parsed from LLM completion."""

    status: str  # 'ANSWERED', 'INSUFFICIENT_EVIDENCE', 'CONFLICT'
    answer: str
    evidence_ids: List[str]
    claims: List[Dict[str, Any]] = []
    uncertainty_note: Optional[str] = None


class LLMService(abc.ABC):
    """Interface for local model inference."""

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        pass

    @abc.abstractmethod
    def generate_grounded_answer(
        self,
        question: str,
        evidence_passages: List[Dict[str, Any]],
    ) -> LLMStructuredResponse:
        """Prompt the local LLM to generate an answer strictly grounded in evidence."""
        pass

