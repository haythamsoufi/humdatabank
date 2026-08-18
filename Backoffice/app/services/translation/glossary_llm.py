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


def _has_rtl(text: str) -> bool:
    # Quick check: Arabic/Hebrew Unicode blocks
    return any("\u0600" <= ch <= "\u06ff" or "\u0590" <= ch <= "\u05ff" for ch in text)


def term_is_attested(term: str, corpus: str) -> bool:
    needle = normalize_span(term)
    hay = normalize_span(corpus)
    if len(needle) < 2 or len(hay) < 2:
        return False
    if needle in hay:
        return True
    # For RTL scripts, allow partial-token match: all words ≥4 chars of needle appear in hay.
    if _has_rtl(needle):
        words = [w for w in needle.split() if len(w) >= 4]
        return bool(words) and all(w in hay for w in words)
    return False


def classify_against_glossary(
    source: str,
    target: str,
    lang: str,
    glossary: Dict[tuple, str],
) -> str:
    """Return 'new', 'same', or 'conflict' versus an approved glossary map."""
    official = glossary.get(((source or "").strip().lower(), lang))
    if not official:
        return "new"
    if normalize_span(official) == normalize_span(target or ""):
        return "same"
    return "conflict"


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


def _openai_json(messages: List[Dict[str, str]], *, max_tokens: int = 2400) -> Dict[str, Any]:
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
    client = OpenAI(api_key=key, timeout=120)
    kwargs: Dict[str, Any] = {
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_tokens,
    }
    response = _openai_chat_completions_create(client, model_name=model, **kwargs)
    content = ""
    try:
        content = response.choices[0].message.content or ""
    except Exception:
        logger.debug("glossary LLM empty response", exc_info=True)
    return _coerce_json_object(content) or {}


def _chunk_batches(chunks: Sequence[Any], *, max_chars: int = 12000, max_batches: int = 10) -> List[List[Any]]:
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
    return batches[:max_batches]


def _format_extract_batch(chunks: Sequence[Any]) -> str:
    parts = []
    for chunk in chunks:
        page = getattr(chunk, "page_number", None) or "?"
        text = _MULTI_SPACE.sub(" ", (getattr(chunk, "content", None) or "").strip())[:1600]
        parts.append(f"[page {page}]\n{text}")
    return "\n\n".join(parts)


_EXTRACT_SYSTEM = (
    "Extract official humanitarian / IFRC terminology from the document excerpts.\n"
    "Identify short, reusable glossary heads (1-8 words): programme names, institutional names, "
    "technical terms, Fundamental Principles, strategic goals, approaches.\n"
    "Skip: author names, page labels, copyright lines, full sentences, generic words (people, change, data).\n"
    "Each term MUST appear verbatim in the excerpts. Copy a short evidence span that contains it.\n"
    "tier = 'must' for proper-name terms (institution names, named programmes), 'preferred' otherwise.\n"
    "Return JSON only: {\"terms\": [{\"term\": \"\", \"evidence\": \"\", \"tier\": \"must|preferred\"}]}\n"
    "At most 15 terms per call. If none, return {\"terms\": []}."
)


def extract_source_terms_from_chunks(chunks: Sequence[Any], *, cap: int = 50) -> List[Dict[str, Any]]:
    corpus = "\n".join((getattr(c, "content", None) or "") for c in chunks)
    collected: List[Dict[str, Any]] = []
    for batch in _chunk_batches(chunks):
        blob = _format_extract_batch(batch)
        if not blob.strip():
            continue
        payload = _openai_json(
            [
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": blob},
            ],
            max_tokens=2400,
        )
        collected.extend(payload.get("terms") or [])
    attested = []
    for row in collected:
        term = usable_glossary_term(str(row.get("term") or ""))
        evidence = str(row.get("evidence") or "")
        if not term:
            continue
        if not term_is_attested(term, corpus):
            continue
        attested.append({"term": term, "evidence": evidence, "tier": row.get("tier") or "preferred"})
    return dedupe_source_terms(attested, cap=cap)


def retrieve_target_excerpts(
    term: str,
    evidence: str,
    target_document_ids: Sequence[int],
    *,
    top_k: int = 5,
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
        text = _MULTI_SPACE.sub(" ", (hit.get("content") or "").strip())[:800]
        if text:
            excerpts.append(f"[page {page}] {text}")
    return "\n".join(excerpts), unique


_PAIR_SYSTEM = (
    "Find the official target-language equivalent of each English glossary term.\n"
    "Use ONLY wording that appears verbatim in TARGET_EXCERPTS. Do not translate freely.\n"
    "target_term must be a short phrase (1-10 words), NOT a full sentence.\n"
    "Copy a short target_evidence span (≤ 30 words) that contains the target_term.\n"
    "Omit any term whose equivalent is not found in TARGET_EXCERPTS.\n"
    "Return JSON only: {\"pairs\": [{\"source_term\": \"\", \"target_term\": \"\", "
    "\"target_evidence\": \"\", \"confidence\": 0.0}]}"
)


def pair_terms_for_language(
    terms: Sequence[Dict[str, Any]],
    excerpts_by_source: Dict[str, str],
    *,
    target_lang: str,
    batch_size: int = 8,
) -> List[Dict[str, Any]]:
    if not terms:
        return []
    # Build blocks only for terms that have retrieved excerpts.
    term_blocks: List[Tuple[str, str]] = []
    for row in terms:
        term = row["term"]
        excerpts = excerpts_by_source.get(term) or excerpts_by_source.get(normalize_span(term)) or ""
        if not excerpts.strip():
            continue
        block = (
            f"SOURCE: {term}\n"
            f"EN_EVIDENCE: {(row.get('evidence') or '')[:240]}\n"
            f"TARGET_EXCERPTS ({target_lang}):\n{excerpts}"
        )
        term_blocks.append((term, block))

    if not term_blocks:
        return []

    keyed = {normalize_span(k): v for k, v in excerpts_by_source.items()}
    keyed.update(excerpts_by_source)

    all_pairs: List[Dict[str, Any]] = []
    for i in range(0, len(term_blocks), batch_size):
        sub = term_blocks[i : i + batch_size]
        payload = _openai_json(
            [
                {"role": "system", "content": f"Target language: {target_lang}.\n{_PAIR_SYSTEM}"},
                {"role": "user", "content": "\n\n".join(block for _, block in sub)},
            ],
            max_tokens=2400,
        )
        all_pairs.extend(ground_pairs(payload.get("pairs") or [], keyed, target_lang=target_lang))

    return all_pairs


def mine_llm_pairs(
    by_lang: Dict[str, List[Any]],
    already: Dict[tuple, str],
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
    per_lang_cap = max(15, remaining // max(1, len(target_langs)))
    source_cap = min(50, per_lang_cap * len(target_langs))
    try:
        source_terms = extract_source_terms_from_chunks(en_chunks, cap=source_cap)
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
            overlap = classify_against_glossary(
                pair["source_term"], pair["target_term"], lang, already
            )
            if overlap == "same":
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
            evidence = {
                "en_evidence": src_row.get("evidence") or "",
                "target_evidence": pair.get("target_evidence") or "",
                "note": "Grounded LLM pair: target wording attested in retrieved target-language chunks.",
            }
            if overlap == "conflict":
                evidence["conflict"] = True
                evidence["official_term"] = already.get(key_existing) or ""
                evidence["note"] = (
                    "Document proposes a different form than the approved glossary. "
                    "Accept replaces the official term."
                )
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
                    evidence=evidence,
                    occurrence_count=1,
                    example_sentences=[
                        src_row.get("evidence") or "",
                        pair.get("target_evidence") or "",
                    ],
                )
            )
            already[key_existing] = pair["target_term"]
            created += 1

    if created == 0:
        return 0, "llm_no_grounded_pairs"
    return created, ""
