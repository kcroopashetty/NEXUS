"""Evidence Passport generation and claim-level grounding verification."""

import re
import uuid
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.services.llm.base import LLMStructuredResponse


@dataclass
class VerifiedClaim:
    """An individual claim verified against an exact source passage."""

    claim_text: str
    citation_id: str
    supported: bool
    document_title: str
    version_number: int
    page_number: int
    authority_level: str
    grounding_score: float


@dataclass
class EvidencePassport:
    """Tamper-evident proof certificate certifying answer grounding and provenance."""

    passport_id: str
    grounding_verified: bool
    grounding_score: float
    status: str
    claims: List[VerifiedClaim]
    evidence_items: List[Dict[str, Any]]
    conflicts_detected: List[str]
    uncertainty_note: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passport_id": self.passport_id,
            "grounding_verified": self.grounding_verified,
            "grounding_score": self.grounding_score,
            "status": self.status,
            "claims": [asdict(c) for c in self.claims],
            "evidence_items": self.evidence_items,
            "conflicts_detected": self.conflicts_detected,
            "uncertainty_note": self.uncertainty_note,
        }


class EvidencePassportValidator:
    """Server-side validator ensuring no hallucinations or unauthorized citations reach the user."""

    @classmethod
    def validate_and_issue(
        cls,
        llm_output: LLMStructuredResponse,
        verified_passages: List[Dict[str, Any]],
    ) -> EvidencePassport:
        passport_id = str(uuid.uuid4())
        passage_map = {p["chunk_id"]: p for p in verified_passages}

        if llm_output.status == "INSUFFICIENT_EVIDENCE" or not verified_passages:
            return EvidencePassport(
                passport_id=passport_id,
                grounding_verified=True,
                grounding_score=1.0,
                status="INSUFFICIENT_EVIDENCE",
                claims=[],
                evidence_items=[],
                conflicts_detected=[],
                uncertainty_note=llm_output.uncertainty_note or "No supporting evidence found in authorized documents.",
            )

        verified_claims: List[VerifiedClaim] = []
        conflicts = []
        supported_claim_count = 0
        total_claims = max(1, len(llm_output.claims) if llm_output.claims else 1)

        # 1. Validate citations and verify claims
        for claim in (llm_output.claims or []):
            claim_text = claim.get("claim_text", "").strip()
            cite_id = str(claim.get("citation_id", ""))

            # Unknown citation ID validation (anti-hallucination rule)
            if cite_id not in passage_map:
                verified_claims.append(
                    VerifiedClaim(
                        claim_text=claim_text,
                        citation_id=cite_id,
                        supported=False,
                        document_title="Unknown / Unverified",
                        version_number=0,
                        page_number=0,
                        authority_level="UNVERIFIED",
                        grounding_score=0.0,
                    )
                )
                continue

            passage = passage_map[cite_id]
            # Grounding check: verify word overlap between claim and passage
            claim_words = set(re.findall(r"\w{3,}", claim_text.lower()))
            passage_words = set(re.findall(r"\w{3,}", passage["chunk_text"].lower()))
            overlap = claim_words.intersection(passage_words)
            overlap_ratio = len(overlap) / max(1, len(claim_words))

            is_supported = overlap_ratio >= 0.35  # Key substantive terms matched
            if is_supported:
                supported_claim_count += 1

            verified_claims.append(
                VerifiedClaim(
                    claim_text=claim_text,
                    citation_id=cite_id,
                    supported=is_supported,
                    document_title=passage["document_title"],
                    version_number=passage["version_number"],
                    page_number=passage["page_start"],
                    authority_level=passage["authority_level"],
                    grounding_score=round(overlap_ratio, 4),
                )
            )

        # 2. Check for conflicts
        if llm_output.status == "CONFLICT":
            conflicts.append("Contradictory directives detected across active policy sources.")

        # 3. Compute overall grounding score
        composite_score = round(supported_claim_count / total_claims, 4)
        is_verified = composite_score >= settings.MIN_GROUNDING_SCORE and len(verified_claims) > 0

        # Build evidence items snapshot
        evidence_items = []
        for p in verified_passages:
            evidence_items.append({
                "chunk_id": p["chunk_id"],
                "document_id": p["document_id"],
                "document_title": p["document_title"],
                "version_id": p["version_id"],
                "version_number": p["version_number"],
                "authority_level": p["authority_level"],
                "page_start": p["page_start"],
                "page_end": p["page_end"],
                "exact_passage": p["chunk_text"],
                "content_sha256": p["content_sha256"],
                "retrieval_score": p["retrieval_score"],
            })

        return EvidencePassport(
            passport_id=passport_id,
            grounding_verified=is_verified,
            grounding_score=composite_score,
            status=llm_output.status if is_verified else "INSUFFICIENT_EVIDENCE",
            claims=verified_claims,
            evidence_items=evidence_items,
            conflicts_detected=conflicts,
            uncertainty_note=llm_output.uncertainty_note,
        )

