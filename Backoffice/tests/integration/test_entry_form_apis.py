import json
import uuid as _uuid
from unittest.mock import patch

import pytest

from app.models import (
    AssignedForm,
    AssignmentEntityStatus,
    DynamicIndicatorData,
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


@pytest.mark.integration
class TestEntryFormFormsApiPresence:
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
