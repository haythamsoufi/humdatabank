"""Permission vocabulary, parser, legacy migration mapping and the route/capability guard."""
import importlib.util
import pathlib

import pytest

from app.services.security import api_key_permissions as perms
from app.services.security.api_key_permissions import (
    ALL_CAPABILITY_CODES,
    CAPABILITIES,
    DATA_READ,
    PII_CAPABILITY_CODES,
    PRESETS,
    SCOPABLE_CAPABILITY_CODES,
    USERS_READ,
    build_permissions_document,
    describe_permissions,
    full_access_document,
    parse_key_permissions,
)
from app.services.security.api_key_route_catalog import (
    collect_key_routes,
    routes_by_capability,
    undeclared_key_routes,
)

pytestmark = [pytest.mark.unit]

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[3] / "migrations" / "versions" / "api_key_permissions_v2.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("api_key_permissions_v2_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParser:
    @pytest.mark.parametrize(
        "raw,schema",
        [
            (None, "missing"),
            ("read_all", "invalid"),
            ([], "invalid"),
            ({}, "invalid"),
            ({"data": "bogus"}, "invalid"),
            ({"version": 9, "capabilities": ["data:read"]}, "invalid"),
        ],
    )
    def test_unusable_documents_grant_nothing(self, raw, schema):
        parsed = parse_key_permissions(raw)
        assert parsed.capabilities == frozenset()
        assert parsed.schema == schema
        assert not parsed.allow_query_api_key
        assert not parsed.legacy_full_access

    def test_v2_grants_only_known_capabilities(self):
        parsed = parse_key_permissions(
            {"version": 2, "capabilities": [DATA_READ, "nope", 5, None]}
        )
        assert parsed.capabilities == frozenset({DATA_READ})
        assert any("unknown capability" in w for w in parsed.warnings)

    def test_v2_capabilities_must_be_a_list(self):
        assert parse_key_permissions({"version": 2, "capabilities": "data:read"}).capabilities == frozenset()

    @pytest.mark.parametrize("scope", ["all", 5, {"template_ids": "1"}, {"template_ids": [0]}, {"country_ids": [True]}])
    def test_malformed_scope_denies_all_data(self, scope):
        parsed = parse_key_permissions({"version": 2, "capabilities": [DATA_READ], "data_scope": scope})
        assert parsed.denies_all_data
        assert parsed.data_scope == {"template_ids": [], "country_ids": []}

    def test_scope_is_normalised(self):
        parsed = parse_key_permissions(
            {"version": 2, "capabilities": [DATA_READ], "data_scope": {"template_ids": ["3", 1, 3]}}
        )
        assert parsed.data_scope == {"template_ids": [1, 3], "country_ids": []}
        assert parsed.is_scoped and not parsed.denies_all_data

    def test_query_key_flag_must_be_literal_true(self):
        base = {"version": 2, "capabilities": [DATA_READ]}
        assert not parse_key_permissions({**base, "allow_query_api_key": "true"}).allow_query_api_key
        assert not parse_key_permissions({**base, "allow_query_api_key": 1}).allow_query_api_key
        assert parse_key_permissions({**base, "allow_query_api_key": True}).allow_query_api_key

    def test_legacy_read_all_v1_is_full_access(self):
        parsed = parse_key_permissions({"data": "read_all"})
        assert parsed.capabilities == perms.LEGACY_FULL_ACCESS_CAPABILITIES
        assert perms.MCP_USE not in parsed.capabilities
        assert parsed.legacy_full_access and parsed.allow_query_api_key

    def test_legacy_none_and_scoped_v1(self):
        assert parse_key_permissions({"data": "none"}).capabilities == perms.LEGACY_NONE_CAPABILITIES
        scoped = parse_key_permissions({"data": "read_scoped", "template_ids": [2]})
        assert scoped.capabilities == perms.LEGACY_SCOPED_CAPABILITIES
        assert scoped.data_scope == {"template_ids": [2], "country_ids": []}

    def test_build_rejects_unknown_capability(self):
        with pytest.raises(ValueError):
            build_permissions_document(["data:read", "root"])

    def test_roundtrip(self):
        doc = build_permissions_document(
            [DATA_READ, USERS_READ], restrict_data=True, template_ids=[4], allow_query_api_key=True
        )
        parsed = parse_key_permissions(doc)
        assert parsed.capabilities == {DATA_READ, USERS_READ}
        assert parsed.data_scope == {"template_ids": [4], "country_ids": []}
        assert parsed.allow_query_api_key

    def test_describe_flags_pii_and_legacy(self):
        info = describe_permissions(parse_key_permissions({"data": "read_all"}))
        assert info["legacy_full_access"] and info["pii"] and info["valid"]
        empty = describe_permissions(parse_key_permissions(None))
        assert empty["no_access"] and not empty["valid"]


class TestVocabulary:
    def test_codes_are_unique_and_documented(self):
        codes = [c.code for c in CAPABILITIES]
        assert len(codes) == len(set(codes))
        for cap in CAPABILITIES:
            assert cap.label and cap.description

    def test_presets_only_use_known_capabilities(self):
        for preset in PRESETS:
            assert set(preset.capabilities) <= ALL_CAPABILITY_CODES

    def test_public_presets_never_include_personal_data(self):
        for preset in PRESETS:
            assert not set(preset.capabilities) & PII_CAPABILITY_CODES, preset.code

    def test_only_data_bearing_capabilities_are_scopable(self):
        assert SCOPABLE_CAPABILITY_CODES == {"data:read", "submissions:read", "templates:read"}

    def test_full_access_document_grants_everything(self):
        assert parse_key_permissions(full_access_document()).capabilities == ALL_CAPABILITY_CODES


class TestLegacyMigrationEquivalence:
    """The self-contained migration mapping must agree with the runtime parser."""

    ORIGINALS = [
        None,
        {"data": "read_all"},
        {"data": "none"},
        {"data": "read_scoped", "template_ids": [1, 2], "country_ids": [9]},
        {"data": "read_scoped"},
        {"data": "read_scoped", "template_ids": ["x"]},
        {"data": "unknown"},
        {"data": "read_all", "mcp": True},
        {"data": "none", "mcp": True},
        {"mcp": True},
        "read_all",
        [],
        {},
    ]

    @pytest.mark.parametrize("original", ORIGINALS, ids=lambda o: repr(o)[:40])
    def test_upgrade_matches_runtime_semantics(self, original):
        migration = _load_migration()
        upgraded = migration.upgrade_document(original)
        assert upgraded is not None
        migrated = parse_key_permissions(upgraded)
        runtime_v1 = parse_key_permissions(original) if isinstance(original, dict) else None
        if original is None:
            assert migrated.capabilities == perms.LEGACY_FULL_ACCESS_CAPABILITIES and migrated.legacy_full_access
        elif runtime_v1 is not None and runtime_v1.is_valid:
            assert migrated.capabilities == runtime_v1.capabilities
            assert migrated.data_scope == runtime_v1.data_scope
            assert migrated.legacy_full_access == runtime_v1.legacy_full_access
        else:
            assert migrated.capabilities == frozenset()

    def test_capability_constants_match_runtime(self):
        migration = _load_migration()
        assert set(migration.LEGACY_FULL_CAPABILITIES) == set(perms.LEGACY_FULL_ACCESS_CAPABILITIES)
        assert migration.MCP_CAPABILITY == perms.MCP_USE
        assert set(migration.SCOPED_CAPABILITIES) == set(perms.LEGACY_SCOPED_CAPABILITIES)
        assert set(migration.NONE_CAPABILITIES) == set(perms.LEGACY_NONE_CAPABILITIES)
        assert migration.SCHEMA_VERSION == perms.SCHEMA_VERSION

    def test_existing_v2_rows_are_left_alone(self):
        migration = _load_migration()
        assert migration.upgrade_document(build_permissions_document([DATA_READ])) is None

    @pytest.mark.parametrize("original", ORIGINALS, ids=lambda o: repr(o)[:40])
    def test_downgrade_restores_the_original_exactly(self, original):
        migration = _load_migration()
        upgraded = migration.upgrade_document(original)
        restore, value = migration.downgrade_document(upgraded)
        assert restore is True
        assert value == original

    def test_downgrade_of_new_style_rows_maps_to_legacy_shape(self):
        migration = _load_migration()
        assert migration.downgrade_document(build_permissions_document([USERS_READ])) == (True, {"data": "none"})
        assert migration.downgrade_document(build_permissions_document([DATA_READ])) == (
            True, {"data": "read_all"},
        )
        scoped = build_permissions_document([DATA_READ], restrict_data=True, template_ids=[3])
        assert migration.downgrade_document(scoped) == (
            True, {"data": "read_scoped", "template_ids": [3], "country_ids": []},
        )
        assert migration.downgrade_document({"data": "read_all"}) == (False, None)


class TestRouteCapabilityGuard:
    def test_every_key_route_declares_a_known_capability(self, app):
        assert undeclared_key_routes(app) == []
        for route in collect_key_routes(app):
            assert route.capability in ALL_CAPABILITY_CODES, (route.path, route.capability)

    def test_scope_aware_routes_only_use_scopable_capabilities(self, app):
        for route in collect_key_routes(app):
            if route.scope_aware:
                assert route.capability in SCOPABLE_CAPABILITY_CODES, route.path

    def test_data_bearing_routes_are_scope_aware_or_unscoped_only(self, app):
        """Scopable capabilities on a route without scope support just refuse scoped keys (fail closed)."""
        unaware = [r.path for r in collect_key_routes(app)
                   if r.capability in SCOPABLE_CAPABILITY_CODES and not r.scope_aware]
        assert set(unaware) <= {
            "/api/v1/upr", "/api/v1/upr/data", "/api/v1/upr/master", "/api/v1/upr/submissions",
        }

    def test_personal_data_routes_require_a_pii_capability(self, app):
        by_cap = routes_by_capability(app)
        pii_paths = {r.path for code in PII_CAPABILITY_CODES for r in by_cap.get(code, [])}
        for path in ("/api/v1/users", "/api/v1/users/<int:user_id>", "/api/v1/quiz/leaderboard",
                     "/api/v1/indicator-suggestions"):
            assert path in pii_paths, path

    def test_no_key_route_is_left_on_the_bare_decorators(self, app):
        """A bare @require_api_key (no capability) would be denied at runtime; catch it here."""
        assert all(r.capability for r in collect_key_routes(app))


class TestMigrationAgainstDatabase:
    def test_upgrade_then_downgrade_roundtrips_real_rows(self, app, db_session):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import text

        from app import db
        from tests.factories import create_test_api_key

        originals = [None, {"data": "read_all"}, {"data": "none"},
                     {"data": "read_scoped", "template_ids": [1], "country_ids": []},
                     {"data": "weird"}, {"data": "read_all", "mcp": True}]
        with app.app_context():
            ids = [create_test_api_key(db_session, permissions=o)[0].id for o in originals]
            fresh_id = create_test_api_key(db_session, permissions=build_permissions_document([DATA_READ]))[0].id
            migration = _load_migration()
            connection = db.session.connection()
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

            def stored(key_id):
                return db.session.execute(
                    text("SELECT permissions FROM api_keys WHERE id = :i"), {"i": key_id}
                ).scalar()

            for key_id, original in zip(ids, originals):
                document = stored(key_id)
                assert document["version"] == perms.SCHEMA_VERSION
                assert document["legacy"]["original"] == original
            assert stored(ids[0])["legacy"]["full_access"] is True
            assert stored(ids[4])["capabilities"] == []
            assert stored(fresh_id) == build_permissions_document([DATA_READ])

            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            for key_id, original in zip(ids, originals):
                assert stored(key_id) == original
            assert stored(fresh_id) == {"data": "read_all"}
            db_session.rollback()
