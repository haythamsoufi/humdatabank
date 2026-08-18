"""Grounded LLM term extraction and bilingual pairing for glossary mining.

Pairs are kept only when both sides are attested in retrieved document text.
Retrieval is embedding search scoped to the target document — not chunk index.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from flask import current_app

logger = logging.getLogger(__name__)

_TERM_NOISE = re.compile(r"[\[\]{}<>]|page\s+\d+", re.IGNORECASE)
_MULTI_SPACE = re.compile(r"\s+")


def normalize_span(text: str) -> str:
    return _MULTI_SPACE.sub(" ", (text or "").replace("\u00a0", " ")).strip().lower()


def term_is_attested(term: str, corpus: str) -> bool:
    needle = normalize_span(term)
    hay = normalize_span(corpus)
    if len(needle) < 2 or len(hay) < 2:
        return False
    return needle in hay


def usable_glossary_term(term: str, *, max_words: int = 12, max_chars: int = 100) -> Optional[str]:
    cleaned = _MULTI_SPACE.sub(" ", (term or "").strip())
    if not cleaned:
        return None
    if _TERM_NOISE.search(cleaned):
        return None
    if cleaned.lower().startswith("page "):
        return None
    words = cleaned.split()
    if not (1 <= len(words) <= max_words):
        return None
    if len(cleaned) > max_chars:
        return None
    if cleaned.endswith(".") and len(words) > 6:
        return None
    return cleaned


def dedupe_source_terms(terms: Sequence[Dict[str, Any]], *, cap: int = 20) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in terms:
        term = usable_glossary_term(str(row.get("term") or row.get("source_term") or ""))
        if not term:
            continue
        key = normalize_span(term)
        if key in seen:
            continue
        evidence = _MULTI_SPACE.sub(" ", str(row.get("evidence") or row.get("en_evidence") or "")).strip()
        if evidence and not term_is_attested(term, evidence):
            continue
        seen.add(key)
        tier = str(row.get("tier") or row.get("proposed_tier") or "preferred").lower()
        if tier not in ("must", "preferred"):
            tier = "preferred"
        out.append({"term": term, "evidence": evidence[:240], "tier": tier})
        if len(out) >= cap:
            break
    return out


def ground_pairs(
    proposed: Sequence[Dict[str, Any]],
    excerpts_by_source: Dict[str, str],
    *,
    target_lang: str,
) -> List[Dict[str, Any]]:
    """Drop pairs whose target wording is not in the retrieved target excerpts."""
    grounded: List[Dict[str, Any]] = []
    for row in proposed:
        source = usable_glossary_term(str(row.get("source_term") or ""))
        target = usable_glossary_term(str(row.get("target_term") or ""), max_words=14, max_chars=120)
        if not source or not target:
            continue
        corpus = excerpts_by_source.get(source) or excerpts_by_source.get(normalize_span(source)) or ""
        extra = str(row.get("target_evidence") or "")
        if extra:
            corpus = f"{corpus}\n{extra}"
        if not term_is_attested(target, corpus):
            continue
        if normalize_span(source) == normalize_span(target) and not source.isupper():
            continue
        try:
            confidence = float(row.get("confidence") or 0.7)
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = min(0.92, max(0.45, confidence))
        grounded.append(
            {
                "source_term": source,
                "target_term": target,
                "target_lang": target_lang,
                "confidence": confidence,
                "target_evidence": _MULTI_SPACE.sub(" ", extra).strip()[:240],
            }
        )
    return grounded


def _openai_json(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    from openai import OpenAI

    from app.routes.ai_documents.helpers import _coerce_json_object, _openai_chat_completions_create

    key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("openai_unavailable")
    model = (
        current_app.config.get("TRANSLATION_GLOSSARY_LLM_MODEL")
        or current_app.config.get("AI_QUERY_REWRITE_MODEL")
        or current_app.config.get("OPENAI_QUERY_PLANNER_MODEL")
        or "gpt-4o-mini"
    )
    client = OpenAI(api_key=key, timeout=90)
    kwargs: Dict[str, Any] = {
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 1800,
    }
    response = _openai_chat_completions_create(client, model_name=model, **kwargs)
    content = ""
    try:
        content = response.choices[0].message.content or ""
    except Exception:
        logger.debug("glossary LLM empty response", exc_info=True)
    return _coerce_json_object(content) or {}


def _chunk_batches(chunks: Sequence[Any], *, max_chars: int = 10000) -> List[List[Any]]:
    batches: List[List[Any]] = []
    current: List[Any] = []
    size = 0
    for chunk in chunks:
        text = (getattr(chunk, "content", None) or "").strip()
        if len(text) < 40:
            continue
        if current and size + len(text) > max_chars:
            batches.append(current)
            current = []
            size = 0
        current.append(chunk)
        size += len(text)
    if current:
        batches.append(current)
    return batches[:4]


def _format_extract_batch(chunks: Sequence[Any]) -> str:
    parts = []
    for chunk in chunks:
        page = getattr(chunk, "page_number", None) or "?"
        text = _MULTI_SPACE.sub(" ", (getattr(chunk, "content", None) or "").strip())[:1600]
        parts.append(f"[page {page}]\n{text}")
    return "\n\n".join(parts)


def extract_source_terms_from_chunks(chunks: Sequence[Any], *, cap: int = 20) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    for batch in _chunk_batches(chunks):
        blob = _format_extract_batch(batch)
        if not blob.strip():
            continue
        payload = _openai_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract official humanitarian / IFRC terminology from the excerpts.\n"
                        "Keep short glossary heads (1-8 words): institution names, programme names, "
                        "principles, goals, recurring technical terms.\n"
                        "Skip authors, page labels, copyright lines, and full sentences.\n"
                        "Each term MUST appear verbatim in the excerpts. Copy a short evidence span "
                        "that contains the term.\n"
                        "Return JSON only: {\"terms\": [{\"term\": \"\", \"evidence\": \"\", "
                        "\"tier\": \"must|preferred\"}]}\n"
                        "At most 8 terms. If none, return {\"terms\": []}."
                    ),
                },
                {"role": "user", "content": blob},
            ]
        )
        collected.extend(payload.get("terms") or [])
    # Keep only terms attested in the source batches we actually sent.
    corpus = "\n".join((getattr(c, "content", None) or "") for c in chunks)
    attested = []
    for row in collected:
        term = usable_glossary_term(str(row.get("term") or ""))
        evidence = str(row.get("evidence") or "")
        if not term:
            continue
        if not term_is_attested(term, corpus):
            continue
        if evidence and not term_is_attested(term, evidence) and not term_is_attested(term, corpus):
            continue
        attested.append({"term": term, "evidence": evidence, "tier": row.get("tier") or "preferred"})
    return dedupe_source_terms(attested, cap=cap)


def retrieve_target_excerpts(
    term: str,
    evidence: str,
    target_document_ids: Sequence[int],
    *,
    top_k: int = 3,
) -> Tuple[str, List[Dict[str, Any]]]:
    from app.services.ai.documents.vector_store import AIVectorStore, VectorStoreError

    hits: List[Dict[str, Any]] = []
    query = " ".join(part for part in (term, evidence) if part).strip() or term
    store = AIVectorStore()
    for doc_id in target_document_ids:
        try:
            hits.extend(
                store.search_similar(
                    query_text=query,
                    top_k=top_k,
                    filters={"document_id": int(doc_id)},
                    user_role="system_manager",
                )
            )
        except VectorStoreError:
            logger.info("glossary LLM vector retrieve failed for document %s", doc_id, exc_info=True)
        except Exception:
            logger.info("glossary LLM vector retrieve error for document %s", doc_id, exc_info=True)
    hits.sort(key=lambda h: float(h.get("similarity_score") or 0), reverse=True)
    seen: Set[int] = set()
    unique = []
    for hit in hits:
        cid = hit.get("chunk_id")
        if cid in seen:
            continue
        seen.add(cid)
        unique.append(hit)
        if len(unique) >= top_k:
            break
    excerpts = []
    for hit in unique:
        page = hit.get("page_number") or "?"
        text = _MULTI_SPACE.sub(" ", (hit.get("content") or "").strip())[:700]
        if text:
            excerpts.append(f"[page {page}] {text}")
    return "\n".join(excerpts), unique


def pair_terms_for_language(
    terms: Sequence[Dict[str, Any]],
    excerpts_by_source: Dict[str, str],
    *,
    target_lang: str,
) -> List[Dict[str, Any]]:
    if not terms:
        return []
    blocks = []
    for row in terms:
        term = row["term"]
        excerpts = excerpts_by_source.get(term) or ""
        if not excerpts.strip():
            continue
        blocks.append(
            f"SOURCE: {term}\nEN_EVIDENCE: {row.get('evidence') or ''}\n"
            f"TARGET_EXCERPTS ({target_lang}):\n{excerpts}"
        )
    if not blocks:
        return []
    payload = _openai_json(
        [
            {
                "role": "system",
                "content": (
                    f"Find the official {target_lang} equivalent of each English glossary term.\n"
                    "Use ONLY wording that appears in TARGET_EXCERPTS. Do not translate freely.\n"
                    "If the equivalent is not attested, omit that term.\n"
                    "target_term must be a short phrase (not a paragraph).\n"
                    "Return JSON only: {\"pairs\": [{\"source_term\": \"\", \"target_term\": \"\", "
                    "\"target_evidence\": \"\", \"confidence\": 0.0}]}"
                ),
            },
            {"role": "user", "content": "\n\n".join(blocks)},
        ]
    )
    keyed = {normalize_span(k): v for k, v in excerpts_by_source.items()}
    keyed.update(excerpts_by_source)
    return ground_pairs(payload.get("pairs") or [], keyed, target_lang=target_lang)


def mine_llm_pairs(
    by_lang: Dict[str, List[Any]],
    already: Set[tuple],
    rejected: Set[tuple],
    remaining: int,
    *,
    chunks_for,
) -> Tuple[int, str]:
    """Extract English terms, retrieve target evidence, persist grounded pairs."""
    from app.models.translation_quality import TranslationGlossaryCandidate
    from app.extensions import db

    if remaining <= 0:
        return 0, ""
    en_docs = by_lang.get("en") or []
    if not en_docs:
        return 0, "no_english_source"
    target_langs = [lang for lang in by_lang if lang != "en" and by_lang[lang]]
    if not target_langs:
        return 0, "same_language"

    key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        return 0, "openai_unavailable"

    en_chunks = chunks_for([d.id for d in en_docs])
    try:
        source_terms = extract_source_terms_from_chunks(en_chunks, cap=min(20, remaining))
    except RuntimeError as exc:
        if "openai_unavailable" in str(exc):
            return 0, "openai_unavailable"
        raise
    except Exception:
        logger.exception("glossary LLM extract failed")
        return 0, "llm_extract_failed"

    if not source_terms:
        return 0, "llm_no_source_terms"

    created = 0
    for lang in target_langs:
        if created >= remaining:
            break
        target_ids = [int(d.id) for d in by_lang[lang]]
        excerpts_by_source: Dict[str, str] = {}
        for row in source_terms:
            text, _hits = retrieve_target_excerpts(row["term"], row.get("evidence") or "", target_ids)
            if text:
                excerpts_by_source[row["term"]] = text
                excerpts_by_source[normalize_span(row["term"])] = text
        try:
            pairs = pair_terms_for_language(source_terms, excerpts_by_source, target_lang=lang)
        except Exception:
            logger.exception("glossary LLM pair failed for %s", lang)
            continue
        for pair in pairs:
            if created >= remaining:
                break
            key_existing = (pair["source_term"].lower(), lang)
            if key_existing in already:
                continue
            if (pair["source_term"].lower(), pair["target_term"].lower(), lang) in rejected:
                continue
            existing = TranslationGlossaryCandidate.query.filter_by(
                source_term=pair["source_term"],
                target_lang=lang,
                status="pending",
            ).first()
            if existing:
                existing.occurrence_count = int(existing.occurrence_count or 1) + 1
                if existing.extractor == "llm_pair" and not existing.target_term:
                    existing.target_term = pair["target_term"]
                continue
            src_row = next((t for t in source_terms if t["term"] == pair["source_term"]), {})
            db.session.add(
                TranslationGlossaryCandidate(
                    source_term=pair["source_term"],
                    target_term=pair["target_term"],
                    source_lang="en",
                    target_lang=lang,
                    extractor="llm_pair",
                    confidence=pair["confidence"],
                    proposed_tier=src_row.get("tier") or "preferred",
                    status="pending",
                    evidence={
                        "en_evidence": src_row.get("evidence") or "",
                        "target_evidence": pair.get("target_evidence") or "",
                        "note": "Grounded LLM pair: target wording attested in retrieved target-language chunks.",
                    },
                    occurrence_count=1,
                    example_sentences=[
                        src_row.get("evidence") or "",
                        pair.get("target_evidence") or "",
                    ],
                )
            )
            already.add(key_existing)
            created += 1

    if created == 0:
        return 0, "llm_no_grounded_pairs"
    return created, ""
