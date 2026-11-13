"""
AI Citation Parser

Extracts inline citations from agent answers and builds a structured 'sources' array
that can be included in API responses.

Inline citation format: [Doc Title, p.N] or [Doc Title]

Used by ai_agent_executor to enrich API responses with citation metadata.
"""

import re
from typing import Any, Dict, List, Optional

# Matches [Doc Title, p.N] or [Doc Title]
_INLINE_CITATION_RE = re.compile(
    r"\[([^\]]+?)(?:,\s*p\.?\s*(\d+))?\]"
)

# Matches markdown links that look like sources: [title](url)
_MD_LINK_SOURCE_RE = re.compile(
    r"\[([^\]]+?)\]\((/api/ai/documents/\d+/download[^)]*)\)"
)


def extract_inline_citations(answer: str) -> List[Dict[str, Any]]:
    """
    Extract inline [Doc Title, p.N] citations from an answer string.

    Returns a list of dicts:
        [{"title": "...", "page": N or None, "citation_text": "..."}]
    Deduplicates by title.
    """
    seen_titles: set = set()
    citations: List[Dict[str, Any]] = []

    for match in _INLINE_CITATION_RE.finditer(answer):
        title = match.group(1).strip()
        page_str = match.group(2)
        page = int(page_str) if page_str else None
        citation_text = match.group(0)

        if title in seen_titles:
            continue
        seen_titles.add(title)
        citations.append({
            "title": title,
            "page": page,
            "citation_text": citation_text,
        })

    return citations


def extract_markdown_source_links(answer: str) -> List[Dict[str, Any]]:
    """
    Extract markdown source links from the ## Sources section of an answer.

    Returns a list of dicts:
        [{"title": "...", "url": "...", "page": N or None}]
    """
    sources: List[Dict[str, Any]] = []
    for match in _MD_LINK_SOURCE_RE.finditer(answer):
        link_text = match.group(1).strip()
        url = match.group(2).strip()
        # Try to parse page number from link text: "Doc Title - page N" or "Doc Title, p. N"
        page = None
        page_match = re.search(r"(?:page|p\.)\s*(\d+)", link_text, re.IGNORECASE)
        if page_match:
            page = int(page_match.group(1))
            title = link_text[:page_match.start()].strip(" -,")
        else:
            title = link_text
        sources.append({"title": title, "url": url, "page": page})
    return sources


def build_sources_array(
    answer: str,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Build a structured sources array from inline citations and/or retrieved chunks.

    Priority:
    1. Inline [Doc Title, p.N] citations → matched against retrieved_chunks for download URL
    2. Markdown source links in ## Sources section
    3. Top retrieved_chunks as fallback (if no citations found)

    Returns a list of source dicts suitable for API response.
    """
    inline = extract_inline_citations(answer)
    md_links = extract_markdown_source_links(answer)

    # Build a lookup of chunk data by title (case-insensitive)
    chunk_by_title: Dict[str, Dict[str, Any]] = {}
    if retrieved_chunks:
        for chunk in retrieved_chunks:
            title = (chunk.get("document_title") or "").strip().lower()
            if title:
                chunk_by_title[title] = chunk

    sources: List[Dict[str, Any]] = []
    seen: set = set()

    for cit in inline:
        title = cit["title"]
        page = cit.get("page")
        key = (title.lower(), page)
        if key in seen:
            continue
        seen.add(key)

        # Try to find chunk for download URL and doc_id
        chunk = chunk_by_title.get(title.lower())
        doc_id = chunk.get("document_id") if chunk else None
        url = f"/api/ai/documents/{doc_id}/download" if doc_id else None

        sources.append({
            "type": "document",
            "title": title,
            "page": page,
            "document_id": doc_id,
            "url": url,
            "document_language": chunk.get("document_language") if chunk else None,
            "document_date": chunk.get("document_date") if chunk else None,
        })

    for lnk in md_links:
        key = (lnk["title"].lower(), lnk.get("page"))
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "type": "document",
            "title": lnk["title"],
            "page": lnk.get("page"),
            "url": lnk["url"],
            "document_id": None,
            "document_language": None,
            "document_date": None,
        })

    # Fallback: include top retrieved chunks as unnamed sources
    if not sources and retrieved_chunks:
        for chunk in retrieved_chunks[:5]:
            doc_id = chunk.get("document_id")
            title = chunk.get("document_title") or f"Document {doc_id}"
            page = chunk.get("page_number")
            key = (title.lower(), page)
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                "type": "document",
                "title": title,
                "page": page,
                "document_id": doc_id,
                "url": f"/api/ai/documents/{doc_id}/download" if doc_id else None,
                "document_language": chunk.get("document_language"),
                "document_date": chunk.get("document_date"),
            })

    return sources
