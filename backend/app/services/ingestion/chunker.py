"""Chunking service with permission metadata and page-level provenance."""

import hashlib
import uuid
from dataclasses import dataclass
from typing import List, Optional
from app.services.ingestion.extractor import ExtractedPage


@dataclass
class ChunkItem:
    """A granular chunk of document text carrying provenance and access-control tags."""

    chunk_index: int
    page_start: int
    page_end: int
    section_heading: Optional[str]
    chunk_text: str
    text_sha256: str
    allowed_roles: str
    classification: str
    vector_id: str


class DocumentChunker:
    """Divides page-aware text into structured, permission-carrying vector chunks."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_pages(
        self,
        pages: List[ExtractedPage],
        version_id: uuid.UUID,
        allowed_roles: str = "EMPLOYEE,CLIENT_ADMIN",
        classification: str = "INTERNAL",
    ) -> List[ChunkItem]:
        chunks: List[ChunkItem] = []
        chunk_idx = 0

        for page in pages:
            raw_text = page.text.strip()
            if not raw_text:
                continue

            current_heading = page.headings[0] if page.headings else None

            # If text is small enough, keep as single page-bound chunk
            if len(raw_text) <= self.chunk_size:
                c_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                vector_id = f"chunk_{version_id}_{chunk_idx}"
                chunks.append(
                    ChunkItem(
                        chunk_index=chunk_idx,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section_heading=current_heading,
                        chunk_text=raw_text,
                        text_sha256=c_sha,
                        allowed_roles=allowed_roles,
                        classification=classification,
                        vector_id=vector_id,
                    )
                )
                chunk_idx += 1
                continue

            # Sliding window within the page
            start = 0
            while start < len(raw_text):
                end = min(start + self.chunk_size, len(raw_text))

                # Try to break on paragraph or sentence boundary
                if end < len(raw_text):
                    last_newline = raw_text.rfind("\n", start + self.chunk_size // 2, end)
                    last_period = raw_text.rfind(". ", start + self.chunk_size // 2, end)
                    split_point = max(last_newline, last_period)
                    if split_point > start:
                        end = split_point + 1

                piece = raw_text[start:end].strip()
                if piece:
                    c_sha = hashlib.sha256(piece.encode("utf-8")).hexdigest()
                    vector_id = f"chunk_{version_id}_{chunk_idx}"
                    chunks.append(
                        ChunkItem(
                            chunk_index=chunk_idx,
                            page_start=page.page_number,
                            page_end=page.page_number,
                            section_heading=current_heading,
                            chunk_text=piece,
                            text_sha256=c_sha,
                            allowed_roles=allowed_roles,
                            classification=classification,
                            vector_id=vector_id,
                        )
                    )
                    chunk_idx += 1

                start = end - self.chunk_overlap
                if start >= len(raw_text) or end == len(raw_text):
                    break

        return chunks

