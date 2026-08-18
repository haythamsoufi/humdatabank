"""Mine glossary candidates from selected AI Knowledge Base documents."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from flask_login import current_user

from app.extensions import db
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

# "Cash and Voucher Assistance (CVA)" and "CVA (Cash and Voucher Assistance)".
# Do not let the expansion cross a newline — PDF chunks are full of title-case noise.
_ACRONYM_EXPANSION = re.compile(
    r"\b([A-Z][A-Za-z][\w&/' -]{2,80}?)\s+\(([A-Z][A-Z0-9]{1,12})\)"
)
_ACRONYM_FIRST = re.compile(
    r"\b([A-Z][A-Z0-9]{1,12})\s+\(([A-Z][A-Za-z][\w&/' -]{2,80}?)\)"
)
_FALSE_ACRONYMS = {
    "AND", "ARE", "FOR", "FROM", "NOT", "PAGE", "THAT", "THE", "THIS", "WITH", "YOU",
}

_AUTHORITATIVE_ORGS = ("ifrc", "international federation", "secretariat")
_AUTHORITATIVE_CATEGORIES = ("policy", "guideline", "manual", "strategic_plan", "country_plan")


def _trust_weight(doc) -> float:
    org = (getattr(doc, "source_organization", None) or "").lower()
    cat = (getattr(doc, "document_category", None) or "").lower()
    score = 1.0
    if any(k in org for k in _AUTHORITATIVE_ORGS):
        score += 1.5
    if cat in _AUTHORITATIVE_CATEGORIES:
        score += 1.0
    return score


def _chunks_for(doc_ids: List[int]) -> List[Any]:
    from app.models.embeddings import AIDocumentChunk

    if not doc_ids:
        return []
    return (
        AIDocumentChunk.query.filter(AIDocumentChunk.document_id.in_(doc_ids))
        .order_by(AIDocumentChunk.document_id.asc(), AIDocumentChunk.id.asc())
        .all()
    )


def _usable_acronym_hit(expansion: str, acronym: str, sentence: str) -> Optional[Dict[str, str]]:
    """Keep only short bilingual-looking acronym expansions, not page headers or sentences."""
    if "\n" in (expansion or "") or "\r" in (expansion or ""):
        return None
    acr = (acronym or "").strip()
    exp = " ".join((expansion or "").split())
    if not (2 <= len(acr) <= 8 and acr.isupper() and acr.isalnum()):
        return None
    if acr in _FALSE_ACRONYMS:
        return None
    words = exp.split()
    if not (2 <= len(words) <= 12):
        return None
    if len(exp) > 100:
        return None
    if any(ch in exp for ch in "[]{}<>"):
        return None
    if exp.lower().startswith("page "):
        return None
    if not all(w[0].isalpha() for w in words):
        return None
    return {
        "expansion": exp,
        "acronym": acr,
        "sentence": " ".join((sentence or "").split()),
    }


def _extract_acronyms(text: str) -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    if not text:
        return found
    for m in _ACRONYM_EXPANSION.finditer(text):
        hit = _usable_acronym_hit(m.group(1), m.group(2), m.group(0))
        if hit:
            found.append(hit)
    for m in _ACRONYM_FIRST.finditer(text):
        hit = _usable_acronym_hit(m.group(2), m.group(1), m.group(0))
        if hit:
            found.append(hit)
    return found


def _existing_rejected() -> Set[tuple]:
    from app.models.translation_quality import TranslationGlossaryCandidate

    rows = TranslationGlossaryCandidate.query.filter_by(status="rejected").all()
    return {(r.source_term.lower(), r.target_term.lower(), r.target_lang) for r in rows}


def _existing_glossary() -> Dict[Tuple[str, str], str]:
    from app.models.translation_quality import TranslationGlossaryTerm

    rows = TranslationGlossaryTerm.query.filter_by(is_active=True).all()
    return {(r.source_term.lower(), r.target_lang): r.target_term for r in rows}


def mine_selected_documents(document_ids: List[int], *, cap: int = 150) -> Dict[str, int]:
    """Run extractors on selected completed documents. Everything is a candidate."""
    from app.models.embeddings import AIDocument
    from app.models.enums import AIDocumentProcessingStatusValue
    from app.models.translation_quality import TranslationGlossaryCandidate
    from app.services.translation.glossary_llm import classify_against_glossary

    ids = [int(x) for x in (document_ids or []) if x]
    raw_docs = AIDocument.query.filter(AIDocument.id.in_(ids)).all() if ids else []
    completed = AIDocumentProcessingStatusValue.completed
    docs = [
        d
        for d in raw_docs
        if d.processing_status == completed
        or getattr(d.processing_status, "value", None) == completed.value
        or str(d.processing_status) == completed.value
    ]
    skipped_not_completed = max(0, len(ids) - len(docs))
    if not docs:
        return {
            "candidates": 0,
            "documents": 0,
            "selected": len(ids),
            "skipped_not_completed": skipped_not_completed,
        }

    by_lang: Dict[str, List[Any]] = defaultdict(list)
    for d in docs:
        lang = (d.document_language or "en").lower()[:2]
        by_lang[lang].append(d)

    rejected = _existing_rejected()
    already = _existing_glossary()
    created = 0

    # Extractor 1: acronym-expansion join on the acronym key.
    expansions: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for lang, lang_docs in by_lang.items():
        chunks = _chunks_for([d.id for d in lang_docs])
        doc_by_id = {d.id: d for d in lang_docs}
        for ch in chunks:
            doc = doc_by_id.get(ch.document_id)
            if not doc:
                continue
            for hit in _extract_acronyms(ch.content or ""):
                expansions[hit["acronym"]][lang].append(
                    {
                        "expansion": hit["expansion"],
                        "sentence": hit["sentence"],
                        "title": doc.title,
                        "date": str(doc.document_date or ""),
                        "page": getattr(ch, "page_number", None),
                        "trust": _trust_weight(doc),
                    }
                )

    en_keys = set(expansions.keys())
    for acronym in en_keys:
        en_hits = expansions[acronym].get("en") or []
        if not en_hits:
            continue
        en_expansion = max(en_hits, key=lambda h: h["trust"])["expansion"]
        for lang, hits in expansions[acronym].items():
            if lang == "en" or not hits:
                continue
            target_expansion = max(hits, key=lambda h: h["trust"])["expansion"]
            key = (en_expansion.lower(), lang)
            overlap = classify_against_glossary(en_expansion, target_expansion, lang, already)
            if overlap == "same":
                continue
            if (en_expansion.lower(), target_expansion.lower(), lang) in rejected:
                continue
            existing = TranslationGlossaryCandidate.query.filter_by(
                source_term=en_expansion,
                target_term=target_expansion,
                target_lang=lang,
                extractor="acronym_join",
                status="pending",
            ).first()
            if existing:
                existing.occurrence_count = int(existing.occurrence_count or 1) + len(hits)
                continue
            evidence = {
                "acronym": acronym,
                "documents": [
                    {"title": h["title"], "date": h["date"], "page": h["page"]}
                    for h in (en_hits[:2] + hits[:2])
                ],
            }
            if overlap == "conflict":
                evidence["conflict"] = True
                evidence["official_term"] = already.get(key) or ""
                evidence["note"] = "Document form differs from the approved glossary."
            db.session.add(
                TranslationGlossaryCandidate(
                    source_term=en_expansion,
                    target_term=target_expansion,
                    source_lang="en",
                    target_lang=lang,
                    extractor="acronym_join",
                    confidence=min(0.95, 0.7 + 0.05 * len(hits)),
                    proposed_tier="must",
                    status="pending",
                    evidence=evidence,
                    occurrence_count=len(en_hits) + len(hits),
                    example_sentences=[h["sentence"] for h in (en_hits[:2] + hits[:2])],
                )
            )
            created += 1
            if created >= cap:
                break
        if created >= cap:
            break

    # Extractor 2: frequency / conflict vs approved glossary forms in target-language docs.
    if created < cap:
        created += _mine_frequency_conflicts(by_lang, already, rejected, cap - created)

    llm_reason = ""
    if created < cap:
        from app.services.translation.glossary_llm import mine_llm_pairs

        llm_created, llm_reason = mine_llm_pairs(
            by_lang, already, rejected, cap - created, chunks_for=_chunks_for
        )
        created += llm_created

    db.session.commit()
    langs = sorted(by_lang.keys())
    reason = ""
    if created == 0:
        if len(langs) < 2:
            reason = "same_language"
        else:
            reason = llm_reason or "no_shared_acronyms"
    return {
        "candidates": created,
        "documents": len(docs),
        "selected": len(ids),
        "skipped_not_completed": skipped_not_completed,
        "languages": langs,
        "reason": reason,
    }


def _mine_frequency_conflicts(
    by_lang: Dict[str, List[Any]],
    already: Dict[Tuple[str, str], str],
    rejected: Set[tuple],
    remaining: int,
) -> int:
    from app.models.translation_quality import TranslationGlossaryCandidate, TranslationGlossaryTerm

    created = 0
    terms = TranslationGlossaryTerm.query.filter_by(is_active=True, source_lang="en").all()
    for term in terms:
        lang_docs = by_lang.get(term.target_lang) or []
        if not lang_docs:
            continue
        chunks = _chunks_for([d.id for d in lang_docs])
        blob = "\n".join((c.content or "") for c in chunks)
        if not blob:
            continue
        approved = term.target_term
        count_approved = len(re.findall(re.escape(approved), blob, flags=re.IGNORECASE))
        # Surface when the English source term appears but the approved target does not.
        source_mentions = len(re.findall(re.escape(term.source_term), blob, flags=re.IGNORECASE))
        if source_mentions >= 3 and count_approved == 0:
            db.session.add(
                TranslationGlossaryCandidate(
                    source_term=term.source_term,
                    target_term=approved,
                    source_lang="en",
                    target_lang=term.target_lang,
                    extractor="frequency_conflict",
                    confidence=0.55,
                    proposed_tier=term.tier or "must",
                    status="pending",
                    evidence={
                        "note": "Source term appears in target-language documents but the approved target form does not.",
                        "source_mentions": source_mentions,
                        "approved_mentions": count_approved,
                    },
                    occurrence_count=source_mentions,
                    example_sentences=[],
                )
            )
            created += 1
            if created >= remaining:
                break
    return created


def decide_candidate(
    candidate_id: int,
    *,
    accept: bool,
    tier: Optional[str] = None,
    source_term: Optional[str] = None,
    target_term: Optional[str] = None,
    commit: bool = True,
) -> bool:
    from app.models.translation_quality import TranslationGlossaryCandidate, TranslationGlossaryTerm

    row = TranslationGlossaryCandidate.query.get(int(candidate_id))
    if row is None or row.status != "pending":
        return False
    if accept:
        src = " ".join((source_term if source_term is not None else row.source_term or "").split())
        tgt = " ".join((target_term if target_term is not None else row.target_term or "").split())
        if not src or not tgt:
            return False
        row.source_term = src[:500]
        row.target_term = tgt[:500]
    row.status = "accepted" if accept else "rejected"
    row.reviewed_at = utcnow()
    try:
        if current_user and getattr(current_user, "is_authenticated", False):
            row.reviewer_user_id = int(current_user.id)
    except Exception:
        logger.debug("candidate reviewer id skipped", exc_info=True)
    if accept:
        existing = TranslationGlossaryTerm.query.filter_by(
            source_term=row.source_term,
            source_lang=row.source_lang,
            target_lang=row.target_lang,
        ).first()
        if existing is None:
            db.session.add(
                TranslationGlossaryTerm(
                    source_term=row.source_term,
                    source_lang=row.source_lang,
                    target_term=row.target_term,
                    target_lang=row.target_lang,
                    tier=tier or row.proposed_tier or "preferred",
                    origin="document_mining",
                    is_active=True,
                )
            )
        else:
            existing.target_term = row.target_term
            existing.tier = tier or row.proposed_tier or existing.tier
            existing.is_active = True
    if commit:
        db.session.commit()
    return True


def decide_candidates_bulk(items: List[Any], *, accept: bool) -> Dict[str, Any]:
    """Accept or reject many pending candidates in one transaction."""
    updated = 0
    skipped = 0
    for raw in items or []:
        payload = raw if isinstance(raw, dict) else {"id": raw}
        try:
            cid = int(payload.get("id"))
        except (TypeError, ValueError):
            skipped += 1
            continue
        ok = decide_candidate(
            cid,
            accept=accept,
            tier=payload.get("tier") or payload.get("proposed_tier"),
            source_term=payload.get("source_term"),
            target_term=payload.get("target_term"),
            commit=False,
        )
        if ok:
            updated += 1
        else:
            skipped += 1
    db.session.commit()
    return {"updated": updated, "skipped": skipped, "accepted": bool(accept)}
