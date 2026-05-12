import pytest
from unittest.mock import patch

from app.models import AssignedForm, FormData, FormItem, FormSection, FormTemplate
from app.models.assignments import AssignmentEntityStatus
from app.models.enums import EntityType

from tests.factories import create_test_country, create_test_template, create_test_user


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _get_csrf_headers(client) -> dict:
    """
    Fetch a CSRF token using the dedicated endpoint and return request headers.

    Mirrors the MobileApp (Path A) flow: after login, fetch a token from
    `/api/v1/csrf-token` and send it back on unsafe JSON requests via X-CSRFToken.
    """
    resp = client.get("/api/v1/csrf-token")
    assert resp.status_code == 200
    data = resp.get_json() or {}
    token = data.get("csrf_token")
    assert token
    return {"X-CSRFToken": token}


@pytest.mark.integration
class TestEntryFormVariablesResolveApi:
    def test_variables_resolve_requires_body(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)
            # Send empty JSON so Content-Type is set; endpoint should reject missing fields
            resp = client.post("/api/v1/variables/resolve", json={}, headers=headers)
            assert resp.status_code == 400

    def test_variables_resolve_missing_required_fields_returns_400(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            resp = client.post(
                "/api/v1/variables/resolve",
                json={"assignment_entity_status_id": 123},
                headers=headers,
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert (data or {}).get("error")

    def test_variables_resolve_assignment_entity_status_not_found_returns_404(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            resp = client.post(
                "/api/v1/variables/resolve",
                json={"assignment_entity_status_id": 999999, "template_id": 1},
                headers=headers,
            )
            assert resp.status_code == 404
            data = resp.get_json()
            assert (data or {}).get("error") == "Assignment entity status not found"

    def test_variables_resolve_access_denied_returns_403(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            template_id = template.id
            db_session.commit()

            with patch(
                "app.services.authorization_service.AuthorizationService.can_access_assignment",
                return_value=False,
            ):
                resp = client.post(
                    "/api/v1/variables/resolve",
                    json={"assignment_entity_status_id": aes_id, "template_id": template_id, "row_entity_id": 1},
                    headers=headers,
                )
                assert resp.status_code == 403
                data = resp.get_json()
                assert (data or {}).get("error") == "Access denied"

    def test_variables_resolve_template_not_found_returns_404(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            db_session.commit()

            with patch(
                "app.services.authorization_service.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/variables/resolve",
                    json={"assignment_entity_status_id": aes_id, "template_id": 999999, "row_entity_id": 1},
                    headers=headers,
                )
                assert resp.status_code == 404
                data = resp.get_json()
                assert (data or {}).get("error") == "Template not found"

    def test_variables_resolve_template_no_published_version_returns_404(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            # Create a template without published version
            tpl = FormTemplate()
            db_session.add(tpl)
            db_session.flush()
            template_id = tpl.id

            assigned_form = AssignedForm(template_id=template_id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            db_session.commit()

            with patch(
                "app.services.authorization_service.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/variables/resolve",
                    json={"assignment_entity_status_id": aes_id, "template_id": template_id, "row_entity_id": 1},
                    headers=headers,
                )
                assert resp.status_code == 404
                data = resp.get_json()
                assert (data or {}).get("error") == "Template version not found"

    def test_variables_resolve_single_row_happy_path_contract(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            template_id = template.id
            db_session.commit()

            with patch(
                "app.services.authorization_service.AuthorizationService.can_access_assignment",
                return_value=True,
            ), patch(
                "app.services.variable_resolution_service.VariableResolutionService.resolve_variables",
                return_value={"FOO": "bar"},
            ) as mock_resolve:
                resp = client.post(
                    "/api/v1/variables/resolve",
                    json={"assignment_entity_status_id": aes_id, "template_id": template_id, "row_entity_id": 777},
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["variables"]["FOO"] == "bar"
                assert mock_resolve.call_args.kwargs.get("row_entity_id") == 777

    def test_variables_resolve_batch_happy_path(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            template_id = template.id
            db_session.commit()

            with patch(
                "app.services.authorization_service.AuthorizationService.can_access_assignment",
                return_value=True,
            ), patch(
                "app.services.variable_resolution_service.VariableResolutionService.resolve_variables_batch",
                return_value={1: {"FOO": "bar"}, 2: {"FOO": "baz"}},
            ):
                resp = client.post(
                    "/api/v1/variables/resolve",
                    json={
                        "assignment_entity_status_id": aes_id,
                        "template_id": template_id,
                        "row_entity_ids": [1, 2],
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert "results" in data
                # JSON object keys are strings; JS will access by numeric id which coerces to string.
                assert data["results"]["1"]["FOO"] == "bar"


@pytest.mark.integration
class TestEntryFormMatrixAutoLoadEntitiesApi:
    def _create_form_item(self, db_session, template) -> int:
        section = FormSection(
            template_id=template.id,
            version_id=template.published_version_id,
            name="Matrix Section",
            order=1,
        )
        db_session.add(section)
        db_session.flush()

        form_item = FormItem(
            section_id=section.id,
            template_id=template.id,
            version_id=template.published_version_id,
            item_type="indicator",
            label="Matrix Field",
            order=1,
        )
        db_session.add(form_item)
        db_session.flush()
        db_session.commit()
        return form_item.id

    def _create_assignment_entity_status(self, db_session, template, period_name: str, entity_id: int) -> AssignmentEntityStatus:
        assigned_form = AssignedForm(template_id=template.id, period_name=period_name)
        db_session.add(assigned_form)
        db_session.flush()

        aes = AssignmentEntityStatus(
            assigned_form_id=assigned_form.id,
            entity_type=EntityType.country.value,
            entity_id=entity_id,
            status="In Progress",
        )
        db_session.add(aes)
        db_session.flush()
        db_session.commit()
        return aes

    def test_auto_load_entities_requires_body(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)
            # Send empty JSON so Content-Type is set; endpoint should reject missing fields
            resp = client.post("/api/v1/matrix/auto-load-entities", json={}, headers=headers)
            assert resp.status_code == 400

    def test_auto_load_entities_missing_any_required_param_returns_400(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            resp = client.post(
                "/api/v1/matrix/auto-load-entities",
                json={
                    "source_template_id": 1,
                    "source_assignment_period": "2024",
                    # missing source_form_item_id
                    "assignment_entity_status_id": 1,
                },
                headers=headers,
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert (data or {}).get("error") == "All parameters are required"

    def test_auto_load_entities_assignment_entity_status_not_found_returns_404(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            resp = client.post(
                "/api/v1/matrix/auto-load-entities",
                json={
                    "source_template_id": 1,
                    "source_assignment_period": "2024",
                    "source_form_item_id": 1,
                    "assignment_entity_status_id": 999999,
                },
                headers=headers,
            )
            assert resp.status_code == 404
            data = resp.get_json()
            assert (data or {}).get("error") == "Assignment entity status not found"

    def test_auto_load_entities_access_denied_returns_403(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            current_aes = self._create_assignment_entity_status(db_session, template, "2024", country.id)

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=False,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": template.id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": 1,
                        "assignment_entity_status_id": current_aes.id,
                    },
                    headers=headers,
                )
                assert resp.status_code == 403
                data = resp.get_json()
                assert (data or {}).get("error") == "Access denied"

    def test_auto_load_entities_no_source_assignment_returns_empty(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            template_id = template.id
            db_session.commit()

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": template_id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": 1,
                        "assignment_entity_status_id": aes_id,
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["entities"] == []
                assert data.get("reason") == "no_source_assignment"

    def test_auto_load_entities_no_matching_entity_in_source_returns_empty(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            current_country = create_test_country(db_session)
            other_country = create_test_country(db_session)
            current_template = create_test_template(db_session)
            source_template = create_test_template(db_session)

            current_aes = self._create_assignment_entity_status(db_session, current_template, "2024", current_country.id)

            # Source assignment exists, but entity does not match current
            _source_assigned_form = AssignedForm(template_id=source_template.id, period_name="1999")
            db_session.add(_source_assigned_form)
            db_session.flush()
            db_session.add(
                AssignmentEntityStatus(
                    assigned_form_id=_source_assigned_form.id,
                    entity_type=EntityType.country.value,
                    entity_id=other_country.id,
                    status="In Progress",
                )
            )
            db_session.commit()

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": source_template.id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": 1,
                        "assignment_entity_status_id": current_aes.id,
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["entities"] == []
                assert data.get("reason") == "no_matching_entity_in_source"

    def test_auto_load_entities_no_form_data_returns_reason(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            current_template = create_test_template(db_session)
            source_template = create_test_template(db_session)

            current_aes = self._create_assignment_entity_status(db_session, current_template, "2024", country.id)

            # Source assignment with matching entity status, but no FormData rows
            source_assigned_form = AssignedForm(template_id=source_template.id, period_name="1999")
            db_session.add(source_assigned_form)
            db_session.flush()
            source_aes = AssignmentEntityStatus(
                assigned_form_id=source_assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(source_aes)
            db_session.flush()

            source_form_item_id = self._create_form_item(db_session, source_template)

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": source_template.id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": source_form_item_id,
                        "assignment_entity_status_id": current_aes.id,
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["entities"] == []
                assert data.get("reason") == "no_form_data"
                assert isinstance(data.get("debug_info"), dict)

    def test_auto_load_entities_no_entity_keys_in_data_returns_reason(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            current_template = create_test_template(db_session)
            source_template = create_test_template(db_session)

            current_aes = self._create_assignment_entity_status(db_session, current_template, "2024", country.id)

            source_assigned_form = AssignedForm(template_id=source_template.id, period_name="1999")
            db_session.add(source_assigned_form)
            db_session.flush()
            source_aes = AssignmentEntityStatus(
                assigned_form_id=source_assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(source_aes)
            db_session.flush()

            source_form_item_id = self._create_form_item(db_session, source_template)
            db_session.add(
                FormData(
                    assignment_entity_status_id=source_aes.id,
                    form_item_id=source_form_item_id,
                    disagg_data={"_table": "country"},
                )
            )
            db_session.commit()

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": source_template.id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": source_form_item_id,
                        "assignment_entity_status_id": current_aes.id,
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["entities"] == []
                assert data.get("reason") == "no_entity_keys_in_data"

    def test_auto_load_entities_happy_path_extracts_entities(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            current_template = create_test_template(db_session)
            source_template = create_test_template(db_session)
            current_aes = self._create_assignment_entity_status(db_session, current_template, "2024", country.id)

            source_assigned_form = AssignedForm(template_id=source_template.id, period_name="1999")
            db_session.add(source_assigned_form)
            db_session.flush()
            source_aes = AssignmentEntityStatus(
                assigned_form_id=source_assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(source_aes)
            db_session.flush()

            source_form_item_id = self._create_form_item(db_session, source_template)
            db_session.add(
                FormData(
                    assignment_entity_status_id=source_aes.id,
                    form_item_id=source_form_item_id,
                    disagg_data={
                        "_table": "country",
                        "61_SP1": 0,
                        "62_SP2": 123,
                    },
                )
            )
            db_session.commit()

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": source_template.id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": source_form_item_id,
                        "assignment_entity_status_id": current_aes.id,
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data.get("entity_type") == "country"
                entities = data.get("entities") or []
                entity_ids = {e["entity_id"] for e in entities}
                assert entity_ids == {61, 62}
                assert all(e["entity_type"] == "country" for e in entities)

    def test_auto_load_entities_tick_filtering_includes_only_ticked(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            current_template = create_test_template(db_session)
            source_template = create_test_template(db_session)
            current_aes = self._create_assignment_entity_status(db_session, current_template, "2024", country.id)

            source_assigned_form = AssignedForm(template_id=source_template.id, period_name="1999")
            db_session.add(source_assigned_form)
            db_session.flush()
            source_aes = AssignmentEntityStatus(
                assigned_form_id=source_assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(source_aes)
            db_session.flush()

            source_form_item_id = self._create_form_item(db_session, source_template)
            db_session.add(
                FormData(
                    assignment_entity_status_id=source_aes.id,
                    form_item_id=source_form_item_id,
                    disagg_data={
                        "_table": "country",
                        "61_TICK": 1,
                        "62_TICK": 0,
                        # Validate effective value selection for {original, modified} structure
                        "63_TICK": {"original": 0, "modified": 1},
                    },
                )
            )
            db_session.commit()

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": source_template.id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": source_form_item_id,
                        "assignment_entity_status_id": current_aes.id,
                        "require_tick_value_1": True,
                        "tick_column_names": ["TICK"],
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                entities = data.get("entities") or []
                entity_ids = {e["entity_id"] for e in entities}
                assert entity_ids == {61, 63}

    def test_auto_load_entities_tick_filtering_all_filtered_sets_reason(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            headers = _get_csrf_headers(client)

            country = create_test_country(db_session)
            current_template = create_test_template(db_session)
            source_template = create_test_template(db_session)
            current_aes = self._create_assignment_entity_status(db_session, current_template, "2024", country.id)

            source_assigned_form = AssignedForm(template_id=source_template.id, period_name="1999")
            db_session.add(source_assigned_form)
            db_session.flush()
            source_aes = AssignmentEntityStatus(
                assigned_form_id=source_assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress",
            )
            db_session.add(source_aes)
            db_session.flush()

            source_form_item_id = self._create_form_item(db_session, source_template)
            db_session.add(
                FormData(
                    assignment_entity_status_id=source_aes.id,
                    form_item_id=source_form_item_id,
                    disagg_data={
                        "_table": "country",
                        "61_TICK": 0,
                        "62_TICK": 0,
                    },
                )
            )
            db_session.commit()

            with patch(
                "app.routes.api.assignments.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    "/api/v1/matrix/auto-load-entities",
                    json={
                        "source_template_id": source_template.id,
                        "source_assignment_period": "1999",
                        "source_form_item_id": source_form_item_id,
                        "assignment_entity_status_id": current_aes.id,
                        "require_tick_value_1": True,
                        "tick_column_names": ["TICK"],
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data.get("entities") == []
                assert data.get("reason") == "all_filtered_by_tick"
