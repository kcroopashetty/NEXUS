"""Knowledge Change Intelligence: Deterministic Diffing and Policy Impact Analysis."""

import difflib
import logging
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.document_page import DocumentPage
from app.models.document_chunk import DocumentChunk
from app.models.document_change import DocumentChange
from app.models.document_change_item import DocumentChangeItem
from app.models.document_impact_suggestion import DocumentImpactSuggestion

logger = logging.getLogger("nexus.change_intelligence")


def _classify_text(text: str) -> str:
    """Classify the policy domain of a clause based on deterministic keywords."""
    t_lower = text.lower()
    if re.search(r"\b(hours|days|business days|sla|timeline|turnaround|deadline)\b", t_lower):
        return "SLA"
    if re.search(r"(\$|\b(cost|fee|expense|reimburse|reimbursement|payment|penalty|usd)\b)", t_lower):
        return "FINANCIAL"
    if re.search(r"\b(director|signoff|escalat|escalation|approve|approval|officer|manager)\b", t_lower):
        return "GOVERNANCE"
    if re.search(r"\b(confidential|security|access|credential|encryption|restricted)\b", t_lower):
        return "SECURITY"
    return "GENERAL"


def _extract_clauses_with_pages(pages: List[DocumentPage]) -> List[Tuple[int, str]]:
    """Split page texts into distinct clauses/sentences along with page numbers."""
    clauses = []
    for page in pages:
        # Split by periods, semicolons, or newlines followed by space or uppercase
        raw_splits = re.split(r"(?<=[.;\n])\s+", page.extracted_text)
        for s in raw_splits:
            cleaned = s.strip()
            if len(cleaned) >= 5:  # skip empty or trivial punctuation
                clauses.append((page.page_number, cleaned))
    return clauses


def compute_version_diff(
    tenant_id: uuid.UUID,
    to_version_id: uuid.UUID,
    user_id: uuid.UUID,
    db_session: Session,
    from_version_id: Optional[uuid.UUID] = None,
) -> DocumentChange:
    """
    Computes a deterministic passage-level diff between from_version and to_version,
    persisting DocumentChange, DocumentChangeItem, and DocumentImpactSuggestion records.
    """
    to_version = (
        db_session.query(DocumentVersion)
        .filter(DocumentVersion.tenant_id == tenant_id, DocumentVersion.id == to_version_id)
        .first()
    )
    if not to_version:
        raise ValueError(f"Target version {to_version_id} not found in tenant {tenant_id}")

    # If from_version_id is not specified, check for an existing ACTIVE version or prior version number
    if not from_version_id:
        prior_active = (
            db_session.query(DocumentVersion)
            .filter(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == to_version.document_id,
                DocumentVersion.status == "ACTIVE",
                DocumentVersion.id != to_version.id,
            )
            .first()
        )
        if prior_active:
            from_version_id = prior_active.id
        else:
            # Fallback: version with version_number = to_version.version_number - 1
            prior_by_num = (
                db_session.query(DocumentVersion)
                .filter(
                    DocumentVersion.tenant_id == tenant_id,
                    DocumentVersion.document_id == to_version.document_id,
                    DocumentVersion.version_number < to_version.version_number,
                )
                .order_by(DocumentVersion.version_number.desc())
                .first()
            )
            if prior_by_num:
                from_version_id = prior_by_num.id

    # Check if a DocumentChange already exists
    existing_change = (
        db_session.query(DocumentChange)
        .filter(
            DocumentChange.tenant_id == tenant_id,
            DocumentChange.document_id == to_version.document_id,
            DocumentChange.from_version_id == from_version_id,
            DocumentChange.to_version_id == to_version_id,
        )
        .first()
    )
    if existing_change:
        return existing_change

    to_pages = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.tenant_id == tenant_id, DocumentPage.version_id == to_version_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    to_clauses = _extract_clauses_with_pages(to_pages)

    change_record = DocumentChange(
        tenant_id=tenant_id,
        document_id=to_version.document_id,
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        status="PENDING_REVIEW",
        created_by=user_id,
    )
    db_session.add(change_record)
    db_session.flush()

    items: List[DocumentChangeItem] = []

    if not from_version_id:
        # First version: all clauses are additions
        for page_num, clause in to_clauses:
            item = DocumentChangeItem(
                tenant_id=tenant_id,
                change_id=change_record.id,
                change_type="ADDITION",
                section_heading=None,
                old_text=None,
                new_text=clause,
                old_page=None,
                new_page=page_num,
                classification=_classify_text(clause),
                confidence=1.0,
            )
            items.append(item)
    else:
        from_pages = (
            db_session.query(DocumentPage)
            .filter(DocumentPage.tenant_id == tenant_id, DocumentPage.version_id == from_version_id)
            .order_by(DocumentPage.page_number.asc())
            .all()
        )
        from_clauses = _extract_clauses_with_pages(from_pages)

        from_texts = [c[1] for c in from_clauses]
        to_texts = [c[1] for c in to_clauses]

        matcher = difflib.SequenceMatcher(None, from_texts, to_texts)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            elif tag == "delete":
                for idx in range(i1, i2):
                    page_num, clause = from_clauses[idx]
                    items.append(
                        DocumentChangeItem(
                            tenant_id=tenant_id,
                            change_id=change_record.id,
                            change_type="REMOVAL",
                            section_heading=None,
                            old_text=clause,
                            new_text=None,
                            old_page=page_num,
                            new_page=None,
                            classification=_classify_text(clause),
                            confidence=1.0,
                        )
                    )
            elif tag == "insert":
                for idx in range(j1, j2):
                    page_num, clause = to_clauses[idx]
                    items.append(
                        DocumentChangeItem(
                            tenant_id=tenant_id,
                            change_id=change_record.id,
                            change_type="ADDITION",
                            section_heading=None,
                            old_text=None,
                            new_text=clause,
                            old_page=None,
                            new_page=page_num,
                            classification=_classify_text(clause),
                            confidence=1.0,
                        )
                    )
            elif tag == "replace":
                del_count = i2 - i1
                ins_count = j2 - j1
                # If 1-to-1 or equal count, treat as modifications
                if del_count == ins_count:
                    for k in range(del_count):
                        old_p, old_t = from_clauses[i1 + k]
                        new_p, new_t = to_clauses[j1 + k]
                        items.append(
                            DocumentChangeItem(
                                tenant_id=tenant_id,
                                change_id=change_record.id,
                                change_type="MODIFICATION",
                                section_heading=None,
                                old_text=old_t,
                                new_text=new_t,
                                old_page=old_p,
                                new_page=new_p,
                                classification=_classify_text(new_t) or _classify_text(old_t),
                                confidence=1.0,
                            )
                        )
                else:
                    # Compare pairs by string similarity
                    used_ins = set()
                    for idx_del in range(i1, i2):
                        old_p, old_t = from_clauses[idx_del]
                        best_sim = 0.0
                        best_ins_idx = -1
                        for idx_ins in range(j1, j2):
                            if idx_ins in used_ins:
                                continue
                            sim = difflib.SequenceMatcher(None, old_t, to_clauses[idx_ins][1]).ratio()
                            if sim > best_sim:
                                best_sim = sim
                                best_ins_idx = idx_ins

                        if best_sim >= 0.4 and best_ins_idx != -1:
                            used_ins.add(best_ins_idx)
                            new_p, new_t = to_clauses[best_ins_idx]
                            items.append(
                                DocumentChangeItem(
                                    tenant_id=tenant_id,
                                    change_id=change_record.id,
                                    change_type="MODIFICATION",
                                    section_heading=None,
                                    old_text=old_t,
                                    new_text=new_t,
                                    old_page=old_p,
                                    new_page=new_p,
                                    classification=_classify_text(new_t) or _classify_text(old_t),
                                    confidence=round(best_sim, 4),
                                )
                            )
                        else:
                            items.append(
                                DocumentChangeItem(
                                    tenant_id=tenant_id,
                                    change_id=change_record.id,
                                    change_type="REMOVAL",
                                    section_heading=None,
                                    old_text=old_t,
                                    new_text=None,
                                    old_page=old_p,
                                    new_page=None,
                                    classification=_classify_text(old_t),
                                    confidence=1.0,
                                )
                            )

                    # Remaining inserts are additions
                    for idx_ins in range(j1, j2):
                        if idx_ins not in used_ins:
                            new_p, new_t = to_clauses[idx_ins]
                            items.append(
                                DocumentChangeItem(
                                    tenant_id=tenant_id,
                                    change_id=change_record.id,
                                    change_type="ADDITION",
                                    section_heading=None,
                                    old_text=None,
                                    new_text=new_t,
                                    old_page=None,
                                    new_page=new_p,
                                    classification=_classify_text(new_t),
                                    confidence=1.0,
                                )
                            )

    db_session.add_all(items)

    # Compute summary
    n_add = sum(1 for item in items if item.change_type == "ADDITION")
    n_rem = sum(1 for item in items if item.change_type == "REMOVAL")
    n_mod = sum(1 for item in items if item.change_type == "MODIFICATION")

    from_ver = db_session.get(DocumentVersion, from_version_id) if from_version_id else None
    from_ver_str = f"v{from_ver.version_number}" if from_ver else "scratch"
    change_record.summary = (
        f"Change report comparing {from_ver_str} -> v{to_version.version_number}: "
        f"{n_mod} modifications, {n_add} additions, {n_rem} removals."
    )
    change_record.summary_model = "nexus-difflib-deterministic-v1"

    # Knowledge Integrity: Policy Impact Suggestions on other documents
    # If any SLA or Governance items changed, inspect other tenant documents
    policy_items = [it for it in items if it.classification in ("SLA", "GOVERNANCE", "FINANCIAL")]
    if policy_items:
        other_active_versions = (
            db_session.query(DocumentVersion)
            .filter(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id != to_version.document_id,
                DocumentVersion.status == "ACTIVE",
            )
            .all()
        )
        for other_ver in other_active_versions:
            other_doc = other_ver.document
            if not other_doc:
                continue
            # Check if other doc title or active chunks match policy keywords
            for p_item in policy_items:
                target_text = (p_item.new_text or p_item.old_text or "").lower()
                keywords = [w for w in re.findall(r"\w{4,}", target_text) if w not in ("shall", "within", "clause", "document", "require", "section")]
                if any(kw in other_doc.title.lower() for kw in keywords):
                    suggestion = DocumentImpactSuggestion(
                        tenant_id=tenant_id,
                        change_id=change_record.id,
                        related_document_id=other_doc.id,
                        rationale=(
                            f"Document '{other_doc.title}' may be impacted by {p_item.classification} changes "
                            f"in clause: '{p_item.new_text or p_item.old_text}'."
                        ),
                        basis="KEYWORD",
                        review_status="PENDING",
                    )
                    db_session.add(suggestion)
                    break

    db_session.commit()
    db_session.refresh(change_record)
    return change_record
