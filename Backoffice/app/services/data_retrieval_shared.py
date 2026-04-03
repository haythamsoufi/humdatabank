# ========== Data Retrieval Shared Helpers ==========
"""
Shared helpers for the data retrieval layer (country, form, and main service).

Used by: data_retrieval_country, data_retrieval_form, data_retrieval_service.
"""

import logging
import re
from typing import List, Optional

from flask_login import current_user
from sqlalchemy import or_, text

from app.models import User, Country, FormItem, IndicatorBank
from app.extensions import db
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.constants import DEFAULT_INDICATOR_CANDIDATES_LIMIT

logger = logging.getLogger(__name__)


def get_effective_request_user():
    """
    Best-effort authenticated user resolution.

    This service is used from HTTP routes, WS handlers, and agent execution paths where
    `current_user` may be anonymous even though we have a real user id in request-scoped
    context (e.g., `g.ai_user_id`).
    """
    user_obj = current_user if getattr(current_user, "is_authenticated", False) else None
    try:
        from flask import g, has_request_context

        if user_obj is None and has_request_context():
            uid = getattr(g, "ai_user_id", None)
            if uid:
                user_obj = db.session.get(User, int(uid))
    except Exception as e:
        logger.debug("get_effective_request_user: failed to resolve ai_user_id: %s", e)
    return user_obj


def can_view_non_public_form_items(user) -> bool:
    """
    Determine if a user may view non-public (organization-network / internal) form items.

    Returns True for: system managers, admins, users with data-explore RBAC, or users
    whose email belongs to the organization domain (same-org / internal users, e.g.
    focal points identified by organization_email_domain in settings).
    """
    try:
        from app.services.authorization_service import AuthorizationService
        from app.utils.app_settings import is_organization_email
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if AuthorizationService.is_system_manager(user) or AuthorizationService.is_admin(user):
            return True
        if (AuthorizationService.has_rbac_permission(user, "admin.data_explore.data_table") or
            AuthorizationService.has_rbac_permission(user, "admin.data_explore.analysis") or
            AuthorizationService.has_rbac_permission(user, "admin.data_explore.compliance")):
            return True
        # Same-org users (email domain matches organization_email_domain from settings)
        if getattr(user, "email", None) and is_organization_email(user.email):
            return True
    except Exception as e:
        logger.debug("can_view_non_public_form_items failed: %s", e)
        return False
    return False


def form_item_privacy_is_public_expr():
    """SQLAlchemy expression for FormItem privacy == 'public' (stored in config JSON)."""
    return FormItem.config["privacy"].as_string() == "public"


def escape_like_pattern(s: Optional[str]) -> str:
    """
    Escape SQL LIKE/ILIKE special characters (% and _) so user-supplied
    period/search strings do not change match semantics.
    """
    if not s:
        return ""
    return str(s).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_RELEVANCE_STOP_WORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "not",
    "their", "its", "into", "with", "by", "from", "as", "at", "is", "are",
    "was", "were", "be", "been", "do", "does", "did", "has", "have", "had",
    "that", "this", "it", "number", "total",
})


_STEM_GROUPS: dict[str, set[str]] = {
    "volunteer": {"volunteer", "volunteers", "volunteering"},
    "branch": {"branch", "branches", "branching"},
    "staff": {"staff", "staffed", "staffing"},
    "member": {"member", "members", "membership"},
    "donate": {"donate", "donates", "donated", "donation", "donations", "donating"},
    "train": {"train", "trains", "trained", "training", "trainings"},
}
_WORD_TO_STEM: dict[str, str] = {}
for _stem, _forms in _STEM_GROUPS.items():
    for _form in _forms:
        _WORD_TO_STEM[_form] = _stem


def _stem_match(word_a: str, word_b: str) -> bool:
    """True when two words share the same stem group (volunteer≈volunteering)."""
    sa = _WORD_TO_STEM.get(word_a)
    sb = _WORD_TO_STEM.get(word_b)
    return sa is not None and sa == sb


def score_indicator_relevance(ind_name: str, query: str) -> float:
    """
    Keyword-based indicator relevance score (higher = more relevant).

    When vector similarity is available this is used as a lightweight secondary
    signal (weighted ×0.3); when embeddings are unavailable it serves as the
    primary disambiguation signal.  Combines query-term overlap, contiguous
    phrase matching, domain-specific core-term bonuses, and penalties for
    overly-specific qualifiers / long names.
    """
    score = 1.0
    name_lower = (ind_name or "").lower()
    query_lower = (query or "").lower()

    query_terms = [w for w in re.findall(r"[a-z]+", query_lower)
                   if w not in _RELEVANCE_STOP_WORDS and len(w) > 1]
    name_terms_set = set(re.findall(r"[a-z]+", name_lower))
    if query_terms:
        matched = sum(
            1 for t in query_terms
            if t in name_terms_set or any(_stem_match(t, nt) for nt in name_terms_set)
        )
        score += (matched / len(query_terms)) * 3.0

    query_words = query_lower.split()
    phrase_bonus = 0.0
    for n in range(min(len(query_words), 4), 1, -1):
        for i in range(len(query_words) - n + 1):
            phrase = " ".join(query_words[i:i + n])
            if len(phrase) > 5 and phrase in name_lower:
                phrase_bonus += n * 0.3
    score += min(phrase_bonus, 2.0)

    core_terms = ['branch', 'branches', 'volunteer', 'volunteers', 'staff', 'member', 'members']
    for term in core_terms:
        if term in query_lower:
            if term in name_lower:
                if name_lower.startswith(f"number of {term}") or name_lower.startswith(f"number of national society {term}"):
                    score += 2.0
                elif f"number of {term}" in name_lower:
                    score += 1.5
            if term in ('volunteer', 'volunteers') and 'people volunteering' in name_lower:
                score += 2.5

    specific_qualifiers = [
        'with ', 'supported through', 'that have', 'which have', 'providing',
        'covered by', 'engaged in', 'involved in', 'trained in', 'participating in',
        'enrolled in', 'assigned to', 'deployed to', 'registered in',
    ]
    qualifier_penalty = 0.0
    for qualifier in specific_qualifiers:
        if qualifier in name_lower:
            qualifier_penalty += 2.0
    score -= min(qualifier_penalty, 4.0)

    word_count = len(name_lower.split())
    if word_count <= 5:
        score += 1.0
    elif word_count <= 8:
        pass
    elif word_count <= 12:
        score -= 0.5
    else:
        score -= 1.0
    return score


def user_allowed_country_ids() -> Optional[set]:
    """
    Return set of country IDs the current user may access.
    None for unrestricted; set of IDs for scoped users; empty set if no access.
    """
    try:
        from app.services.authorization_service import AuthorizationService
        user_obj = get_effective_request_user() or current_user

        if AuthorizationService.is_system_manager(user_obj):
            return None
        if AuthorizationService.has_rbac_permission(user_obj, "admin.countries.view"):
            return None
        if AuthorizationService.has_rbac_permission(user_obj, "admin.countries.edit"):
            return None
        if AuthorizationService.has_rbac_permission(user_obj, "admin.organization.manage"):
            return None
        if hasattr(user_obj, 'countries') and hasattr(user_obj.countries, 'all'):
            return set(c.id for c in user_obj.countries.all())
    except Exception as e:
        logger.warning(f"Error determining user country access: {e}")
    return set()


def resolve_country_from_identifier(country_identifier: str):
    """
    Resolve a Country from a string using database only: ID, ISO3, name, or name_translations.
    """
    import unicodedata

    raw = (country_identifier or "").strip()
    if not raw:
        return None

    def _norm(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        s = "".join(
            ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
        )
        s = s.lower()
        s = re.sub(r"\([^)]*\)", " ", s)
        s = re.sub(r"[^a-z0-9\s-]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    norm = _norm(raw)
    candidates: list[str] = []
    for s in (raw, norm):
        if s and s not in candidates:
            candidates.append(s)

    for cand in candidates:
        if not cand:
            continue
        if str(cand).isdigit():
            c = db.session.get(Country, int(cand))
            if c:
                return c
        if len(cand) == 2:
            c = Country.query.filter(Country.iso2.ilike(safe_ilike_pattern(cand, prefix=False, suffix=False))).first()
            if c:
                return c
        if len(cand) == 3:
            c = Country.query.filter(Country.iso3.ilike(safe_ilike_pattern(cand, prefix=False, suffix=False))).first()
            if c:
                return c
        exact_pat = safe_ilike_pattern(cand, prefix=False, suffix=False)
        c = Country.query.filter(Country.name.ilike(exact_pat)).first()
        if c:
            return c
        # Substring match: avoid "Oman" resolving to "Romania" (both match "%oman%").
        # Prefer exact normalized match, then startswith, then shortest name.
        safe_pat = safe_ilike_pattern(cand)
        name_matches = Country.query.filter(Country.name.ilike(safe_pat)).all()
        if name_matches:
            c = _best_country_match(name_matches, cand, _norm)
            if c:
                return c
        try:
            pat = safe_ilike_pattern(cand)
            trans_matches = Country.query.filter(
                Country.name_translations.isnot(None),
                text(
                    "EXISTS (SELECT 1 FROM jsonb_each_text(country.name_translations) AS _t(_k, _v) WHERE _v ILIKE :pat)"
                ),
            ).bindparams(pat=pat).all()
            if trans_matches:
                c = _best_country_match(trans_matches, cand, _norm)
                if c:
                    return c
        except Exception as e:
            logger.debug("name_translations lookup failed (non-PostgreSQL?): %s", e)
            break

    return None


def get_indicator_candidates_by_keyword(
    ident: str,
    limit: int = DEFAULT_INDICATOR_CANDIDATES_LIMIT,
) -> List[IndicatorBank]:
    """
    Resolve indicator name to IndicatorBank candidates via keyword (ILIKE) search.
    Uses safe_ilike_pattern to prevent SQL injection via search terms.
    Use as fallback when vector/LLM resolution is unavailable or returns nothing.

    Returns list of IndicatorBank matching ident and name variants (e.g. "volunteers" -> "volunteering").
    """
    ident = (ident or "").strip()
    if not ident:
        return []
    patterns = [safe_ilike_pattern(ident)]
    if ident.endswith("s") and len(ident) > 3:
        patterns.append(safe_ilike_pattern(ident[:-1] + "ing"))
        patterns.append(safe_ilike_pattern(ident[:-1]))

    # Stem-aware: for each meaningful word in the query, add patterns for all
    # stem variants so "Number of volunteers" also finds "people volunteering".
    query_words = [w.strip().lower() for w in re.split(r"\s+", ident) if len(w.strip()) > 2]
    for word in query_words:
        stem = _WORD_TO_STEM.get(word.lower())
        if stem:
            for variant in _STEM_GROUPS[stem]:
                if variant != word.lower():
                    patterns.append(safe_ilike_pattern(variant))

    single_word = " " not in ident.strip()
    if single_word and len(ident.strip()) > 2:
        cap = ident.strip().lower().capitalize()
        patterns.append(safe_ilike_pattern(f"Number of {cap}"))
        patterns.append(safe_ilike_pattern(f"Number of National Society {cap}"))

    seen_ids: set[int] = set()
    unique_patterns = list(dict.fromkeys(patterns))
    results: list[IndicatorBank] = []
    for ind in (
        IndicatorBank.query.filter(or_(*[IndicatorBank.name.ilike(p) for p in unique_patterns]))
        .limit(limit)
        .all()
    ):
        if ind.id not in seen_ids:
            seen_ids.add(ind.id)
            results.append(ind)
    logger.info(
        "get_indicator_candidates_by_keyword: ident=%r patterns=%d results=%d matches=%s",
        ident, len(unique_patterns), len(results),
        [(ind.name, ind.id) for ind in results[:8]],
    )
    return results


def _best_country_match(
    countries: list,
    cand: str,
    norm_fn,
) -> Optional[Country]:
    """
    From countries matching a substring (e.g. "%oman%"), pick the best:
    prefer exact normalized name, then name starting with cand, then shortest name.
    Avoids "Oman" resolving to "Romania" when cand is "oman".
    """
    if not countries:
        return None
    norm_cand = norm_fn(cand)
    exact = [c for c in countries if norm_fn(c.name) == norm_cand]
    if exact:
        return exact[0]
    startswith = [c for c in countries if norm_fn(c.name).startswith(norm_cand)]
    if startswith:
        return min(startswith, key=lambda c: len(c.name))
    return min(countries, key=lambda c: len(c.name))
