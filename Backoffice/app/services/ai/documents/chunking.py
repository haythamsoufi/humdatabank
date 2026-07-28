"""
AI Chunking Service

Implements intelligent document chunking strategies for RAG system.
Splits documents into meaningful chunks with appropriate overlap for context preservation.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from flask import current_app

logger = logging.getLogger(__name__)

_PAGE_MARK_RE = re.compile(r"^\s*\[Page\s+(\d+)\]\s*$", re.IGNORECASE)
_PAGE_MARK_PREFIX_RE = re.compile(r"^\s*\[Page\s+(\d+)\]\s*[\r\n]+(.*)$", re.IGNORECASE | re.DOTALL)
_EXCEL_SHEET_MARK_PREFIX_RE = re.compile(r"^\s*===\s*Sheet:\s*(.+?)\s*===\s*$", re.IGNORECASE)
_PAGE_MARK_ANYWHERE_RE = re.compile(r"\[Page\s+\d+\]", re.IGNORECASE)


@dataclass
class Chunk:
    """Represents a document chunk."""
    content: str
    chunk_index: int
    char_count: int
    token_count: int
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    chunk_type: str = 'semantic'
    overlap_chars: int = 0
    metadata: Optional[Dict[str, Any]] = None


class AIChunkingService:
    """
    Service for intelligently chunking documents.

    Strategies:
    - Semantic chunking: Split on natural boundaries (sentences, paragraphs)
    - Fixed-size chunking: Split at fixed character/token counts
    - Recursive chunking: Hierarchical splitting for large sections
    - Paragraph chunking: Split on paragraph boundaries

    Features:
    - Configurable chunk size and overlap
    - Token counting for LLM context management
    - Preservation of document structure (sections, pages)
    - Metadata tracking for each chunk
    """

    def __init__(self):
        """Initialize the chunking service."""
        self.chunk_size = int(current_app.config.get('AI_CHUNK_SIZE', 512))  # tokens
        self.chunk_overlap = int(current_app.config.get('AI_CHUNK_OVERLAP', 50))  # tokens
        self.min_chunk_size = max(100, self.chunk_size // 4)  # Don't create tiny chunks

        # Initialize tokenizer for token counting
        self._init_tokenizer()

    def _init_tokenizer(self):
        """Initialize tokenizer for counting tokens."""
        try:
            import tiktoken
            self.tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-3.5/GPT-4 encoding
            self.has_tokenizer = True
        except ImportError:
            logger.warning("tiktoken not installed, using approximate token counting")
            self.tokenizer = None
            self.has_tokenizer = False

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self.has_tokenizer and self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Approximate: ~4 characters per token on average
            return len(text) // 4

    def chunk_document(
        self,
        text: str,
        pages: Optional[List[Dict[str, Any]]] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
        strategy: str = 'semantic'
    ) -> List[Chunk]:
        """
        Chunk a document using specified strategy.

        Args:
            text: Full document text
            pages: Optional page information
            sections: Optional section information
            strategy: Chunking strategy ('semantic', 'fixed', 'paragraph', 'recursive')

        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []

        logger.info(f"Chunking document with strategy '{strategy}', target size: {self.chunk_size} tokens")

        if strategy == 'semantic':
            return self._semantic_chunking(text, pages, sections)
        elif strategy == 'fixed':
            return self._fixed_chunking(text, pages, sections)
        elif strategy == 'paragraph':
            return self._paragraph_chunking(text, pages, sections)
        elif strategy == 'recursive':
            return self._recursive_chunking(text, pages, sections)
        else:
            logger.warning(f"Unknown chunking strategy '{strategy}', falling back to semantic")
            return self._semantic_chunking(text, pages, sections)

    def _semantic_chunking(
        self,
        text: str,
        pages: Optional[List[Dict[str, Any]]],
        sections: Optional[List[Dict[str, Any]]]
    ) -> List[Chunk]:
        """
        Semantic chunking: Split on natural boundaries (sentences, paragraphs).

        This is the preferred strategy as it maintains meaning within chunks.
        """
        chunks = []

        # Precompute section lookup (PDF TOC provides {title, page_number}).
        # We assign the most recent section whose page_number <= current page.
        section_starts: List[Dict[str, Any]] = []
        if isinstance(sections, list):
            for s in sections:
                try:
                    if not isinstance(s, dict):
                        continue
                    title = (s.get("title") or "").strip() or None
                    page_number = s.get("page_number")
                    if title and isinstance(page_number, int) and page_number > 0:
                        section_starts.append({"page_number": page_number, "title": title})
                except Exception as e:
                    logger.debug("Skipping invalid section entry: %s", e)
                    continue
        section_starts.sort(key=lambda x: int(x.get("page_number") or 0))

        # Split into paragraphs first
        paragraphs = self._split_paragraphs(text)

        current_chunk = []
        current_tokens = 0
        current_page = None
        current_section = None

        def _flush_current_chunk():
            nonlocal current_chunk, current_tokens
            if not current_chunk:
                return
            chunks.append(
                self._create_chunk(
                    content="\n\n".join(current_chunk),
                    chunk_index=len(chunks),
                    page_number=current_page,
                    section_title=current_section,
                    chunk_type="semantic",
                )
            )
            current_chunk = []
            current_tokens = 0

        def _section_for_page(page_num: Optional[int]) -> Optional[str]:
            if not page_num or not section_starts:
                return current_section
            title = None
            for s in section_starts:
                try:
                    if int(s["page_number"]) <= int(page_num):
                        title = s.get("title") or title
                    else:
                        break
                except Exception as e:
                    logger.debug("_section_for_page skip: %s", e)
                    continue
            return title or current_section

        def _looks_like_table_block(block: str) -> bool:
            """
            Heuristic: tables extracted from PDFs are often newline-heavy, low punctuation,
            and contain many short "cells" per line.
            """
            if not block:
                return False
            # Keep it cheap; avoid heavy parsing.
            line_count = block.count("\n") + 1
            if line_count < 8:
                return False
            # If it has many lines but little sentence punctuation, treat as table-ish.
            punct = sum(block.count(ch) for ch in (".", "!", "?", ";", ":"))
            # Tabs / repeated spacing often indicates columnar text.
            has_tabs_or_columns = ("\t" in block) or bool(re.search(r"\s{3,}\S", block))
            # Many short lines suggests row/cell layout.
            lines = [ln.strip() for ln in re.split(r"\n+", block) if ln.strip()]
            short_lines = sum(1 for ln in lines[:50] if len(ln) <= 60)
            return (punct <= 2 and short_lines >= min(10, max(0, len(lines) // 3))) or has_tabs_or_columns

        def _split_large_block_lines(block: str) -> List[str]:
            """Split a large block into newline-based segments."""
            parts = [ln.strip() for ln in re.split(r"\n+", block) if ln.strip()]
            return parts if parts else [block]

        def _split_large_block_tokens(block: str) -> List[str]:
            """Fallback: split a large block by tokens (or characters) to enforce max chunk size."""
            if self.has_tokenizer and self.tokenizer:
                tokens = self.tokenizer.encode(block)
                out = []
                start = 0
                while start < len(tokens):
                    end = min(start + self.chunk_size, len(tokens))
                    out.append(self.tokenizer.decode(tokens[start:end]).strip())
                    start = max(end - self.chunk_overlap, end) if self.chunk_overlap else end
                return [o for o in out if o]
            # Character-based fallback
            char_size = self.chunk_size * 4
            char_overlap = self.chunk_overlap * 4
            out = []
            start = 0
            while start < len(block):
                end = min(start + char_size, len(block))
                out.append(block[start:end].strip())
                start = max(end - char_overlap, end) if char_overlap else end
            return [o for o in out if o]

        for para in paragraphs:
            # Track page markers injected by AIDocumentProcessor for PDFs.
            # It emits: "\n\n[Page N]\n<page text>"
            # In practice, the marker often appears at the start of a paragraph.
            m_prefix = _PAGE_MARK_PREFIX_RE.match(para)
            if m_prefix:
                # Page boundary: flush the previous page chunk first so we don't mix pages.
                try:
                    next_page = int(m_prefix.group(1))
                except Exception as e:
                    logger.debug("next_page parse failed: %s", e)
                    next_page = None
                if next_page is not None and current_page is not None and next_page != current_page:
                    _flush_current_chunk()
                try:
                    current_page = int(m_prefix.group(1))
                except Exception as e:
                    logger.debug("current_page parse failed: %s", e)
                    current_page = current_page
                current_section = _section_for_page(current_page)
                para = (m_prefix.group(2) or "").strip()
                if not para:
                    continue
            else:
                m_exact = _PAGE_MARK_RE.match(para)
                if m_exact:
                    try:
                        next_page = int(m_exact.group(1))
                    except Exception as e:
                        logger.debug("next_page (exact) parse failed: %s", e)
                        next_page = None
                    if next_page is not None and current_page is not None and next_page != current_page:
                        _flush_current_chunk()
                    try:
                        current_page = int(m_exact.group(1))
                    except Exception as e:
                        logger.debug("current_page (exact) parse failed: %s", e)
                        current_page = current_page
                    current_section = _section_for_page(current_page)
                    continue

            # Track Excel sheet markers from AIDocumentProcessor ("=== Sheet: X ===").
            # This isn't a "page", but it is useful as a section label in citations.
            m_sheet = _EXCEL_SHEET_MARK_PREFIX_RE.match(para.strip())
            if m_sheet:
                current_section = (m_sheet.group(1) or "").strip() or current_section
                continue

            para_tokens = self.count_tokens(para)

            # If single paragraph exceeds chunk size, split it into sentences
            if para_tokens > self.chunk_size:
                # Save current chunk if any
                if current_chunk:
                    chunks.append(self._create_chunk(
                        content='\n\n'.join(current_chunk),
                        chunk_index=len(chunks),
                        page_number=current_page,
                        section_title=current_section,
                        chunk_type='semantic'
                    ))
                    current_chunk = []
                    current_tokens = 0

                # If this looks like table-like text, split by lines to preserve row structure.
                if _looks_like_table_block(para):
                    parts = _split_large_block_lines(para)
                else:
                    # Split paragraph into sentences; if it doesn't split (common for tables),
                    # fall back to token splitting so we never create oversized chunks.
                    sentences = self._split_sentences(para)
                    if len(sentences) <= 1 and self.count_tokens(para) > self.chunk_size:
                        parts = _split_large_block_tokens(para)
                    else:
                        parts = sentences

                for part in parts:
                    part_tokens = self.count_tokens(part)
                    if current_tokens + part_tokens > self.chunk_size and current_chunk:
                        chunks.append(self._create_chunk(
                            content='\n\n'.join(current_chunk),
                            chunk_index=len(chunks),
                            page_number=current_page,
                            section_title=current_section,
                            chunk_type='semantic'
                        ))
                        overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                        current_chunk = [overlap_text, part] if overlap_text else [part]
                        current_tokens = self.count_tokens('\n\n'.join(current_chunk))
                    else:
                        current_chunk.append(part)
                        current_tokens += part_tokens

            # Normal paragraph - add to current chunk
            elif current_tokens + para_tokens > self.chunk_size and current_chunk:
                # Create chunk
                chunks.append(self._create_chunk(
                    content='\n\n'.join(current_chunk),
                    chunk_index=len(chunks),
                    page_number=current_page,
                    section_title=current_section,
                    chunk_type='semantic'
                ))

                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                current_chunk = [overlap_text, para] if overlap_text else [para]
                current_tokens = self.count_tokens('\n\n'.join(current_chunk))
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

        # Add remaining chunk
        if current_chunk:
            chunks.append(self._create_chunk(
                content='\n\n'.join(current_chunk),
                chunk_index=len(chunks),
                page_number=current_page,
                section_title=current_section,
                chunk_type='semantic'
            ))

        logger.info(f"Created {len(chunks)} semantic chunks")
        return chunks

    def _fixed_chunking(
        self,
        text: str,
        pages: Optional[List[Dict[str, Any]]],
        sections: Optional[List[Dict[str, Any]]]
    ) -> List[Chunk]:
        """
        Fixed-size chunking: Split at fixed token counts.

        Simple but may split in the middle of sentences.
        """
        chunks = []
        tokens = self.tokenizer.encode(text) if self.has_tokenizer else None

        if tokens:
            # Token-based splitting
            start = 0
            while start < len(tokens):
                end = min(start + self.chunk_size, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_text = self.tokenizer.decode(chunk_tokens)

                chunks.append(self._create_chunk(
                    content=chunk_text,
                    chunk_index=len(chunks),
                    chunk_type='fixed',
                    overlap_chars=self.chunk_overlap if start > 0 else 0
                ))

                start = end - self.chunk_overlap
        else:
            # Character-based splitting (fallback)
            char_size = self.chunk_size * 4  # Approximate
            char_overlap = self.chunk_overlap * 4

            start = 0
            while start < len(text):
                end = min(start + char_size, len(text))
                chunk_text = text[start:end]

                chunks.append(self._create_chunk(
                    content=chunk_text,
                    chunk_index=len(chunks),
                    chunk_type='fixed',
                    overlap_chars=char_overlap if start > 0 else 0
                ))

                start = end - char_overlap

        logger.info(f"Created {len(chunks)} fixed-size chunks")
        return chunks

    def _paragraph_chunking(
        self,
        text: str,
        pages: Optional[List[Dict[str, Any]]],
        sections: Optional[List[Dict[str, Any]]]
    ) -> List[Chunk]:
        """
        Paragraph chunking: Each paragraph becomes a chunk (or groups of small paragraphs).
        """
        chunks = []
        paragraphs = self._split_paragraphs(text)

        current_group = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            # If paragraph alone exceeds chunk size, it becomes its own chunk
            if para_tokens > self.chunk_size:
                # Save current group
                if current_group:
                    chunks.append(self._create_chunk(
                        content='\n\n'.join(current_group),
                        chunk_index=len(chunks),
                        chunk_type='paragraph'
                    ))
                    current_group = []
                    current_tokens = 0

                # Large paragraph as single chunk
                chunks.append(self._create_chunk(
                    content=para,
                    chunk_index=len(chunks),
                    chunk_type='paragraph'
                ))

            # Add to group if it fits
            elif current_tokens + para_tokens <= self.chunk_size:
                current_group.append(para)
                current_tokens += para_tokens

            # Start new group
            else:
                if current_group:
                    chunks.append(self._create_chunk(
                        content='\n\n'.join(current_group),
                        chunk_index=len(chunks),
                        chunk_type='paragraph'
                    ))
                current_group = [para]
                current_tokens = para_tokens

        # Add remaining group
        if current_group:
            chunks.append(self._create_chunk(
                content='\n\n'.join(current_group),
                chunk_index=len(chunks),
                chunk_type='paragraph'
            ))

        logger.info(f"Created {len(chunks)} paragraph chunks")
        return chunks

    def _recursive_chunking(
        self,
        text: str,
        pages: Optional[List[Dict[str, Any]]],
        sections: Optional[List[Dict[str, Any]]]
    ) -> List[Chunk]:
        """
        Recursive chunking: Hierarchical splitting.

        Tries to split on large separators first, then smaller ones.
        Preserves document structure better than other methods.
        """
        separators = [
            '\n\n\n',  # Multiple line breaks (section boundaries)
            '\n\n',    # Paragraph breaks
            '\n',      # Line breaks
            '. ',      # Sentence boundaries
            '! ',
            '? ',
            ', ',      # Clause boundaries
            ' ',       # Word boundaries
        ]

        chunks = self._recursive_split(text, separators, 0)

        # Convert to Chunk objects
        result = []
        for i, chunk_text in enumerate(chunks):
            if chunk_text.strip() and self.count_tokens(chunk_text) >= self.min_chunk_size:
                result.append(self._create_chunk(
                    content=chunk_text,
                    chunk_index=i,
                    chunk_type='recursive'
                ))

        logger.info(f"Created {len(result)} recursive chunks")
        return result

    def _recursive_split(self, text: str, separators: List[str], level: int) -> List[str]:
        """Recursively split text on separators."""
        if not separators or self.count_tokens(text) <= self.chunk_size:
            return [text]

        separator = separators[0]
        remaining_separators = separators[1:]

        chunks = []
        parts = text.split(separator)

        current_chunk = ""
        for part in parts:
            test_chunk = current_chunk + separator + part if current_chunk else part

            if self.count_tokens(test_chunk) <= self.chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                # If single part is too large, split it recursively
                if self.count_tokens(part) > self.chunk_size:
                    sub_chunks = self._recursive_split(part, remaining_separators, level + 1)
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split on double newlines or more
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting (could be improved with NLP library)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _get_overlap_text(self, chunks: List[str], overlap_tokens: int) -> str:
        """Get overlap text from previous chunks."""
        if not chunks:
            return ""

        # Take last chunk(s) until we have enough overlap
        overlap_text = ""
        for chunk in reversed(chunks):
            overlap_text = chunk + "\n\n" + overlap_text
            if self.count_tokens(overlap_text) >= overlap_tokens:
                break

        # Trim to exact overlap size
        if self.has_tokenizer and self.tokenizer:
            tokens = self.tokenizer.encode(overlap_text)
            if len(tokens) > overlap_tokens:
                tokens = tokens[-overlap_tokens:]
                overlap_text = self.tokenizer.decode(tokens)

        return overlap_text.strip()

    def _create_chunk(
        self,
        content: str,
        chunk_index: int,
        page_number: Optional[int] = None,
        section_title: Optional[str] = None,
        chunk_type: str = 'semantic',
        overlap_chars: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Chunk:
        """Create a Chunk object with metadata."""
        content = (content or "").strip()

        # For readability and backward compatibility with older behavior, include a page marker
        # in the stored chunk text (in addition to the page_number column).
        if page_number and not _PAGE_MARK_ANYWHERE_RE.search(content):
            content = f"[Page {int(page_number)}]\n{content}".strip()

        return Chunk(
            content=content,
            chunk_index=chunk_index,
            char_count=len(content),
            token_count=self.count_tokens(content),
            page_number=page_number,
            section_title=section_title,
            chunk_type=chunk_type,
            overlap_chars=overlap_chars,
            metadata=metadata if (isinstance(metadata, dict) and metadata) else None
        )

    def chunk_tables(self, tables: Optional[List[Dict[str, Any]]]) -> List[Chunk]:
        """
        Convert extracted tables into JSON-backed chunks.

        Each chunk stores:
        - A readable text representation (for embeddings/search)
        - A structured JSON representation in metadata['table'] (for deterministic use)
        """
        if not tables:
            return []
        out: List[Chunk] = []

        def norm_cell(v: Any) -> str:
            s = "" if v is None else str(v)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        for t in tables:
            if not isinstance(t, dict):
                continue
            page_number = t.get("page_number")
            table_index = t.get("table_index")
            header = t.get("header") or []
            rows = t.get("rows") or []
            records = t.get("records") or []
            if not isinstance(rows, list) or not rows:
                continue
            # Normalize rows
            norm_rows: List[List[str]] = []
            for r in rows:
                if isinstance(r, (list, tuple)):
                    norm_rows.append([norm_cell(c) for c in r])
                else:
                    norm_rows.append([norm_cell(r)])
            if not norm_rows:
                continue
            # Header may already be extracted separately; if not, fall back to first row.
            if not isinstance(header, list) or not header:
                header = norm_rows[0]
                data_rows = norm_rows[1:] if len(norm_rows) > 1 else []
            else:
                data_rows = norm_rows
            total_data_rows = len(data_rows)

            # Chunk rows into groups that fit roughly into chunk_size.
            # Keep header in every chunk for readability.
            current_group: List[List[str]] = []
            current_tokens = 0
            group_start = 0

            def flush_group(group_rows: List[List[str]], start_idx: int):
                nonlocal current_tokens
                if not group_rows:
                    return

                # Build readable, unambiguous text for embedding.
                # Prefer parsed records if they align with rows (one record per expanded row).
                category_cols = list(header[1:]) if isinstance(header, list) and len(header) > 1 else []

                # Expected "core" columns (the PDF header often collapses these into the first column)
                cols = ["National Society", "Year", "Funding Requirement", "Confirmed Funding"] + category_cols
                lines = [
                    f"Table {table_index}",
                    f"Columns: {' | '.join([c for c in cols if c])}",
                ]

                group_records = None
                if isinstance(records, list) and records and len(records) >= (start_idx + len(group_rows)):
                    # Best-effort assumption: records are aligned with expanded rows order.
                    group_records = records[start_idx : start_idx + len(group_rows)]

                if group_records:
                    for rec in group_records:
                        if not isinstance(rec, dict):
                            continue
                        ns = norm_cell(rec.get("national_society"))
                        year = norm_cell(rec.get("year"))
                        fr = norm_cell(rec.get("funding_requirement"))
                        cf = norm_cell(rec.get("confirmed_funding"))
                        cats = rec.get("categories") or {}
                        row_parts = [ns, year, fr, cf]
                        for c in category_cols:
                            row_parts.append(norm_cell(cats.get(c, "")) if isinstance(cats, dict) else "")
                        lines.append(" | ".join(row_parts).rstrip())
                else:
                    # Fallback to raw rows (still useful for retrieval, but can be ambiguous)
                    for rr in group_rows:
                        lines.append(" | ".join([c for c in rr]))

                text = "\n".join(lines).strip()

                table_obj = {
                    "page_number": page_number,
                    "table_index": table_index,
                    "bbox": t.get("bbox"),
                    "header": header,
                    "rows": group_rows,
                    "row_start": int(start_idx),
                    "row_end": int(start_idx + len(group_rows) - 1),
                    "total_rows": int(total_data_rows),
                    "records": records,
                }

                out.append(
                    self._create_chunk(
                        content=text,
                        chunk_index=len(out),  # temporary; caller may reindex
                        page_number=int(page_number) if isinstance(page_number, int) else None,
                        section_title=f"Table {table_index}",
                        chunk_type="table",
                        metadata={"table": table_obj},
                    )
                )
                current_tokens = 0

            # If there's no data rows, still store the header as a single chunk.
            if not data_rows:
                flush_group([header], 0)
                continue

            # Token budget for a group (reserve some room for headers/overlap).
            max_group_tokens = max(100, int(self.chunk_size) - 80)

            for i, rr in enumerate(data_rows):
                rr_text = " | ".join(rr)
                rr_tokens = self.count_tokens(rr_text)
                if current_group and (current_tokens + rr_tokens > max_group_tokens):
                    flush_group(current_group, group_start)
                    current_group = []
                    current_tokens = 0
                    group_start = i

                current_group.append(rr)
                current_tokens += rr_tokens

            if current_group:
                flush_group(current_group, group_start)

        # Note: chunk_index will be re-assigned by the caller when merging with text chunks.
        return out

    def chunk_upr_visuals(
        self,
        *,
        pages: Optional[List[Dict[str, Any]]],
        document_title: Optional[str] = None,
        document_filename: Optional[str] = None,
    ) -> List[Chunk]:
        """
        Create structured chunks for repeated UPR visual blocks (template-specific).

        Similar to `chunk_tables()`, each chunk includes:
        - embedding-friendly text content
        - structured JSON in metadata['upr']
        """
        try:
            enabled = bool(current_app.config.get("AI_UPR_VISUAL_CHUNKING_ENABLED", True))
        except Exception as e:
            logger.debug("AI_UPR_VISUAL_CHUNKING_ENABLED config read failed: %s", e)
            enabled = True
        if not enabled:
            return []

        if not pages:
            return []

        try:
            from app.services.upr.visual_chunking import (
                is_likely_upr_document,
                extract_in_support_kpis,
                extract_people_reached,
                extract_financial_overview,
                extract_funding_requirements,
                extract_hazards,
                extract_pns_bilateral_support,
                block_to_embedding_text,
            )
        except Exception as e:
            logger.debug("upr_visual_chunking import failed: %s", e)
            return []

        if not is_likely_upr_document(title=document_title, filename=document_filename, pages=pages):
            return []

        # UPR visuals are expected in the first 1–3 pages; older docs (country plans) may have
        # hazards, PNS bilateral support table, and funding requirements on pages 3–5.
        upr_pages = (pages or [])[:5]

        blocks = []
        blocks.extend(extract_in_support_kpis(upr_pages))
        blocks.extend(extract_people_reached(upr_pages))
        blocks.extend(extract_financial_overview(upr_pages))
        blocks.extend(extract_funding_requirements(upr_pages))
        blocks.extend(extract_hazards(upr_pages))
        blocks.extend(extract_pns_bilateral_support(upr_pages))
        if not blocks:
            return []

        out: List[Chunk] = []
        for b in blocks:
            try:
                page_number = b.get("page_number")
                text = block_to_embedding_text(b)
                out.append(
                    self._create_chunk(
                        content=text,
                        chunk_index=len(out),  # temporary; caller may reindex
                        page_number=int(page_number) if isinstance(page_number, int) else None,
                        section_title=f"UPR: {str(b.get('block') or 'visual')}",
                        chunk_type="upr_visual",
                        metadata={"upr": b},
                    )
                )
            except Exception as e:
                logger.debug("Skipping UPR block chunk: %s", e)
                continue

        return out

    def optimize_chunks_for_context_window(
        self,
        chunks: List[Chunk],
        max_context_tokens: int = 4000
    ) -> List[List[Chunk]]:
        """
        Group chunks that fit within a context window.

        Useful for batching multiple chunks in a single LLM call.
        """
        groups = []
        current_group = []
        current_tokens = 0

        for chunk in chunks:
            if current_tokens + chunk.token_count > max_context_tokens:
                if current_group:
                    groups.append(current_group)
                current_group = [chunk]
                current_tokens = chunk.token_count
            else:
                current_group.append(chunk)
                current_tokens += chunk.token_count

        if current_group:
            groups.append(current_group)

        return groups
