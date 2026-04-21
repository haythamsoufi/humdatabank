"""
IFRC terminology helpers for AI retrieval/classification.

Combines:
- DB glossary (preferred source)
- Curated fallback glossary (acronyms + canonical phrases)
- Indicator Bank-derived terms (indicator names, sector/subsector labels)
"""

from __future__ import annotations

import logging
import re
import time
import threading
from typing import Any, Dict, List, Set, Tuple, Optional

from flask import current_app
from sqlalchemy import text


_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 600
_TERMS_CACHE: Dict[str, Any] = {
    "expires_at": 0.0,
    "concept_aliases": {},
}
_EMBED_SYNC_CACHE: Dict[str, float] = {"last_sync": 0.0}
_ACRONYM_CONFIRM_REGEX: Dict[str, List[str]] = {
    "cea": [r"\bcea\b", r"\bcommunity\s+engagement\s+and\s+accountability\b"],
    "pgi": [r"\bpgi\b", r"\bprotection,\s*gender\s+and\s+inclusion\b", r"\bprotection\s+gender\s+and\s+inclusion\b"],
}


# Curated IFRC terms. Keep this compact and high-signal.
_STATIC_CONCEPT_ALIASES: Dict[str, List[str]] = {
    "cea": [
        "cea",
        "community engagement and accountability",
        "community engagement",
        "accountability to affected populations",
        "aap",
        "feedback mechanism",
        "community feedback",
        "two-way communication",
    ],
    "cash": [
        "cash",
        "cash assistance",
        "cash transfer",
        "cash and voucher assistance",
        "voucher assistance",
        "cva",
    ],
    "livelihoods": [
        "livelihoods",
        "livelihood",
        "economic security",
        "income generation",
        "food security",
        "economic recovery",
        "economic inclusion",
        "economic empowerment",
        "vocational training",
        "skills training",
        "cash for work",
        "agricultural livelihoods",
        "income-generating activities",
        "market-based programming",
        "employment",
        "enterprise development",
    ],
    "social_protection": [
        "social protection",
        "social assistance",
        "social safety net",
        "social welfare",
        "social insurance",
        "social inclusion",
        "safety net",
        "social cohesion",
        "social services",
        "auxiliary role",
        "national society auxiliary role",
    ],
    "pgi": [
        "pgi",
        "protection, gender and inclusion",
        "gender and inclusion",
    ],
}


def _norm(text: Any) -> str:
    s = str(text or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _clean_alias(alias: str) -> str:
    a = _norm(alias)
    if not a:
        return ""
    # Keep punctuation that may be meaningful for acronyms/codes.
    a = re.sub(r"[^\w\s\-/&(),.]", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    return a


def _regex_word_match(haystack: str, phrase: str) -> bool:
    p = str(phrase or "").strip()
    if not p:
        return False
    esc = re.escape(p).replace(r"\ ", r"\s+")
    try:
        return bool(re.search(rf"\b{esc}\b", haystack, flags=re.IGNORECASE))
    except Exception as e:
        logging.getLogger(__name__).debug("_regex_word_match: %s", e)
        return False


def _indicator_relevant_to_concept(name: str, definition: str, seed_terms: List[str]) -> bool:
    """
    Conservative concept match for Indicator Bank enrichment.
    """
    n = _norm(name)
    d = _norm(definition)
    if not (n or d):
        return False
    # Require at least one seed term as a bounded phrase in name OR definition.
    for t in (seed_terms or [])[:40]:
        term = _norm(t)
        if not term:
            continue
        if _regex_word_match(n, term) or _regex_word_match(d, term):
            return True
    return False


def _dedupe_aliases(items: List[str], max_items: int = 120) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for it in items:
        c = _clean_alias(it)
        if not c or c in seen:
            continue
        # Avoid excessively short/noisy fragments.
        if len(c) <= 1:
            continue
        seen.add(c)
        out.append(c)
        if len(out) >= max_items:
            break
    return out


def _build_concept_aliases_from_indicator_bank() -> Dict[str, List[str]]:
    """
    Build concept -> aliases from static glossary + Indicator Bank signals.
    """
    from app.models.indicator_bank import IndicatorBank, Sector, SubSector

    concept_aliases: Dict[str, List[str]] = {k: list(v) for k, v in _STATIC_CONCEPT_ALIASES.items()}
    concept_static = {k: [_norm(v) for v in vals] for k, vals in _STATIC_CONCEPT_ALIASES.items()}

    # Preload sector/subsector labels to avoid N+1 lookups.
    sector_names = {int(s.id): str(s.name or "").strip() for s in Sector.query.all() if getattr(s, "id", None)}
    subsector_names = {int(s.id): str(s.name or "").strip() for s in SubSector.query.all() if getattr(s, "id", None)}

    indicators = (
        IndicatorBank.query.filter(IndicatorBank.archived == False)
        .with_entities(
            IndicatorBank.id,
            IndicatorBank.name,
            IndicatorBank.definition,
            IndicatorBank.fdrs_kpi_code,
            IndicatorBank.sector,
            IndicatorBank.sub_sector,
        )
        .all()
    )

    for row in indicators or []:
        name = str(getattr(row, "name", "") or "").strip()
        definition = str(getattr(row, "definition", "") or "").strip()
        kpi = str(getattr(row, "fdrs_kpi_code", "") or "").strip()
        sector_json = getattr(row, "sector", None) or {}
        subsector_json = getattr(row, "sub_sector", None) or {}
        blob = _norm(f"{name} {definition}")
        if not blob:
            continue

        for concept, static_terms in concept_static.items():
            if not any((t and t in blob) for t in static_terms):
                continue
            # Add indicator name/code as concept aliases.
            if name:
                concept_aliases.setdefault(concept, []).append(name)
            if kpi:
                concept_aliases.setdefault(concept, []).append(kpi)

            # Add linked sector/subsector names (often contain IFRC terminology context).
            if isinstance(sector_json, dict):
                for lvl in ("primary", "secondary", "tertiary"):
                    sid = sector_json.get(lvl)
                    try:
                        if sid is not None and int(sid) in sector_names:
                            concept_aliases.setdefault(concept, []).append(sector_names[int(sid)])
                    except Exception as e:
                        logging.getLogger(__name__).debug("sector alias lookup: %s", e)
                        continue
            if isinstance(subsector_json, dict):
                for lvl in ("primary", "secondary", "tertiary"):
                    ssid = subsector_json.get(lvl)
                    try:
                        if ssid is not None and int(ssid) in subsector_names:
                            concept_aliases.setdefault(concept, []).append(subsector_names[int(ssid)])
                    except Exception as e:
                        logging.getLogger(__name__).debug("subsector alias lookup: %s", e)
                        continue

    # Final cleanup and dedupe.
    for concept in list(concept_aliases.keys()):
        concept_aliases[concept] = _dedupe_aliases(concept_aliases.get(concept) or [])
    return concept_aliases


def _build_concept_aliases_from_indicator_bank_with_seed(
    seed_aliases: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """
    Enrich an existing concept alias map with Indicator Bank terms.
    """
    from app.models.indicator_bank import IndicatorBank, Sector, SubSector

    concept_aliases: Dict[str, List[str]] = {k: list(v) for k, v in (seed_aliases or {}).items()}
    concept_seed = {k: [_norm(v) for v in vals] for k, vals in concept_aliases.items()}
    per_concept_added: Dict[str, int] = {k: 0 for k in concept_aliases.keys()}
    max_added_per_concept = int(current_app.config.get("AI_TERM_MAX_INDICATOR_ALIASES_PER_CONCEPT", 80))
    include_sector_aliases = bool(current_app.config.get("AI_TERM_INCLUDE_SECTOR_ALIASES", False))

    sector_names = {int(s.id): str(s.name or "").strip() for s in Sector.query.all() if getattr(s, "id", None)}
    subsector_names = {int(s.id): str(s.name or "").strip() for s in SubSector.query.all() if getattr(s, "id", None)}

    indicators = (
        IndicatorBank.query.filter(IndicatorBank.archived == False)
        .with_entities(
            IndicatorBank.id,
            IndicatorBank.name,
            IndicatorBank.definition,
            IndicatorBank.fdrs_kpi_code,
            IndicatorBank.sector,
            IndicatorBank.sub_sector,
        )
        .all()
    )

    for row in indicators or []:
        name = str(getattr(row, "name", "") or "").strip()
        definition = str(getattr(row, "definition", "") or "").strip()
        kpi = str(getattr(row, "fdrs_kpi_code", "") or "").strip()
        sector_json = getattr(row, "sector", None) or {}
        subsector_json = getattr(row, "sub_sector", None) or {}
        blob = _norm(f"{name} {definition}")
        if not blob:
            continue

        for concept, seed_terms in concept_seed.items():
            if per_concept_added.get(concept, 0) >= max_added_per_concept:
                continue
            if not _indicator_relevant_to_concept(name, definition, seed_terms):
                continue
            if name:
                concept_aliases.setdefault(concept, []).append(name)
                per_concept_added[concept] = int(per_concept_added.get(concept, 0) + 1)
            if kpi:
                concept_aliases.setdefault(concept, []).append(kpi)

            if include_sector_aliases:
                if isinstance(sector_json, dict):
                    for lvl in ("primary", "secondary", "tertiary"):
                        sid = sector_json.get(lvl)
                        try:
                            if sid is not None and int(sid) in sector_names:
                                concept_aliases.setdefault(concept, []).append(sector_names[int(sid)])
                        except Exception as e:
                            logging.getLogger(__name__).debug("sector alias lookup (seed): %s", e)
                            continue
                if isinstance(subsector_json, dict):
                    for lvl in ("primary", "secondary", "tertiary"):
                        ssid = subsector_json.get(lvl)
                        try:
                            if ssid is not None and int(ssid) in subsector_names:
                                concept_aliases.setdefault(concept, []).append(subsector_names[int(ssid)])
                        except Exception as e:
                            logging.getLogger(__name__).debug("subsector alias lookup (seed): %s", e)
                            continue

    for concept in list(concept_aliases.keys()):
        concept_aliases[concept] = _dedupe_aliases(concept_aliases.get(concept) or [])
    return concept_aliases


def _build_concept_aliases_from_db() -> Dict[str, List[str]]:
    """
    Load concept aliases from DB glossary tables.
    Returns {} when table/data is unavailable so caller can fallback.
    """
    from app.models.ai_terminology import AITermConcept, AITermGlossary

    concepts = (
        AITermConcept.query.filter(AITermConcept.is_active == True)
        .with_entities(AITermConcept.id, AITermConcept.concept_key, AITermConcept.display_name)
        .all()
    )
    if not concepts:
        return {}

    concept_by_id: Dict[int, str] = {}
    aliases: Dict[str, List[str]] = {}
    for c in concepts:
        cid = int(getattr(c, "id"))
        ckey = _norm(getattr(c, "concept_key", "") or "")
        display_name = str(getattr(c, "display_name", "") or "").strip()
        if not ckey:
            continue
        concept_by_id[cid] = ckey
        aliases.setdefault(ckey, []).append(ckey)
        if display_name:
            aliases.setdefault(ckey, []).append(display_name)

    rows = (
        AITermGlossary.query.filter(AITermGlossary.is_active == True)
        .with_entities(
            AITermGlossary.concept_id,
            AITermGlossary.term,
            AITermGlossary.weight,
        )
        .order_by(AITermGlossary.weight.desc(), AITermGlossary.id.asc())
        .all()
    )
    for r in rows or []:
        cid = int(getattr(r, "concept_id"))
        ckey = concept_by_id.get(cid)
        if not ckey:
            continue
        term = str(getattr(r, "term", "") or "").strip()
        if term:
            aliases.setdefault(ckey, []).append(term)

    for concept in list(aliases.keys()):
        aliases[concept] = _dedupe_aliases(aliases.get(concept) or [])
    return aliases


def _concept_text_for_embedding(concept_key: str, aliases: List[str]) -> str:
    """
    Build one multilingual-ish embedding text per concept.
    """
    concept_key = _norm(concept_key)
    vals = _dedupe_aliases(list(aliases or []), max_items=200)
    # Keep the concept key near the front to anchor the embedding.
    parts = [concept_key] if concept_key else []
    parts.extend(vals)
    return " | ".join([p for p in parts if p]).strip()


def _sync_concept_embeddings(concept_aliases: Dict[str, List[str]]) -> None:
    """
    Upsert concept embeddings for active glossary concepts.
    """
    from app.extensions import db
    from app.models.ai_terminology import AITermConcept, AITermConceptEmbedding
    from app.services.ai_embedding_service import AIEmbeddingService

    if not concept_aliases:
        return
    concepts = (
        AITermConcept.query.filter(AITermConcept.is_active == True)
        .with_entities(AITermConcept.id, AITermConcept.concept_key, AITermConcept.updated_at)
        .all()
    )
    if not concepts:
        return

    emb_service = AIEmbeddingService()
    concepts_to_embed: List[Tuple[int, str]] = []
    existing_by_cid: Dict[int, Any] = {
        int(e.concept_id): e
        for e in AITermConceptEmbedding.query.filter(
            AITermConceptEmbedding.concept_id.in_([int(c.id) for c in concepts])
        ).all()
    }

    for c in concepts:
        cid = int(getattr(c, "id"))
        ckey = _norm(getattr(c, "concept_key", "") or "")
        if not ckey:
            continue
        aliases = concept_aliases.get(ckey) or []
        if not aliases:
            continue
        txt = _concept_text_for_embedding(ckey, aliases)
        if not txt:
            continue
        existing = existing_by_cid.get(cid)
        # Re-embed if missing, text changed, model changed, or dimension changed.
        if (
            existing is None
            or str(getattr(existing, "text_embedded", "") or "").strip() != txt
            or str(getattr(existing, "model", "") or "").strip() != str(emb_service.model)
            or int(getattr(existing, "dimensions", 0) or 0) != int(emb_service.configured_dimensions)
        ):
            concepts_to_embed.append((cid, txt))

    if not concepts_to_embed:
        return

    texts = [t for _, t in concepts_to_embed]
    vectors, total_cost = emb_service.generate_embeddings_batch(texts, batch_size=64)
    cost_per = (float(total_cost) / float(len(vectors))) if vectors else 0.0
    dims = len(vectors[0]) if vectors else int(emb_service.configured_dimensions)

    for idx, (cid, txt) in enumerate(concepts_to_embed):
        if idx >= len(vectors):
            break
        vec = vectors[idx]
        existing = existing_by_cid.get(cid)
        if existing:
            existing.embedding = vec
            existing.text_embedded = txt
            existing.model = emb_service.model
            existing.dimensions = dims
            existing.generation_cost_usd = cost_per
        else:
            db.session.add(
                AITermConceptEmbedding(
                    concept_id=cid,
                    embedding=vec,
                    text_embedded=txt,
                    model=emb_service.model,
                    dimensions=dims,
                    generation_cost_usd=cost_per,
                )
            )
    db.session.commit()


def _maybe_sync_concept_embeddings(concept_aliases: Dict[str, List[str]]) -> None:
    """
    Throttled best-effort sync so request latency stays predictable.
    """
    now = time.time()
    min_interval = int(current_app.config.get("AI_TERM_EMBED_SYNC_MIN_INTERVAL_SECONDS", 600))
    with _CACHE_LOCK:
        last = float(_EMBED_SYNC_CACHE.get("last_sync") or 0.0)
        if (now - last) < float(max(30, min_interval)):
            return
        _EMBED_SYNC_CACHE["last_sync"] = now
    try:
        _sync_concept_embeddings(concept_aliases)
    except Exception as e:
        logging.getLogger(__name__).debug("_maybe_sync_concept_embeddings: %s", e)
        # Non-fatal; callers can fallback to lexical matching.
        return


def _semantic_concepts_for_query(query: str, *, top_k: int = 3, min_similarity: Optional[float] = None) -> List[str]:
    """
    Return concept keys semantically closest to the query.
    """
    from app.extensions import db
    from app.models.ai_terminology import AITermConcept, AITermConceptEmbedding
    from app.services.ai_embedding_service import AIEmbeddingService

    q = _norm(query)
    if not q:
        return []
    if min_similarity is None:
        min_similarity = float(current_app.config.get("AI_TERM_QUERY_MIN_SIMILARITY", 0.50))

    emb_service = AIEmbeddingService()
    q_emb, _ = emb_service.generate_embedding(q)
    rows = (
        db.session.query(
            AITermConcept.concept_key,
            (1 - AITermConceptEmbedding.embedding.cosine_distance(q_emb)).label("similarity"),
        )
        .join(AITermConceptEmbedding, AITermConceptEmbedding.concept_id == AITermConcept.id)
        .filter(AITermConcept.is_active == True)
        .order_by(text("similarity DESC"))
        .limit(max(1, int(top_k)))
        .all()
    )
    out: List[str] = []
    for key, sim in rows or []:
        try:
            if float(sim) >= float(min_similarity):
                out.append(_norm(key))
        except Exception as e:
            logging.getLogger(__name__).debug("_semantic_concepts_for_query similarity check: %s", e)
            continue
    return [k for k in out if k]


def get_focus_area_semantic_doc_hits(
    *,
    doc_ids: List[int],
    area_keys: List[str],
    min_similarity: Optional[float] = None,
    return_debug: bool = False,
    include_per_doc_debug: bool = True,
) -> Dict[str, Any]:
    """
    For each focus area, return doc_ids that have semantically similar chunks.
    Uses ai_term_concept_embeddings vs ai_embeddings vectors.
    """
    from app.extensions import db
    from app.models.ai_terminology import AITermConcept, AITermConceptEmbedding
    from app.models import AIEmbedding, AIDocumentChunk

    out: Dict[str, Set[int]] = {k: set() for k in area_keys}
    if not doc_ids or not area_keys:
        if return_debug:
            return {"hits_by_area": out, "debug": {"note": "No doc_ids or area_keys provided."}}
        return out
    if min_similarity is None:
        min_similarity = float(current_app.config.get("AI_TERM_DOC_MIN_SIMILARITY", 0.52))
    low_floor = float(current_app.config.get("AI_TERM_DOC_LOW_FLOOR", 0.44))
    min_chunk_hits = int(current_app.config.get("AI_TERM_DOC_MIN_CHUNK_HITS", 1))
    margin = float(current_app.config.get("AI_TERM_DOC_MARGIN", 0.05))
    high_conf = float(current_app.config.get("AI_TERM_DOC_HIGH_CONFIDENCE", 0.68))
    debug: Dict[str, Any] = {
        "config": {
            "min_similarity": float(min_similarity),
            "low_floor": float(low_floor),
            "min_chunk_hits": int(min_chunk_hits),
            "margin": float(margin),
            "high_confidence": float(high_conf),
        },
        "input": {
            "doc_count": int(len(doc_ids)),
            "area_keys": list(area_keys),
        },
        "concept_stats": {},
        "acronym_confirmation": {},
        "per_doc": {} if include_per_doc_debug else None,
    }

    concept_rows = (
        db.session.query(AITermConcept.concept_key, AITermConceptEmbedding.embedding)
        .join(AITermConceptEmbedding, AITermConceptEmbedding.concept_id == AITermConcept.id)
        .filter(AITermConcept.is_active == True, AITermConcept.concept_key.in_(area_keys))
        .all()
    )
    if not concept_rows:
        if return_debug:
            debug["note"] = "No active concept embeddings found for requested area keys."
            return {"hits_by_area": out, "debug": debug}
        return out

    # Track per-doc scores across concepts so we can apply margining.
    score_map: Dict[int, Dict[str, float]] = {}
    hit_count_map: Dict[int, Dict[str, int]] = {}
    concept_candidate_docs: Dict[str, Set[int]] = {k: set() for k in area_keys}
    logger.info("get_focus_area_semantic_doc_hits: starting cosine queries for %d concepts across %d docs",
                len(concept_rows), len(doc_ids))
    _cosine_t0 = time.time()
    for ckey, cemb in concept_rows:
        key = _norm(ckey)
        if key not in out:
            continue
        _q_start = time.time()
        rows = (
            db.session.query(
                AIDocumentChunk.document_id,
                (1 - AIEmbedding.embedding.cosine_distance(cemb)).label("similarity"),
            )
            .join(AIEmbedding, AIEmbedding.chunk_id == AIDocumentChunk.id)
            .filter(AIDocumentChunk.document_id.in_(doc_ids))
            .filter((1 - AIEmbedding.embedding.cosine_distance(cemb)) >= float(low_floor))
            .all()
        )
        logger.info("get_focus_area_semantic_doc_hits: cosine query for concept=%s done in %dms, rows=%d",
                    key, int((time.time() - _q_start) * 1000), len(rows or []))
        for r in rows or []:
            if not r or r[0] is None:
                continue
            did = int(r[0])
            sim = float(r[1] or 0.0)
            score_map.setdefault(did, {})
            hit_count_map.setdefault(did, {})
            prev = float(score_map[did].get(key) or 0.0)
            if sim > prev:
                score_map[did][key] = sim
            hit_count_map[did][key] = int(hit_count_map[did].get(key, 0) + 1)
            concept_candidate_docs.setdefault(key, set()).add(did)

    logger.info("get_focus_area_semantic_doc_hits: all cosine queries done in %dms",
                int((time.time() - _cosine_t0) * 1000))

    for k in area_keys:
        debug["concept_stats"][k] = {
            "candidate_docs_low_floor": int(len(concept_candidate_docs.get(k) or set())),
            "selected_docs": 0,
            "excluded_reasons": {
                "below_min_similarity": 0,
                "below_min_chunk_hits": 0,
                "below_margin_and_high_confidence": 0,
                "removed_by_acronym_confirmation": 0,
            },
        }

    # Apply confidence + margin gating per document/concept.
    # Docs that pass min_similarity + hits but fail margin are tracked for potential
    # lexical rescue by the caller (co-occurring concepts like cash + CEA cause
    # legitimate matches to fail the margin gate).
    margin_rejected: Dict[str, Set[int]] = {k: set() for k in area_keys}
    for did, c_scores in score_map.items():
        if not c_scores:
            continue
        items = sorted(c_scores.items(), key=lambda kv: float(kv[1]), reverse=True)
        for concept_key, score in items:
            hits = int((hit_count_map.get(did) or {}).get(concept_key, 0))
            best_other = max([float(v) for k, v in items if k != concept_key], default=0.0)
            margin_delta = float(score - best_other)
            score_ok = bool(score >= float(min_similarity))
            hits_ok = bool(hits >= int(max(1, min_chunk_hits)))
            margin_or_high_ok = bool(score >= float(high_conf) or margin_delta >= float(margin))

            if include_per_doc_debug:
                pd = debug["per_doc"].setdefault(str(did), {})
                pd[concept_key] = {
                    "score": float(score),
                    "hits": int(hits),
                    "best_other_score": float(best_other),
                    "margin_delta": float(margin_delta),
                    "score_gate_passed": bool(score_ok),
                    "hits_gate_passed": bool(hits_ok),
                    "margin_or_high_confidence_passed": bool(margin_or_high_ok),
                    "selected": False,
                }

            if not score_ok:
                debug["concept_stats"].setdefault(concept_key, {}).setdefault("excluded_reasons", {}).setdefault("below_min_similarity", 0)
                debug["concept_stats"][concept_key]["excluded_reasons"]["below_min_similarity"] += 1
                continue
            if not hits_ok:
                debug["concept_stats"].setdefault(concept_key, {}).setdefault("excluded_reasons", {}).setdefault("below_min_chunk_hits", 0)
                debug["concept_stats"][concept_key]["excluded_reasons"]["below_min_chunk_hits"] += 1
                continue
            if not margin_or_high_ok:
                debug["concept_stats"].setdefault(concept_key, {}).setdefault("excluded_reasons", {}).setdefault("below_margin_and_high_confidence", 0)
                debug["concept_stats"][concept_key]["excluded_reasons"]["below_margin_and_high_confidence"] += 1
                margin_rejected.setdefault(concept_key, set()).add(int(did))
                continue
            out.setdefault(concept_key, set()).add(int(did))
            if include_per_doc_debug:
                debug["per_doc"][str(did)][concept_key]["selected"] = True

    # Acronym lexical confirmation for ambiguous acronym concepts.
    confirm_concepts = [k for k in out.keys() if k in _ACRONYM_CONFIRM_REGEX and out.get(k)]
    for concept_key in confirm_concepts:
        candidate_docs = list(out.get(concept_key) or set())
        if not candidate_docs:
            continue
        regexes = [re.compile(p, re.IGNORECASE) for p in (_ACRONYM_CONFIRM_REGEX.get(concept_key) or [])]
        keep_docs: Set[int] = set()
        chunks = (
            db.session.query(AIDocumentChunk.document_id, AIDocumentChunk.content)
            .filter(AIDocumentChunk.document_id.in_(candidate_docs))
            .all()
        )
        for row in chunks or []:
            if not row or row[0] is None:
                continue
            did = int(row[0])
            txt = str(row[1] or "")
            if txt and any(rx.search(txt) for rx in regexes):
                keep_docs.add(did)
                if include_per_doc_debug and str(did) in (debug.get("per_doc") or {}) and concept_key in debug["per_doc"][str(did)]:
                    debug["per_doc"][str(did)][concept_key]["acronym_lexical_confirmed"] = True
            elif include_per_doc_debug and str(did) in (debug.get("per_doc") or {}) and concept_key in debug["per_doc"][str(did)]:
                debug["per_doc"][str(did)][concept_key]["acronym_lexical_confirmed"] = False
        removed = set(out.get(concept_key) or set()) - set(keep_docs)
        debug["acronym_confirmation"][concept_key] = {
            "candidate_docs": int(len(candidate_docs)),
            "kept_docs": int(len(keep_docs)),
            "removed_docs": int(len(removed)),
        }
        if removed:
            debug["concept_stats"].setdefault(concept_key, {}).setdefault("excluded_reasons", {}).setdefault("removed_by_acronym_confirmation", 0)
            debug["concept_stats"][concept_key]["excluded_reasons"]["removed_by_acronym_confirmation"] += int(len(removed))
        out[concept_key] = keep_docs
    for k in area_keys:
        debug["concept_stats"].setdefault(k, {})
        debug["concept_stats"][k]["selected_docs"] = int(len(out.get(k) or set()))

    if return_debug:
        # JSON-friendly conversion
        out_json = {k: sorted([int(x) for x in (v or set())]) for k, v in out.items()}
        margin_rejected_json = {k: sorted([int(x) for x in (v or set())]) for k, v in margin_rejected.items()}
        debug["margin_rejected_by_area"] = margin_rejected_json
        return {"hits_by_area": out_json, "margin_rejected_by_area": margin_rejected_json, "debug": debug}
    return out


def get_ifrc_concept_aliases() -> Dict[str, List[str]]:
    """
    Return cached concept aliases.
    """
    now = time.time()
    with _CACHE_LOCK:
        if (
            isinstance(_TERMS_CACHE.get("concept_aliases"), dict)
            and float(_TERMS_CACHE.get("expires_at") or 0) > now
        ):
            return dict(_TERMS_CACHE.get("concept_aliases") or {})

    built: Dict[str, List[str]]
    try:
        db_aliases = _build_concept_aliases_from_db()
    except Exception as e:
        logging.getLogger(__name__).debug("_build_concept_aliases_from_db fallback: %s", e)
        db_aliases = {}

    if db_aliases:
        try:
            built = _build_concept_aliases_from_indicator_bank_with_seed(db_aliases)
        except Exception as e:
            logging.getLogger(__name__).debug("_build_concept_aliases_from_indicator_bank_with_seed fallback: %s", e)
            built = db_aliases
    else:
        # Backward-compatible fallback when DB glossary is not set up yet.
        built = _build_concept_aliases_from_indicator_bank()

    with _CACHE_LOCK:
        _TERMS_CACHE["concept_aliases"] = built
        _TERMS_CACHE["expires_at"] = now + _CACHE_TTL_SECONDS
    # Best-effort embedding sync (throttled). Do not block aliases when this fails.
    try:
        _maybe_sync_concept_embeddings(built)
    except Exception as e:
        logging.getLogger(__name__).debug("get_ifrc_concept_aliases embed sync: %s", e)
    return dict(built)


def get_focus_area_aliases(area_key: str, *, max_aliases: int = 120) -> List[str]:
    aliases = (get_ifrc_concept_aliases().get(str(area_key or "").strip().lower()) or [])[: max(1, int(max_aliases))]
    return aliases


def get_query_expansion_terms(query: str, *, max_terms: int = 10) -> List[str]:
    """
    Return high-signal expansion terms for the query based on IFRC concepts.
    """
    q = _norm(query)
    if not q:
        return []
    aliases_by_concept = get_ifrc_concept_aliases()
    selected: List[str] = []
    # Semantic concept detection first (multilingual-friendly).
    semantic_keys: List[str] = []
    try:
        semantic_keys = _semantic_concepts_for_query(query, top_k=4)
    except Exception as e:
        logging.getLogger(__name__).debug("get_query_expansion_terms semantic fallback: %s", e)
        semantic_keys = []
    for ckey in semantic_keys:
        selected.append(ckey)
        for a in (aliases_by_concept.get(ckey) or [])[:14]:
            selected.append(a)

    # Lexical trigger fallback/complement.
    for concept, aliases in aliases_by_concept.items():
        # Trigger concept if query contains concept name or one of its top aliases.
        trigger_aliases = aliases[:20] if isinstance(aliases, list) else []
        if (concept in q) or any((a and a in q) for a in trigger_aliases):
            # Include canonical and a limited number of aliases.
            selected.append(concept)
            for a in aliases[:12]:
                selected.append(a)

    # Deduplicate and cap
    return _dedupe_aliases(selected, max_items=max_terms)

