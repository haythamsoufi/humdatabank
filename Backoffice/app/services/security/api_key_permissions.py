# ========== API Key Permission Model ==========
"""
Capability vocabulary and permission-document parsing for database API keys.

This module is pure Python (no Flask, no database) so it can be imported by the
model, the authentication layer, the admin UI and tests without cycles.

Permission document (``api_keys.permissions``, schema v2)::

    {
      "version": 2,
      "capabilities": ["data:read", "reference:read"],
      "data_scope": {"template_ids": [1], "country_ids": [5]},   # optional
      "allow_query_api_key": false,                               # optional
      "legacy": {"full_access": true, "original": null}           # migrated keys only
    }

Rules (all enforced in one place, ``app.services.security.api_authentication``):

* A key may only call routes whose declared capability it holds.
* ``data_scope`` restricts every data-bearing capability (``scopable`` ones) to the
  listed templates / countries. Absent means unrestricted; present with both lists
  empty means *no* data (fail closed).
* Anything we cannot interpret (NULL, wrong type, unknown ``data`` value, malformed
  ids) grants nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

SCHEMA_VERSION = 2

# Legacy (v1) vocabulary, kept only to interpret rows written before schema v2.
LEGACY_DATA_READ_ALL = "read_all"
LEGACY_DATA_READ_SCOPED = "read_scoped"
LEGACY_DATA_NONE = "none"

DATA_READ = "data:read"
SUBMISSIONS_READ = "submissions:read"
TEMPLATES_READ = "templates:read"
DOCUMENTS_READ = "documents:read"
USERS_READ = "users:read"
REFERENCE_READ = "reference:read"
CONTENT_READ = "content:read"
INDICATORS_SUGGEST = "indicators:suggest"
INDICATORS_MANAGE = "indicators:manage"
MOBILE_CLIENT = "mobile:client"
MCP_USE = "mcp:use"

SENSITIVITY_STANDARD = "standard"
SENSITIVITY_SENSITIVE = "sensitive"
SENSITIVITY_PII = "pii"


@dataclass(frozen=True)
class Capability:
    """One grantable permission. Endpoint lists are derived from the live URL map."""

    code: str
    label: str
    description: str
    sensitivity: str = SENSITIVITY_STANDARD
    scopable: bool = False
    group: str = "reference"


CAPABILITIES: Tuple[Capability, ...] = (
    Capability(
        DATA_READ,
        "Form data",
        "Read submitted form data (values, disaggregation, dynamic and repeat sections) "
        "for BI tools and integrations.",
        SENSITIVITY_SENSITIVE,
        scopable=True,
        group="data",
    ),
    Capability(
        SUBMISSIONS_READ,
        "Submissions and assignments",
        "List and open assignments and submissions with status, due dates and answers. "
        "Public-submitter names and email addresses are only included when the key also "
        "has 'User directory and personal data'.",
        SENSITIVITY_SENSITIVE,
        scopable=True,
        group="data",
    ),
    Capability(
        TEMPLATES_READ,
        "Form templates",
        "Read form template structure (pages, sections, items).",
        SENSITIVITY_STANDARD,
        scopable=True,
        group="data",
    ),
    Capability(
        DOCUMENTS_READ,
        "Submitted documents",
        "Also list pending, rejected and non-public submitted documents (GET /submitted-documents), "
        "and include the documents attached to a submission. Public, approved documents only "
        "need 'Public content'.",
        SENSITIVITY_SENSITIVE,
        scopable=False,
        group="data",
    ),
    Capability(
        USERS_READ,
        "User directory and personal data",
        "Read user names, email addresses, titles, roles and country assignments, the quiz "
        "leaderboard, and submitter contact details on submissions.",
        SENSITIVITY_PII,
        scopable=False,
        group="people",
    ),
    Capability(
        REFERENCE_READ,
        "Reference data",
        "Read countries, national societies, periods, sectors, subsectors, lookup lists "
        "and the indicator bank.",
        SENSITIVITY_STANDARD,
        group="reference",
    ),
    Capability(
        CONTENT_READ,
        "Public content",
        "Read public website content: resources, embedded content, glossary terms, public "
        "approved documents and the published public figures feed.",
        SENSITIVITY_STANDARD,
        group="reference",
    ),
    Capability(
        INDICATORS_SUGGEST,
        "Submit indicator suggestions",
        "Create indicator suggestions (write). Used by the public website suggestion form.",
        SENSITIVITY_STANDARD,
        group="indicators",
    ),
    Capability(
        INDICATORS_MANAGE,
        "Review indicator suggestions",
        "Read submitted indicator suggestions (includes submitter names and emails) and "
        "change their review status (write).",
        SENSITIVITY_PII,
        group="indicators",
    ),
    Capability(
        MOBILE_CLIENT,
        "Mobile app client marker",
        "Lets a client send this key as X-Mobile-Auth to skip CSRF on session-backed mobile "
        "requests. Grants no data access on its own.",
        SENSITIVITY_STANDARD,
        group="clients",
    ),
    Capability(
        MCP_USE,
        "MCP proxy",
        "Use the Backoffice proxy to the Databank MCP server (AI assistant connectors).",
        SENSITIVITY_STANDARD,
        group="clients",
    ),
)

CAPABILITY_BY_CODE: Dict[str, Capability] = {c.code: c for c in CAPABILITIES}
ALL_CAPABILITY_CODES: FrozenSet[str] = frozenset(CAPABILITY_BY_CODE)
SCOPABLE_CAPABILITY_CODES: FrozenSet[str] = frozenset(c.code for c in CAPABILITIES if c.scopable)
SENSITIVE_CAPABILITY_CODES: FrozenSet[str] = frozenset(
    c.code for c in CAPABILITIES if c.sensitivity in (SENSITIVITY_SENSITIVE, SENSITIVITY_PII)
)
PII_CAPABILITY_CODES: FrozenSet[str] = frozenset(
    c.code for c in CAPABILITIES if c.sensitivity == SENSITIVITY_PII
)

# What a legacy ``read_all`` key could reach before capabilities existed: every key-protected
# route except the MCP proxy, which always required an explicit ``"mcp": true`` flag.
LEGACY_FULL_ACCESS_CAPABILITIES: FrozenSet[str] = ALL_CAPABILITY_CODES - {MCP_USE}

# Capabilities a legacy ``{"data": "none"}`` key keeps: it was documented as "no data
# access", so it never receives data, submissions, documents or personal data.
LEGACY_NONE_CAPABILITIES: FrozenSet[str] = frozenset({REFERENCE_READ, CONTENT_READ})
# A legacy ``read_scoped`` key keeps data reads inside its scope plus reference lookups.
LEGACY_SCOPED_CAPABILITIES: FrozenSet[str] = frozenset({DATA_READ, REFERENCE_READ})


@dataclass(frozen=True)
class Preset:
    code: str
    label: str
    description: str
    capabilities: Tuple[str, ...]


PRESETS: Tuple[Preset, ...] = (
    Preset(
        "public_website",
        "Public website / embed",
        "Reference data, public content and the suggestion form. No form data and no "
        "personal data. Use for keys that are embedded in a website front end.",
        (REFERENCE_READ, CONTENT_READ, INDICATORS_SUGGEST),
    ),
    Preset(
        "bi_readonly",
        "BI / analytics (read-only data)",
        "Form data, submissions, templates and reference data for Power BI or similar. "
        "Optionally limit to specific templates and countries.",
        (DATA_READ, SUBMISSIONS_READ, TEMPLATES_READ, REFERENCE_READ),
    ),
    Preset(
        "website_backend",
        "Website back end (server-side only)",
        "Everything the public Website reads: form data, templates, reference data, public "
        "content and the suggestion form. No submissions, documents or personal data. Keep "
        "this key on a server; anything shipped to a browser is public.",
        (DATA_READ, TEMPLATES_READ, REFERENCE_READ, CONTENT_READ, INDICATORS_SUGGEST),
    ),
    Preset(
        "mobile_client",
        "Mobile app client",
        "Reference data, public content and the X-Mobile-Auth marker.",
        (MOBILE_CLIENT, REFERENCE_READ, CONTENT_READ),
    ),
)
PRESET_BY_CODE: Dict[str, Preset] = {p.code: p for p in PRESETS}


def normalize_id_list(values: Any) -> Optional[List[int]]:
    """Return a sorted, de-duplicated list of positive ints, or ``None`` if malformed."""
    if values is None:
        return []
    if not isinstance(values, (list, tuple, set, frozenset)):
        return None
    out = set()
    for raw in values:
        if isinstance(raw, bool):
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        if value < 1:
            return None
        out.add(value)
    return sorted(out)


@dataclass(frozen=True)
class KeyPermissions:
    """Interpreted permission document. Immutable; safe to cache on ``g``."""

    capabilities: FrozenSet[str] = frozenset()
    data_scope: Optional[Dict[str, List[int]]] = None
    allow_query_api_key: bool = False
    legacy: bool = False
    legacy_full_access: bool = False
    schema: str = "missing"
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    @property
    def is_scoped(self) -> bool:
        return self.data_scope is not None

    @property
    def denies_all_data(self) -> bool:
        scope = self.data_scope
        return scope is not None and not scope["template_ids"] and not scope["country_ids"]

    @property
    def is_valid(self) -> bool:
        return self.schema in ("v2", "v1")

    @property
    def sensitive_capabilities(self) -> FrozenSet[str]:
        return self.capabilities & SENSITIVE_CAPABILITY_CODES


def _empty(schema: str, *warnings: str) -> KeyPermissions:
    return KeyPermissions(schema=schema, warnings=tuple(warnings))


def _parse_scope(raw_scope: Any) -> Tuple[Optional[Dict[str, List[int]]], Optional[str]]:
    """Return (scope, warning). A malformed scope becomes deny-all, never unrestricted."""
    if raw_scope is None:
        return None, None
    deny_all = {"template_ids": [], "country_ids": []}
    if not isinstance(raw_scope, dict):
        return deny_all, "data_scope is not an object; data access denied"
    template_ids = normalize_id_list(raw_scope.get("template_ids"))
    country_ids = normalize_id_list(raw_scope.get("country_ids"))
    if template_ids is None or country_ids is None:
        return deny_all, "data_scope contains invalid ids; data access denied"
    return {"template_ids": template_ids, "country_ids": country_ids}, None


def _parse_v2(raw: Dict[str, Any]) -> KeyPermissions:
    warnings: List[str] = []
    raw_caps = raw.get("capabilities")
    if not isinstance(raw_caps, list):
        return _empty("v2", "capabilities is not a list; nothing granted")
    caps = set()
    for item in raw_caps:
        if isinstance(item, str) and item in ALL_CAPABILITY_CODES:
            caps.add(item)
        else:
            warnings.append(f"unknown capability ignored: {item!r}")

    scope, scope_warning = _parse_scope(raw.get("data_scope"))
    if scope_warning:
        warnings.append(scope_warning)

    legacy_meta = raw.get("legacy")
    legacy = isinstance(legacy_meta, dict)
    legacy_full = bool(legacy and legacy_meta.get("full_access") is True)

    caps |= _legacy_mcp_flag(raw)
    return KeyPermissions(
        capabilities=frozenset(caps),
        data_scope=scope,
        allow_query_api_key=raw.get("allow_query_api_key") is True,
        legacy=legacy,
        legacy_full_access=legacy_full,
        schema="v2",
        warnings=tuple(warnings),
    )


def _legacy_mcp_flag(raw: Dict[str, Any]) -> FrozenSet[str]:
    """The MCP proxy was granted by a top-level ``"mcp": true`` flag before schema v2."""
    return frozenset({MCP_USE}) if raw.get("mcp") is True else frozenset()


def _parse_v1(raw: Dict[str, Any]) -> KeyPermissions:
    data_perm = raw.get("data")
    if data_perm == LEGACY_DATA_READ_ALL:
        return KeyPermissions(
            capabilities=LEGACY_FULL_ACCESS_CAPABILITIES | _legacy_mcp_flag(raw),
            allow_query_api_key=True,
            legacy=True,
            legacy_full_access=True,
            schema="v1",
        )
    if data_perm == LEGACY_DATA_READ_SCOPED:
        template_ids = normalize_id_list(raw.get("template_ids"))
        country_ids = normalize_id_list(raw.get("country_ids"))
        if template_ids is None or country_ids is None:
            return _empty("v1", "read_scoped ids are invalid; nothing granted")
        return KeyPermissions(
            capabilities=LEGACY_SCOPED_CAPABILITIES | _legacy_mcp_flag(raw),
            data_scope={"template_ids": template_ids, "country_ids": country_ids},
            allow_query_api_key=True,
            legacy=True,
            schema="v1",
        )
    if data_perm == LEGACY_DATA_NONE:
        return KeyPermissions(
            capabilities=LEGACY_NONE_CAPABILITIES | _legacy_mcp_flag(raw),
            allow_query_api_key=True,
            legacy=True,
            schema="v1",
        )
    return _empty("invalid", f"unrecognised legacy data permission: {data_perm!r}")


def parse_key_permissions(raw: Any) -> KeyPermissions:
    """
    Interpret ``APIKey.permissions``. Never raises; anything unclear grants nothing.

    * ``None`` → nothing (NULL is *not* "full access"; the migration rewrites old rows).
    * schema v2 → the listed capabilities / scope.
    * schema v1 (``{"data": ...}``) → mapped to v2 equivalents for rows written by an
      older release during a rolling deploy.
    """
    if raw is None:
        return _empty("missing", "permissions not set; nothing granted")
    if not isinstance(raw, dict):
        return _empty("invalid", "permissions is not an object; nothing granted")
    if "version" in raw:
        if raw.get("version") != SCHEMA_VERSION:
            return _empty("invalid", f"unsupported permissions version: {raw.get('version')!r}")
        return _parse_v2(raw)
    if "data" in raw:
        return _parse_v1(raw)
    if "mcp" in raw:
        return KeyPermissions(
            capabilities=_legacy_mcp_flag(raw),
            legacy=True,
            schema="v1",
        )
    return _empty("invalid", "unrecognised permissions document; nothing granted")


def build_permissions_document(
    capabilities: Iterable[str],
    *,
    template_ids: Optional[Iterable[int]] = None,
    country_ids: Optional[Iterable[int]] = None,
    restrict_data: bool = False,
    allow_query_api_key: bool = False,
    legacy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a schema-v2 document. Unknown capability codes raise ``ValueError``."""
    caps = sorted(set(capabilities))
    unknown = [c for c in caps if c not in ALL_CAPABILITY_CODES]
    if unknown:
        raise ValueError(f"Unknown API capabilities: {', '.join(unknown)}")
    doc: Dict[str, Any] = {"version": SCHEMA_VERSION, "capabilities": caps}
    if restrict_data:
        doc["data_scope"] = {
            "template_ids": normalize_id_list(template_ids) or [],
            "country_ids": normalize_id_list(country_ids) or [],
        }
    if allow_query_api_key:
        doc["allow_query_api_key"] = True
    if legacy is not None:
        doc["legacy"] = legacy
    return doc


def full_access_document() -> Dict[str, Any]:
    """Every capability, unscoped, no legacy marker (explicit, for tests and tooling)."""
    return build_permissions_document(ALL_CAPABILITY_CODES)


def describe_permissions(perms: KeyPermissions) -> Dict[str, Any]:
    """Plain-language summary for the admin UI: what this key can actually do."""
    granted = [CAPABILITY_BY_CODE[c] for c in sorted(perms.capabilities)]
    data_caps = [c for c in granted if c.scopable]
    return {
        "capabilities": granted,
        "sensitive": [c for c in granted if c.sensitivity in (SENSITIVITY_SENSITIVE, SENSITIVITY_PII)],
        "pii": [c for c in granted if c.sensitivity == SENSITIVITY_PII],
        "is_scoped": perms.is_scoped,
        "scope_applies_to": [c.label for c in data_caps] if perms.is_scoped else [],
        "denies_all_data": perms.denies_all_data,
        "legacy": perms.legacy,
        "legacy_full_access": perms.legacy_full_access,
        "allow_query_api_key": perms.allow_query_api_key,
        "valid": perms.is_valid,
        "no_access": not perms.capabilities,
        "warnings": list(perms.warnings),
    }
