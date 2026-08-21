"""UPR visuals assignment PDF routes."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_live_assignment_pdf_route_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/assignment/42/pdf")
    assert endpoint == "upr_visuals.assignment_pdf"
    assert values == {"aes_id": 42}


@pytest.mark.unit
def test_dashboard_assignment_pdf_route_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/assignment/42/pdf/combined")
    assert endpoint == "upr_visuals.assignment_pdf_dashboard"
    assert values == {"aes_id": 42, "dashboard_id": "combined"}


@pytest.mark.unit
def test_live_assignment_pdf_requires_login(client):
    response = client.get("/assignment/42/pdf")
    assert response.status_code in (302, 401)
