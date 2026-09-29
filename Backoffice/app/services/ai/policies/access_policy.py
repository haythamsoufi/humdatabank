"""Per-request AI access policy: the one object AI tools, RAG retrieval and data tools consult.

Computed once from the authenticated identity (or anonymous), stored on ``flask.g.ai_access_policy``
and re-derived (deny by default) whenever a worker thread has no stored copy.

Access matrix (see also ``docs/DEVELOPER-HANDBOOK.md`` -> "AI access policy"):

============================  ======================  =====================================  ==========================
Principal                     Tools                   Structured data                        Documents
============================  ======================  =====================================  ==========================
anonymous (Website proxy)     public allow-list only  ``privacy='public'``, submitted/        ``is_public`` + role_ok
                                                      approved, any country
authenticated user            full catalog (RBAC-     public anywhere; non-public + drafts   public + own uploads
                              gated sub-sets)         only for accessible countries
admin / countries manager     full catalog            every country                          every document
system manager                full catalog            every country                          every document
internal job                  n/a                     n/a                                    every document
============================  ======================  =====================================  ==========================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional

from app.services.ai.documents.access import (
    ANONYMOUS_PRINCIPAL,
    DocumentPrincipal,
    can_read_ai_document,
    principal_for_user,
)
from app.services.data_retrieval.access import (
    DataAccessPolicy,
    PRINCIPAL_ANONYMOUS,
    build_data_access_policy,
)

logger = logging.getLogger(__name__)

PUBLIC_TOOL_ALLOWLIST: FrozenSet[str] = frozenset(
    {
        "get_indicator_value",
        "get_indicator_timeseries",
        "get_indicator_values_for_all_countries",
        "get_indicator_metadata",
        "search_indicator_bank",
        "get_form_field_value",
        "get_form_field_values_for_all_countries",
        "search_workflow_docs",
        "get_workflow_guide",
        "list_documents",
        "search_documents",
        "search_documents_hybrid",
        "analyze_unified_plans_focus_areas",
        "get_upr_kpi_value",
        "get_upr_kpi_timeseries",
        "get_upr_kpi_values_for_all_countries",
    }
)

PUBLIC_SOURCE_KEYS = ("historical", "system_documents", "upr_documents")


@dataclass(frozen=True)
class AIAccessPolicy:
    data: DataAccessPolicy = field(default_factory=DataAccessPolicy)
    documents: DocumentPrincipal = ANONYMOUS_PRINCIPAL
    user_id: Optional[int] = None
    access_level: str = "public"

    @property
    def principal(self) -> str:
        return self.data.principal

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None and not self.documents.is_internal

    def allows_tool(self, tool_name: str) -> bool:
        """Anonymous callers get an explicit allow-list; authenticated callers keep the RBAC-gated catalog."""
        if self.is_anonymous:
            return tool_name in PUBLIC_TOOL_ALLOWLIST
        return True

    def filter_tool_definitions(self, tool_defs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.is_anonymous:
            return list(tool_defs)
        out = []
        for td in tool_defs:
            fn = td.get("function") if isinstance(td, dict) else None
            name = str((fn or {}).get("name") or "").strip()
            if name in PUBLIC_TOOL_ALLOWLIST:
                out.append(td)
        return out

    def can_read_document(self, doc: Any) -> bool:
        return can_read_ai_document(self.documents, doc)

    def clamp_sources(self, sources_cfg: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Anonymous callers cannot switch on sources beyond the public set; unknown keys are dropped."""
        if sources_cfg is None or not isinstance(sources_cfg, dict):
            return sources_cfg
        if not self.is_anonymous:
            return sources_cfg
        return {k: bool(sources_cfg.get(k, False)) for k in PUBLIC_SOURCE_KEYS}

    def bind_page_context(
        self, page_context: Optional[Dict[str, Any]], *, auth_source: Optional[str] = "cookie"
    ) -> Optional[Dict[str, Any]]:
        """Remove client-asserted privileged context (form builder) the server cannot vouch for."""
        if not isinstance(page_context, dict) or "formBuilder" not in page_context:
            return page_context
        from app.utils.ai_utils import authorize_form_builder_context

        bound = dict(page_context)
        fb = authorize_form_builder_context(
            bound.get("formBuilder"), user_id=self.user_id, auth_source=auth_source
        )
        if fb is None:
            bound.pop("formBuilder", None)
        else:
            bound["formBuilder"] = fb
        return bound


PUBLIC_POLICY = AIAccessPolicy()


def build_ai_access_policy(user: Any = None, *, elevated_api_key: bool = False) -> AIAccessPolicy:
    """Policy for ``user`` (``None`` or unauthenticated => anonymous public)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return PUBLIC_POLICY
    data = build_data_access_policy(user, elevated_api_key=elevated_api_key)
    if data.principal == PRINCIPAL_ANONYMOUS:
        return PUBLIC_POLICY
    try:
        from app.services.organization.authorization_service import AuthorizationService

        level = AuthorizationService.access_level(user)
    except Exception as exc:
        logger.debug("build_ai_access_policy: access_level failed: %s", exc)
        level = "user"
    return AIAccessPolicy(
        data=data,
        documents=principal_for_user(user),
        user_id=data.user_id,
        access_level=level,
    )


def set_request_policy(policy: AIAccessPolicy) -> AIAccessPolicy:
    """Store ``policy`` on ``flask.g`` for the current request/worker context."""
    try:
        from flask import g, has_request_context

        if has_request_context():
            g.ai_access_policy = policy
    except Exception as exc:
        logger.debug("set_request_policy failed: %s", exc)
    return policy


def resolve_ai_access_policy() -> AIAccessPolicy:
    """Return the request's policy, deriving it (deny by default) when a route did not store one."""
    try:
        from flask import g, has_request_context
        from flask_login import current_user

        if has_request_context():
            stored = getattr(g, "ai_access_policy", None)
            if isinstance(stored, AIAccessPolicy):
                return stored

        user = current_user if getattr(current_user, "is_authenticated", False) else None
        if user is None and has_request_context():
            uid = getattr(g, "ai_user_id", None)
            if uid:
                from app.extensions import db
                from app.models import User

                user = db.session.get(User, int(uid))
        policy = build_ai_access_policy(user)
    except Exception as exc:
        logger.warning("resolve_ai_access_policy failed, falling back to public policy: %s", exc)
        return PUBLIC_POLICY
    return set_request_policy(policy)


def record_form_builder_authorization(form_builder: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Remember the server-validated form-builder context (``None`` = not authorized) for this request."""
    try:
        from flask import g, has_request_context

        if has_request_context():
            g.ai_form_builder_authorized = dict(form_builder) if isinstance(form_builder, dict) else None
    except Exception as exc:
        logger.debug("record_form_builder_authorization failed: %s", exc)
    return form_builder


def trusted_form_builder_context() -> Optional[Dict[str, Any]]:
    """The form-builder context the route validated for this request, else ``None`` (deny by default).

    Executors and engines must use this instead of trusting ``page_context.formBuilder`` directly.
    """
    try:
        from flask import g, has_request_context

        if not has_request_context():
            return None
        fb = getattr(g, "ai_form_builder_authorized", None)
    except Exception:
        return None
    if isinstance(fb, dict) and fb.get("enabled"):
        return {**fb, "enabled": True}
    return None
