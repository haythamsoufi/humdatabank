"""Access policy matrix: anonymous / same-org / focal point / admin for documents, data and tools."""

import pytest

from app.extensions import db
from app.models.embeddings import AIDocument
from app.services.ai.documents.access import (
    ANONYMOUS_PRINCIPAL,
    INTERNAL_PRINCIPAL,
    DocumentPrincipal,
    ai_document_read_filter,
    can_read_ai_document,
    principal_for_legacy_args,
    principal_for_user,
)
from app.services.ai.policies.access_policy import (
    PUBLIC_POLICY,
    PUBLIC_TOOL_ALLOWLIST,
    build_ai_access_policy,
)
from app.services.data_retrieval.access import DataAccessPolicy, build_data_access_policy


def _doc(**kw):
    kw.setdefault("title", "t")
    kw.setdefault("filename", "f.pdf")
    kw.setdefault("file_type", "pdf")
    doc = AIDocument(**kw)
    db.session.add(doc)
    db.session.flush()
    return doc


def _readable_ids(principal, ids):
    rows = (
        db.session.query(AIDocument.id)
        .filter(AIDocument.id.in_(ids))
        .filter(ai_document_read_filter(principal))
        .all()
    )
    return {r[0] for r in rows}


class TestDocumentPrincipals:
    def test_anonymous_principal_carries_only_public_token(self):
        assert ANONYMOUS_PRINCIPAL.is_anonymous
        assert ANONYMOUS_PRINCIPAL.role_tokens == frozenset({"public"})

    def test_legacy_bridge_denies_unknown_role_strings(self, app):
        with app.app_context():
            assert principal_for_legacy_args(None, "admin").is_anonymous
            assert principal_for_legacy_args(None, "system_manager").is_internal

    def test_legacy_bridge_ignores_claimed_role_for_real_user(self, app, test_user):
        with app.test_request_context():
            principal = principal_for_legacy_args(test_user.id, "system_manager")
            assert principal.user_id == test_user.id
            assert not principal.is_document_admin

    def test_inactive_user_is_anonymous(self, app, test_user):
        with app.app_context():
            user = db.session.get(type(test_user), test_user.id)
            user.active = False
            assert principal_for_user(user).is_anonymous
            db.session.rollback()


class TestDocumentAclMatrix:
    @pytest.fixture
    def matrix(self, app, db_session, test_user, admin_user, focal_point_user):
        from app.models import Country, User

        with app.app_context():
            other_user = db_session.get(User, test_user.id)
            admin = db_session.get(User, admin_user.id)
            focal = db_session.get(User, focal_point_user["user_id"])
            country = db_session.get(Country, focal_point_user["country_id"])

            docs = {
                "public": _doc(is_public=True, user_id=admin.id),
                "public_focal_only": _doc(is_public=True, allowed_roles=["focal_point"], user_id=admin.id),
                "public_nobody": _doc(is_public=True, allowed_roles=[], user_id=admin.id),
                "public_admin_only": _doc(is_public=True, allowed_roles=["admin"], user_id=admin.id),
                "private_focal": _doc(is_public=False, user_id=focal.id),
                "private_focal_role_list": _doc(is_public=False, allowed_roles=["user"], user_id=focal.id),
                "private_other": _doc(is_public=False, user_id=other_user.id),
                "private_ownerless": _doc(is_public=False, user_id=None),
            }
            db_session.commit()
            yield {
                "docs": docs,
                "ids": [d.id for d in docs.values()],
                "other": other_user,
                "admin": admin,
                "focal": focal,
                "country": country,
            }
            db_session.rollback()
            for d in docs.values():
                obj = db_session.get(AIDocument, d.id)
                if obj is not None:
                    db_session.delete(obj)
            db_session.commit()

    def _expect(self, matrix, principal, expected_names):
        docs = matrix["docs"]
        expected = {docs[n].id for n in expected_names}
        assert _readable_ids(principal, matrix["ids"]) == expected
        py_readable = {d.id for d in docs.values() if can_read_ai_document(principal, d)}
        assert py_readable == expected, "Python and SQL ACL diverged"

    def test_anonymous_sees_only_unrestricted_public(self, app, matrix):
        with app.app_context():
            self._expect(matrix, ANONYMOUS_PRINCIPAL, {"public"})

    def test_same_org_user_sees_public_and_own_only(self, app, matrix):
        with app.test_request_context():
            principal = principal_for_user(matrix["other"])
            self._expect(matrix, principal, {"public", "private_other"})

    def test_allowed_roles_restrict_public_documents(self, app, matrix):
        with app.test_request_context():
            principal = principal_for_user(matrix["focal"])
            self._expect(
                matrix,
                principal,
                {"public", "public_focal_only", "private_focal", "private_focal_role_list"},
            )

    def test_allowed_roles_never_grant_private_document(self, app, matrix):
        with app.test_request_context():
            principal = principal_for_user(matrix["other"])
            assert not can_read_ai_document(principal, matrix["docs"]["private_focal_role_list"])

    def test_admin_reads_everything(self, app, matrix):
        with app.test_request_context():
            principal = principal_for_user(matrix["admin"])
            assert principal.is_document_admin
            self._expect(matrix, principal, set(matrix["docs"]))

    def test_internal_principal_reads_everything(self, app, matrix):
        with app.app_context():
            self._expect(matrix, INTERNAL_PRINCIPAL, set(matrix["docs"]))

    def test_none_document_denied(self):
        assert can_read_ai_document(ANONYMOUS_PRINCIPAL, None) is False

    def test_owner_loses_private_submitted_document_without_country_access(self, app, db_session, matrix):
        from tests.factories import create_test_country

        with app.app_context():
            other_country = create_test_country(db_session)
            doc = AIDocument(
                title="t",
                filename="f.pdf",
                file_type="pdf",
                is_public=False,
                user_id=matrix["focal"].id,
                country_id=other_country.id,
                submitted_document_id=987654,
            )
            principal = DocumentPrincipal(
                user_id=matrix["focal"].id,
                role_tokens=frozenset({"focal_point"}),
                country_ids=frozenset({matrix["country"].id}),
            )
            assert can_read_ai_document(principal, doc) is False
            in_scope = DocumentPrincipal(
                user_id=matrix["focal"].id,
                role_tokens=frozenset({"focal_point"}),
                country_ids=frozenset({other_country.id}),
            )
            assert can_read_ai_document(in_scope, doc) is True


class TestDataAccessPolicy:
    def test_anonymous_policy_public_only(self):
        policy = build_data_access_policy(None)
        assert policy.is_anonymous
        assert not policy.can_read_non_public(1)
        assert policy.allowed_country_ids() == []

    def test_same_org_user_without_country_has_no_non_public(self, app, test_user):
        with app.test_request_context():
            from app.models import User

            user = db.session.get(User, test_user.id)
            policy = build_data_access_policy(user)
            assert policy.principal == "user"
            assert not policy.unrestricted_countries
            assert policy.country_ids == frozenset()
            assert not policy.can_read_non_public(1)

    def test_focal_point_limited_to_assigned_countries(self, app, focal_point_user):
        with app.test_request_context():
            from app.models import User

            user = db.session.get(User, focal_point_user["user_id"])
            policy = build_data_access_policy(user)
            cid = focal_point_user["country_id"]
            assert policy.can_read_non_public(cid)
            assert not policy.can_read_non_public(cid + 9999)
            assert policy.allowed_country_ids() == [cid]

    def test_admin_is_unrestricted(self, app, admin_user):
        with app.test_request_context():
            from app.models import User

            user = db.session.get(User, admin_user.id)
            policy = build_data_access_policy(user)
            assert policy.unrestricted_countries
            assert policy.allowed_country_ids() is None
            assert policy.can_read_non_public(424242)

    def test_elevated_api_key_unrestricted(self):
        policy = build_data_access_policy(None, elevated_api_key=True)
        assert policy.unrestricted_countries
        assert policy.principal == "api_key"

    def test_visible_items_filters_by_privacy(self):
        class Item:
            def __init__(self, privacy):
                self.privacy = privacy

        items = [Item("public"), Item("ifrc_network")]
        anon = DataAccessPolicy()
        assert [i.privacy for i in anon.visible_items(items, 1)] == ["public"]
        scoped = DataAccessPolicy(principal="user", user_id=1, country_ids=frozenset({1}))
        assert len(scoped.visible_items(items, 1)) == 2
        assert len(scoped.visible_items(items, 2)) == 1


class TestToolAllowlist:
    def test_public_policy_is_anonymous(self):
        assert PUBLIC_POLICY.is_anonymous
        assert build_ai_access_policy(None) is PUBLIC_POLICY

    def test_public_policy_allowlist_only(self):
        assert PUBLIC_POLICY.allows_tool("get_indicator_value")
        for name in (
            "get_user_profile",
            "query_database",
            "get_assignment_indicator_values",
            "upload_document",
            "create_form_item",
        ):
            assert not PUBLIC_POLICY.allows_tool(name)

    def test_filter_tool_definitions(self):
        defs = [
            {"type": "function", "function": {"name": "get_indicator_value"}},
            {"type": "function", "function": {"name": "get_assignment_indicator_values"}},
        ]
        out = PUBLIC_POLICY.filter_tool_definitions(defs)
        assert [d["function"]["name"] for d in out] == ["get_indicator_value"]

    def test_allowlist_contains_no_write_or_user_scoped_tools(self):
        forbidden_fragments = ("assignment", "profile", "submit", "create", "update", "delete", "import")
        for name in PUBLIC_TOOL_ALLOWLIST:
            assert not any(f in name for f in forbidden_fragments), name

    def test_authenticated_policy_allows_catalog(self, app, test_user):
        with app.test_request_context():
            from app.models import User

            policy = build_ai_access_policy(db.session.get(User, test_user.id))
            assert not policy.is_anonymous
            assert policy.allows_tool("get_assignment_indicator_values")

    def test_anonymous_source_clamp(self):
        clamped = PUBLIC_POLICY.clamp_sources({"historical": True, "system_documents": True, "evil": True})
        assert set(clamped) == {"historical", "system_documents", "upr_documents"}
        assert clamped["upr_documents"] is False
