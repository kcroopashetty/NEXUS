"""Page-aware document text extraction supporting PDF, DOCX, and TXT formats."""

import hashlib
import io
import re
from dataclasses import dataclass
from typing import List, Optional
import pymupdf  # PyMuPDF / fitz
import docx

from app.core.errors import DocumentProcessingError


@dataclass
class ExtractedPage:
    """Represents extracted text and metadata for a single document page."""

    page_number: int  # 1-indexed
    text: str
    sha256: str
    headings: List[str]


class DocumentExtractor:
    """Extracts text and page structure while preserving page numbers and headings."""

    @staticmethod
    def extract(file_bytes: bytes, filename: str) -> List[ExtractedPage]:
        """Route to appropriate format parser based on file extension."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "pdf":
            return DocumentExtractor._extract_pdf(file_bytes)
        elif ext == "docx":
            return DocumentExtractor._extract_docx(file_bytes)
        elif ext == "txt":
            return DocumentExtractor._extract_txt(file_bytes)
        else:
            raise DocumentProcessingError(
                message=f"Unsupported format '.{ext}' for extraction.",
                code="UNSUPPORTED_EXTRACTION_FORMAT",
            )

    @staticmethod
    def _extract_pdf(file_bytes: bytes) -> List[ExtractedPage]:
        """Extract text page-by-page from PDF using PyMuPDF."""
        pages: List[ExtractedPage] = []
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                text = page.get_text("text").strip()
                page_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

                # Basic heading detection from font size/blocks
                headings = []
                blocks = page.get_text("blocks")
                for b in blocks:
                    block_text = b[4].strip()
                    if block_text and len(block_text) < 100 and (block_text.isupper() or block_text.endswith(":")):
                        headings.append(block_text.split("\n")[0])

                pages.append(
                    ExtractedPage(
                        page_number=page_idx + 1,
                        text=text,
                        sha256=page_sha,
                        headings=headings,
                    )
                )
            doc.close()
        except Exception as exc:
            raise DocumentProcessingError(
                message=f"PDF extraction failed: {str(exc)}",
                code="PDF_PARSING_FAILED",
            )
        return pages

    @staticmethod
    def _extract_docx(file_bytes: bytes) -> List[ExtractedPage]:
        """Extract text from Word document, simulating page breaks or paragraph groupings."""
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            full_text_paras = []
            headings = []

            for para in doc.paragraphs:
                p_text = para.text.strip()
                if not p_text:
                    continue
                if para.style and para.style.name and "Heading" in para.style.name:
                    headings.append(p_text)
                full_text_paras.append(p_text)

            text = "\n\n".join(full_text_paras)
            page_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

            # Word files lack physical pages without rendering; return logical page 1
            return [
                ExtractedPage(
                    page_number=1,
                    text=text,
                    sha256=page_sha,
                    headings=headings,
                )
            ]
        except Exception as exc:
            raise DocumentProcessingError(
                message=f"DOCX extraction failed: {str(exc)}",
                code="DOCX_PARSING_FAILED",
            )

    @staticmethod
    def _extract_txt(file_bytes: bytes) -> List[ExtractedPage]:
        """Safely decode plaintext files with encoding fallback."""
        decoded = False
        text = ""
        for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                text = file_bytes.decode(encoding)
                decoded = True
                break
            except UnicodeDecodeError:
                continue

        if not decoded:
            raise DocumentProcessingError(
                message="Failed to decode text file. Unsupported character encoding.",
                code="TEXT_DECODE_FAILED",
            )

        clean_text = text.strip()
        page_sha = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        headings = []
        for line in clean_text.splitlines():
            line = line.strip()
            if line and len(line) < 80 and (line.startswith("#") or line.isupper()):
                headings.append(line.lstrip("#").strip())

        return [
            ExtractedPage(
                page_number=1,
                text=clean_text,
                sha256=page_sha,
                headings=headings,
            )
        ]
