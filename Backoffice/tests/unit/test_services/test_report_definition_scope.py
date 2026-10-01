"""Scope resolution for report definitions."""

import pytest

from app.services.reports.definition_service import resolve_user_scope
from tests.factories import create_test_user


@pytest.mark.unit
def test_resolve_user_scope_passes_user_object_to_country_lookup(app, db_session):
    """Restricted users must not pass a raw id into _get_user_allowed_country_ids.

    That helper reads auth_user.id and RBAC methods on the user. Passing user.id
    raises AttributeError and the reports metadata API returns an HTML error page.
    """
    with app.app_context():
        user = create_test_user(db_session)
        scope = resolve_user_scope(user)
        assert scope["country_ids"] == set()
        assert isinstance(scope["template_ids"], list)
