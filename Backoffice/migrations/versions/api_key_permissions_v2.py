"""Rewrite api_keys.permissions into the explicit capability schema (v2), reversibly.

Revision ID: api_key_permissions_v2
Revises: add_auth_state_entry
Create Date: 2026-09-29

Before this revision ``api_keys.permissions`` was NULL for every key created in the admin UI
and the runtime treated NULL, unknown values and malformed documents as unrestricted
``read_all``. The runtime now grants nothing unless a capability is listed, so existing rows
are rewritten to say explicitly what they could do before:

* NULL / ``{"data": "read_all"}``  -> every capability a legacy key could reach, unscoped, marked
  ``legacy.full_access`` (so the admin UI can flag it and an operator can narrow it).
* ``{"data": "read_scoped", ...}``  -> data:read + reference:read with the same data_scope.
* ``{"data": "none"}``              -> reference:read + content:read only.
* anything else (unknown value, wrong type) -> no capabilities (it used to fail open).
* A top-level ``"mcp": true`` flag (the MCP proxy grant) becomes the ``mcp:use`` capability.

The previous value is preserved in ``legacy.original`` so ``downgrade()`` restores it exactly.
Rows that already carry a schema-v2 document are left untouched.

The mapping is intentionally self-contained (no app imports): migrations must keep working
when application code changes. tests/unit/test_services/test_api_key_permissions.py asserts
it stays equivalent to the runtime parser.
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "api_key_permissions_v2"
down_revision = "add_auth_state_entry"
branch_labels = None
depends_on = None

SCHEMA_VERSION = 2

LEGACY_FULL_CAPABILITIES = [
    "content:read",
    "data:read",
    "documents:read",
    "indicators:manage",
    "indicators:suggest",
    "mobile:client",
    "reference:read",
    "submissions:read",
    "templates:read",
    "users:read",
]
SCOPED_CAPABILITIES = ["data:read", "reference:read"]
MCP_CAPABILITY = "mcp:use"
NONE_CAPABILITIES = ["content:read", "reference:read"]

_MISSING = object()


def _ids(value):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        return None
    out = set()
    for raw in value:
        if isinstance(raw, bool):
            return None
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return None
        if number < 1:
            return None
        out.add(number)
    return sorted(out)


def upgrade_document(original):
    """Return the v2 document for a pre-v2 ``permissions`` value, or ``None`` to leave it alone."""
    if isinstance(original, dict) and "version" in original:
        return None

    mcp = [MCP_CAPABILITY] if isinstance(original, dict) and original.get("mcp") is True else []

    def doc(capabilities, *, full_access=False, scope=None, allow_query=True, with_mcp=True):
        granted = set(capabilities) | (set(mcp) if with_mcp else set())
        result = {
            "version": SCHEMA_VERSION,
            "capabilities": sorted(granted),
            "legacy": {"full_access": full_access, "original": original},
        }
        if scope is not None:
            result["data_scope"] = scope
        if allow_query:
            result["allow_query_api_key"] = True
        return result

    if original is None:
        return doc(LEGACY_FULL_CAPABILITIES, full_access=True)
    if not isinstance(original, dict):
        return doc([], allow_query=False)

    if "data" not in original and "mcp" in original:
        return doc([], allow_query=False)

    data = original.get("data")
    if data == "read_all":
        return doc(LEGACY_FULL_CAPABILITIES, full_access=True)
    if data == "read_scoped":
        template_ids = _ids(original.get("template_ids"))
        country_ids = _ids(original.get("country_ids"))
        if template_ids is None or country_ids is None:
            return doc([], allow_query=False, with_mcp=False)
        return doc(
            SCOPED_CAPABILITIES,
            scope={"template_ids": template_ids, "country_ids": country_ids},
        )
    if data == "none":
        return doc(NONE_CAPABILITIES)
    return doc([], allow_query=False, with_mcp=False)


def downgrade_document(document):
    """Return ``(restore, value)``; ``restore`` False means leave the row as is."""
    if not isinstance(document, dict) or document.get("version") != SCHEMA_VERSION:
        return False, None
    legacy = document.get("legacy")
    if isinstance(legacy, dict) and "original" in legacy:
        return True, legacy["original"]

    capabilities = set(document.get("capabilities") or [])
    extra = {"mcp": True} if MCP_CAPABILITY in capabilities else {}
    if "data:read" not in capabilities:
        return True, {"data": "none", **extra}
    scope = document.get("data_scope")
    if isinstance(scope, dict):
        return True, {
            "data": "read_scoped",
            "template_ids": scope.get("template_ids") or [],
            "country_ids": scope.get("country_ids") or [],
            **extra,
        }
    return True, {"data": "read_all", **extra}


def _write(bind, key_id, value):
    if value is None:
        bind.execute(sa.text("UPDATE api_keys SET permissions = NULL WHERE id = :id"), {"id": key_id})
    else:
        bind.execute(
            sa.text("UPDATE api_keys SET permissions = CAST(:p AS json) WHERE id = :id"),
            {"id": key_id, "p": json.dumps(value)},
        )


def _rows(bind):
    for key_id, permissions in bind.execute(sa.text("SELECT id, permissions FROM api_keys")).fetchall():
        if isinstance(permissions, str):
            try:
                permissions = json.loads(permissions)
            except ValueError:
                pass
        yield key_id, permissions


def upgrade():
    bind = op.get_bind()
    for key_id, permissions in list(_rows(bind)):
        document = upgrade_document(permissions)
        if document is not None:
            _write(bind, key_id, document)


def downgrade():
    bind = op.get_bind()
    for key_id, permissions in list(_rows(bind)):
        restore, value = downgrade_document(permissions)
        if restore:
            _write(bind, key_id, value)
