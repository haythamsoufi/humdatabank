import json
import uuid as _uuid
from unittest.mock import patch

import pytest

from app.models import (
    AssignedForm,
    AssignmentEntityStatus,
    DynamicIndicatorData,
    FormItem,
    FormSection,
    IndicatorBank,
    LookupList,
    LookupListRow,
    RepeatGroupInstance,
)
from app.models.enums import EntityType

from tests.factories import create_test_country, create_test_template, create_test_user


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


@pytest.mark.integration
class TestEntryFormFormsApiLookupLists:
    def test_lookup_list_options_returns_rows(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            ll = LookupList(
                name=f"Options List {_uuid.uuid4().hex[:8]}",
                columns_config=[{"name": "name", "type": "string"}],
            )
            db_session.add(ll)
            db_session.flush()
            ll_id = ll.id
            db_session.add(LookupListRow(lookup_list_id=ll_id, order=1, data={"name": "A"}))
            db_session.add(LookupListRow(lookup_list_id=ll_id, order=2, data={"name": "B"}))
            db_session.commit()

            resp = client.get(
                f"/api/forms/lookup-lists/{ll_id}/options",
                query_string={"filters": "[]", "field_values": "{}"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["rows"] == [{"name": "A"}, {"name": "B"}]


@pytest.mark.integration
class TestEntryFormFormsApiRepeatInstances:
    def test_repeat_instance_toggle_hide(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            section = FormSection(
                template_id=template.id,
                name="Repeat",
                order=1,
                version_id=template.published_version_id,
                section_type="repeat",
            )
            db_session.add(section)
            db_session.flush()

            inst = RepeatGroupInstance(
                section_id=section.id,
                assignment_entity_status_id=aes.id,
                instance_number=1,
                created_by_user_id=user.id,
            )
            db_session.add(inst)
            db_session.flush()
            inst_id = inst.id
            db_session.commit()

            resp = client.patch(f"/api/forms/repeat-instances/{inst_id}/toggle-hide")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["is_hidden"] is True


@pytest.mark.integration
class TestEntryFormFormsApiDynamicIndicators:
    def test_dynamic_indicators_add_happy_path(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id

            section = FormSection(
                template_id=template.id,
                name="Dyn",
                order=1,
                version_id=template.published_version_id,
                section_type="dynamic_indicators",
            )
            db_session.add(section)
            db_session.flush()
            section_id = section.id

            indicator = IndicatorBank(
                name=f"Indicator X {_uuid.uuid4().hex[:8]}",
                type="number", archived=False, emergency=False,
            )
            db_session.add(indicator)
            db_session.flush()
            indicator_id = indicator.id
            db_session.commit()

            payload = {
                "assignment_entity_status_id": aes_id,
                "section_id": section_id,
                "indicator_bank_id": indicator_id,
                "custom_label": "Custom X",
            }

            # Avoid the access gate complexity; validate our endpoint contract instead
            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}):
                resp = client.post(
                    "/api/forms/dynamic-indicators/add",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["success"] is True
                assert data["assignment"]["indicator_bank_id"] == indicator_id
                assert data["assignment"]["name"] == "Custom X"

    def test_dynamic_indicators_add_requires_dynamic_section(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id

            section = FormSection(
                template_id=template.id,
                name="NotDyn",
                order=1,
                version_id=template.published_version_id,
                section_type="standard",
            )
            db_session.add(section)
            db_session.flush()
            section_id = section.id

            indicator = IndicatorBank(
                name=f"Indicator Y {_uuid.uuid4().hex[:8]}",
                type="number", archived=False, emergency=False,
            )
            db_session.add(indicator)
            db_session.flush()
            indicator_id = indicator.id
            db_session.commit()

            payload = {
                "assignment_entity_status_id": aes_id,
                "section_id": section_id,
                "indicator_bank_id": indicator_id,
            }
            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}):
                resp = client.post(
                    "/api/forms/dynamic-indicators/add",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                assert resp.status_code == 400
                data = resp.get_json()
                assert "Section is not a dynamic indicators section" in (data.get("error") or "")

    def test_render_pending_dynamic_indicator_returns_html(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id

            section = FormSection(
                template_id=template.id,
                name="Dyn Render",
                order=1,
                version_id=template.published_version_id,
                section_type="dynamic_indicators",
            )
            db_session.add(section)
            db_session.flush()
            section_id = section.id

            indicator = IndicatorBank(
                name=f"Indicator Render {_uuid.uuid4().hex[:8]}",
                type="number",
                archived=False,
                emergency=False,
            )
            db_session.add(indicator)
            db_session.flush()
            indicator_id = indicator.id
            indicator_name = indicator.name
            db_session.commit()

            temp_assignment_id = "pending_test_1"
            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}):
                resp = client.post(
                    "/api/forms/dynamic-indicators/render-pending",
                    data={
                        "assignment_entity_status_id": aes_id,
                        "section_id": section_id,
                        "indicator_bank_id": indicator_id,
                        "temp_assignment_id": temp_assignment_id,
                    },
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            html = data["html"]
            assert isinstance(html, str) and html.strip()
            assert f'data-assignment-id="{temp_assignment_id}"' in html
            assert indicator_name in html

    def test_render_dynamic_indicator_returns_html(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)

            section = FormSection(
                template_id=template.id,
                name="Dyn Render Saved",
                order=1,
                version_id=template.published_version_id,
                section_type="dynamic_indicators",
            )
            db_session.add(section)
            db_session.flush()
            section_id = section.id

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id

            indicator = IndicatorBank(
                name=f"Indicator Saved Render {_uuid.uuid4().hex[:8]}",
                type="number",
                archived=False,
                emergency=False,
            )
            db_session.add(indicator)
            db_session.flush()
            indicator_id = indicator.id

            dynamic_assignment = DynamicIndicatorData(
                assignment_entity_status_id=aes_id,
                section_id=section_id,
                indicator_bank_id=indicator_id,
                added_by_user_id=user.id,
                value="456",
            )
            db_session.add(dynamic_assignment)
            db_session.flush()
            assignment_id = dynamic_assignment.id
            indicator_name = indicator.name
            db_session.commit()

            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}):
                resp = client.get(f"/api/forms/dynamic-indicators/{assignment_id}/render")

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            html = data["html"]
            assert isinstance(html, str) and html.strip()
            assert f'data-assignment-id="{assignment_id}"' in html
            assert indicator_name in html
            assert 'value="456"' in html


@pytest.mark.integration
class TestEntryFormFormsApiPresence:
    def test_presence_sync_returns_success(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            db_session.commit()

            with patch("app.routes.forms_api.check_aes_access_light", return_value=True), \
                 patch("app.utils.user_analytics.log_user_activity", return_value=None):
                resp = client.post(f"/api/forms/presence/assignment/{aes_id}/sync")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["success"] is True
                assert isinstance(data["users"], list)

    def test_presence_leave_returns_success(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            db_session.commit()

            with patch("app.utils.user_analytics.log_user_activity", return_value=None):
                resp = client.post(f"/api/forms/presence/assignment/{aes_id}/leave")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["success"] is True

    def test_presence_heartbeat_returns_success(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            # Create a minimal AES for access checks
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            db_session.commit()

            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}), \
                 patch("app.utils.user_analytics.log_user_activity", return_value=None):
                resp = client.post(f"/api/forms/presence/assignment/{aes_id}/heartbeat")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["success"] is True


@pytest.mark.integration
class TestEntryFormFormsApiDynamicIndicatorsUpdate:
    def test_dynamic_indicators_update_happy_path(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)

            section = FormSection(
                template_id=template.id,
                name="Dyn Update",
                order=1,
                version_id=template.published_version_id,
                section_type="dynamic_indicators",
            )
            db_session.add(section)
            db_session.flush()
            section_id = section.id

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id

            indicator = IndicatorBank(
                name=f"Indicator Update {_uuid.uuid4().hex[:8]}",
                type="number",
                archived=False,
                emergency=False,
            )
            db_session.add(indicator)
            db_session.flush()
            indicator_id = indicator.id

            dynamic_assignment = DynamicIndicatorData(
                assignment_entity_status_id=aes_id,
                section_id=section_id,
                indicator_bank_id=indicator_id,
                added_by_user_id=user.id,
            )
            db_session.add(dynamic_assignment)
            db_session.flush()
            assignment_id = dynamic_assignment.id
            db_session.commit()

            with patch("app.routes.forms_api.check_country_access", return_value=True):
                resp = client.put(
                    f"/api/forms/dynamic-indicators/{assignment_id}/update",
                    data=json.dumps({"custom_label": "Updated Label", "order": 2}),
                    content_type="application/json",
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True

            updated = db_session.get(DynamicIndicatorData, assignment_id)
            assert updated.custom_label == "Updated Label"
            assert updated.order == 2

    def test_dynamic_indicators_update_unknown_id(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            resp = client.put(
                "/api/forms/dynamic-indicators/999999/update",
                data=json.dumps({"custom_label": "Nope"}),
                content_type="application/json",
            )
            assert resp.status_code in (404, 500)


@pytest.mark.integration
class TestEntryFormFormsApiDynamicIndicatorsRemove:
    def test_dynamic_indicators_remove_happy_path(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)

            section = FormSection(
                template_id=template.id,
                name="Dyn Remove",
                order=1,
                version_id=template.published_version_id,
                section_type="dynamic_indicators",
            )
            db_session.add(section)
            db_session.flush()
            section_id = section.id

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id

            indicator = IndicatorBank(
                name=f"Indicator Remove {_uuid.uuid4().hex[:8]}",
                type="number",
                archived=False,
                emergency=False,
            )
            db_session.add(indicator)
            db_session.flush()
            indicator_id = indicator.id

            dynamic_assignment = DynamicIndicatorData(
                assignment_entity_status_id=aes_id,
                section_id=section_id,
                indicator_bank_id=indicator_id,
                added_by_user_id=user.id,
            )
            db_session.add(dynamic_assignment)
            db_session.flush()
            assignment_id = dynamic_assignment.id
            db_session.commit()

            with patch("app.routes.forms_api.check_country_access", return_value=True):
                resp = client.delete(f"/api/forms/dynamic-indicators/{assignment_id}/remove")

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert db_session.get(DynamicIndicatorData, assignment_id) is None

    def test_dynamic_indicators_remove_unknown_id(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            resp = client.delete("/api/forms/dynamic-indicators/999999/remove")
            assert resp.status_code in (404, 500)


@pytest.mark.integration
class TestEntryFormFormsApiPresenceActiveUsers:
    def test_presence_active_users_returns_list(self, client, db_session, app):
        with app.app_context():
            from datetime import datetime, timezone

            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            db_session.commit()

            now = datetime.now(timezone.utc)
            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}), \
                 patch(
                     "app.routes.forms_api.get_active_presence",
                     return_value={user.id: now},
                 ):
                resp = client.get(f"/api/forms/presence/assignment/{aes_id}/active-users")

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert isinstance(data["users"], list)
            assert len(data["users"]) == 1
            assert data["users"][0]["id"] == user.id


@pytest.mark.integration
class TestEntryFormFormsApiEntryBootstrap:
    """Covers /api/forms/assignment/<id>/entry-bootstrap (see 2026-07-17 handover:
    'defer page-load requests'). Focuses on the behaviors that were reviewed/fixed:
    auth/access gating, the no-published-version short circuit, skipping matrices
    that are not configured for auto-load, and — most importantly — that the
    per-matrix auto-load + variable-resolve work is deduplicated into a single
    assignment-level resolve and a single batch resolve regardless of how many
    matrices/columns are involved (HIGH #3 fix in forms_api.py).
    """

    def _make_assignment(self, db_session, template=None):
        country = create_test_country(db_session)
        template = template or create_test_template(db_session)
        assigned_form = AssignedForm(template_id=template.id, period_name="2024")
        db_session.add(assigned_form)
        db_session.flush()
        aes = AssignmentEntityStatus(
            assigned_form_id=assigned_form.id,
            entity_type=EntityType.country.value,
            entity_id=country.id,
            status="in_progress",
        )
        db_session.add(aes)
        db_session.flush()
        db_session.commit()
        return template, aes

    def test_requires_login(self, client, db_session, app):
        with app.app_context():
            _, aes = self._make_assignment(db_session)
            resp = client.get(f"/api/forms/assignment/{aes.id}/entry-bootstrap")
            assert resp.status_code in (302, 401)

    def test_unknown_assignment_returns_403(self, client, db_session, app):
        # check_aes_access_light() runs before the not-found lookup and returns False
        # for a nonexistent id, so this — like an access-denied case — surfaces as 403
        # rather than 404 (avoids revealing whether the id exists to unauthorized/absent
        # records).
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            resp = client.get("/api/forms/assignment/999999999/entry-bootstrap")
            assert resp.status_code == 403

    def test_forbidden_without_entity_access(self, client, db_session, app):
        with app.app_context():
            _, aes = self._make_assignment(db_session)
            aes_id = aes.id
            # No entity permissions granted; a plain non-admin user must be denied.
            user = create_test_user(db_session, role="user")
            _login(client, user.id)
            resp = client.get(f"/api/forms/assignment/{aes_id}/entry-bootstrap")
            assert resp.status_code == 403

    def test_no_published_version_returns_zeroed_defaults(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            template = create_test_template(db_session, status="draft")
            template.published_version_id = None
            db_session.commit()

            _, aes = self._make_assignment(db_session, template=template)

            resp = client.get(f"/api/forms/assignment/{aes.id}/entry-bootstrap")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["completion_rate"] == 0.0
            assert data["auto_load"] == {}
            assert data["resolved_variables"] == {}

    def test_happy_path_no_matrices(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            _, aes = self._make_assignment(db_session)

            resp = client.get(f"/api/forms/assignment/{aes.id}/entry-bootstrap")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["completion_rate"] == 0.0
            assert data["auto_load"] == {}
            assert data["resolved_variables"] == {}

    def test_matrix_without_auto_load_config_is_skipped(self, client, db_session, app):
        """A matrix FormItem that isn't configured for auto-load must contribute
        nothing to `auto_load` and must not trigger any variable-resolution calls
        (the cheap `_matrix_uses_auto_load` pre-filter added in the HIGH #3 fix)."""
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            template, aes = self._make_assignment(db_session)
            section = FormSection(
                template_id=template.id,
                version_id=template.published_version_id,
                name="Matrix Section",
                order=1,
            )
            db_session.add(section)
            db_session.flush()
            db_session.add(FormItem(
                section_id=section.id,
                version_id=template.published_version_id,
                template_id=template.id,
                item_type='matrix',
                label='No auto-load',
                order=1,
                config={'matrix_config': {'auto_load_entities': False, 'row_mode': 'list_library'}},
            ))
            db_session.commit()

            with patch(
                "app.services.forms.variable_resolution_service.VariableResolutionService.resolve_variables"
            ) as mock_resolve:
                resp = client.get(f"/api/forms/assignment/{aes.id}/entry-bootstrap")

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["auto_load"] == {}
            # No variable_configs on this template either, so resolve_variables should
            # never even be attempted — belt-and-suspenders confirmation of the skip.
            mock_resolve.assert_not_called()

    def test_forward_lookup_auto_load_populates_entities(self, client, db_session, app):
        """A forward-lookup ('same') matrix column should surface entities returned
        by `_resolve_auto_load_entities_inner` under `auto_load[<form_item_id>]`."""
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            template, aes = self._make_assignment(db_session)
            version_id = template.published_version_id

            from app.models import FormTemplateVersion
            version = db_session.get(FormTemplateVersion, version_id)
            version.variables = {
                'my_var': {
                    'entity_scope': 'same',
                    'source_template_id': 999,
                    'source_assignment_period': '2024',
                    'source_form_item_id': 111,
                }
            }
            db_session.commit()

            section = FormSection(
                template_id=template.id,
                version_id=version_id,
                name="Matrix Section",
                order=1,
            )
            db_session.add(section)
            db_session.flush()
            matrix_item = FormItem(
                section_id=section.id,
                version_id=version_id,
                template_id=template.id,
                item_type='matrix',
                label='Auto-load matrix',
                order=1,
                config={
                    'matrix_config': {
                        'auto_load_entities': True,
                        'row_mode': 'list_library',
                        'columns': [
                            {'name': 'my_col', 'is_variable': True, 'variable': 'my_var', 'type': 'text'},
                        ],
                    }
                },
            )
            db_session.add(matrix_item)
            db_session.commit()
            matrix_item_id = matrix_item.id

            fake_result = {
                'entities': [{'entity_id': 42, 'entity_type': 'country'}],
                'entity_type': 'country',
            }
            with patch(
                "app.routes.api.assignments._resolve_auto_load_entities_inner",
                return_value=fake_result,
            ) as mock_inner:
                resp = client.get(f"/api/forms/assignment/{aes.id}/entry-bootstrap")

            assert resp.status_code == 200
            data = resp.get_json()
            assert str(matrix_item_id) in data["auto_load"]
            assert data["auto_load"][str(matrix_item_id)]["entities"] == [
                {'entity_id': 42, 'entity_type': 'country'}
            ]
            assert data["auto_load"][str(matrix_item_id)]["entity_type"] == 'country'
            # Forward-lookup entities are already tick-filtered server-side inside
            # _resolve_auto_load_entities_inner (called once here for the one column).
            assert mock_inner.call_count == 1

    def test_reverse_lookup_and_saved_rows_share_one_batch_resolve(self, client, db_session, app):
        """Reverse-lookup ('entities_containing') tick filtering and resolved_variables
        for already-saved matrix rows must be served by exactly ONE
        `resolve_variables_batch` call (HIGH #3: previously one batch call per
        reverse-lookup matrix, plus a second, separate call for saved rows)."""
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            template, aes = self._make_assignment(db_session)
            version_id = template.published_version_id

            from app.models import FormTemplateVersion
            version = db_session.get(FormTemplateVersion, version_id)
            version.variables = {
                'rev_var': {
                    'entity_scope': 'entities_containing',
                }
            }
            db_session.commit()

            section = FormSection(
                template_id=template.id,
                version_id=version_id,
                name="Matrix Section",
                order=1,
            )
            db_session.add(section)
            db_session.flush()
            matrix_item = FormItem(
                section_id=section.id,
                version_id=version_id,
                template_id=template.id,
                item_type='matrix',
                label='Reverse auto-load matrix',
                order=1,
                config={
                    'matrix_config': {
                        'auto_load_entities': True,
                        'row_mode': 'list_library',
                        'columns': [
                            {
                                'name': 'tick_col', 'is_variable': True, 'variable': 'rev_var',
                                'type': 'tick',
                            },
                        ],
                    }
                },
            )
            db_session.add(matrix_item)
            db_session.commit()
            matrix_item_id = matrix_item.id

            # Assignment-level resolve returns the auto_load_format JSON blob for the
            # reverse variable, listing two candidate entities.
            assignment_level_resolved = {
                'rev_var': json.dumps({
                    'entity_type': 'country',
                    'entities': [
                        {'entity_id': 7, 'entity_type': 'country'},
                        {'entity_id': 8, 'entity_type': 'country'},
                    ],
                }),
            }
            # Only entity 7 has the tick column set — entity 8 must be filtered out.
            batch_resolve_result = {
                7: {'rev_var': 1},
                8: {'rev_var': 0},
            }

            with patch(
                "app.services.forms.variable_resolution_service.VariableResolutionService.resolve_variables",
                return_value=assignment_level_resolved,
            ) as mock_resolve, patch(
                "app.services.forms.variable_resolution_service.VariableResolutionService.resolve_variables_batch",
                return_value=batch_resolve_result,
            ) as mock_batch:
                resp = client.get(f"/api/forms/assignment/{aes.id}/entry-bootstrap")

            assert resp.status_code == 200
            data = resp.get_json()

            assert data["auto_load"][str(matrix_item_id)]["entities"] == [
                {'entity_id': 7, 'entity_type': 'country'}
            ]
            assert data["resolved_variables"]["7"] == {'rev_var': 1}
            assert data["resolved_variables"]["8"] == {'rev_var': 0}

            # Deduplication: exactly one assignment-level resolve (shared for the
            # reverse-lookup parse AND resolved_variables['']), and exactly one batch
            # resolve (covering both the reverse+tick filter and saved-row resolve).
            assert mock_resolve.call_count == 1
            assert mock_batch.call_count == 1
            batch_call_entity_ids = set(mock_batch.call_args.args[2])
            assert batch_call_entity_ids == {7, 8}
