"""The monitoring plan follows the GO application's sectors, indicators, and activities."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.indicator_bank import IndicatorBank, Sector
from plugins.dref_monitoring.models import DrefOperation
from plugins.dref_monitoring.services.entry_activities import (
    activities_by_section,
    indicators_missing_from_template,
    plan_indicator_filter,
)
from plugins.dref_monitoring.services.go_application import application_from_emergency
from plugins.dref_monitoring.services.go_sync import apply_rows
from plugins.dref_monitoring.services.plans import (
    activities_for,
    groups_for,
    indicators_for_group,
    latest_plan,
    refresh_indicator_matches,
)
from tests.factories import create_test_country

pytestmark = pytest.mark.db


def _row(**overrides):
    base = {
        "id": "Dref-app",
        "appeal_code": "MDRAPP01",
        "appeal_type": "DREF",
        "pillar": "Response",
        "country": "Zedland",
        "country_iso3": "ZZZ",
        "disaster_name": "Zedland Flood",
        "total_approved": 10000,
        "amount_approved": 10000,
        "people_targeted": 100,
        "start_date_of_operation": "2026-01-01",
        "end_date_of_operation": "2026-03-31",
        "operation_timeframe": 3,
        "operation_status": "active",
        "is_latest_stage": True,
        "sector_health": True,
        "sector_health_budget": 8000,
        "sector_health_people_targeted": 80,
        "date_of_approval": "2026-01-05",
    }
    base.update(overrides)
    return base


def test_an_activity_is_placed_under_the_indicator_it_names():
    from types import SimpleNamespace

    from plugins.dref_monitoring.services.plans import indicator_for_activity

    indicators = [
        SimpleNamespace(id=1, title="Number of households receiving multipurpose cash transfers."),
        SimpleNamespace(id=2, title="Percentage of beneficiary households satisfied with the monetary assistance received."),
        SimpleNamespace(id=3, title="Number of post-distribution monitoring exercises performed."),
    ]
    delivery = indicator_for_activity("Delivery of multipurpose cash transfers to affected households.", indicators)
    meetings = indicator_for_activity("Holding community meetings for information and consultation.", [
        SimpleNamespace(id=4, title="Number of community information and consultation meetings held"),
        SimpleNamespace(id=5, title="Number of CEA orientation sessions conducted for staff and volunteers."),
    ])
    support = indicator_for_activity("Recruitment of technical staff for the coordination of CVA.", indicators)
    assert delivery.id == 1
    assert meetings.id == 4
    assert support is None


def test_a_missing_emergency_page_does_not_stop_the_others():
    from plugins.dref_monitoring.services.go_application import attach_applications

    rows = [
        {"link_to_emergency_page": "https://go.ifrc.org/emergencies/6560/details", "stage": "Application"},
        {"link_to_emergency_page": "https://go.ifrc.org/emergencies/6736/details", "stage": "Application"},
        {"link_to_emergency_page": "https://go.ifrc.org/emergencies/6736/details", "stage": "Operational update"},
    ]

    def http_get(url, params):
        del params
        if url.endswith("/6560/"):
            raise RuntimeError("404 Client Error: Not Found for url: https://goadmin.ifrc.org/api/v2/emergency/6560/")
        return {
            "dref": {
                "planned_interventions": [
                    {
                        "title": "health",
                        "budget": 10,
                        "person_targeted": 2,
                        "description": "Open the clinic",
                        "indicators": [{"title": "People reached", "target": 2}],
                    }
                ]
            }
        }

    stats = attach_applications(rows, http_get)
    assert rows[0].get("application") is None
    assert rows[1]["application"]["interventions"][0]["key"] == "health"
    assert rows[2]["application"]["interventions"][0]["key"] == "health"
    assert stats == {"emergencies": 2, "with_plan": 1, "missing": 1, "errors": 0, "cancelled": False}


def test_emergency_payload_becomes_sectors_indicators_and_activities():
    payload = {
        "dref": {
            "planned_interventions": [
                {
                    "title": "health",
                    "title_display": "Health",
                    "budget": 8000,
                    "person_targeted": 80,
                    "description": "1. Establish two service points\n2. Train volunteers",
                    "indicators": [{"title": "People reached with health services", "target": 80}],
                }
            ],
            "operational_update_details": {
                "planned_interventions": [
                    {
                        "title": "health",
                        "budget": 9000,
                        "person_targeted": 90,
                        "description": "Keep the clinics open",
                        "indicators": [{"title": "People reached with health services", "target": 90}],
                    }
                ]
            },
            "proposed_action": [
                {
                    "proposed_type": 1,
                    "activities": [{"sector": 4, "activity": "Preposition the kits"}],
                }
            ],
        }
    }
    application = application_from_emergency(payload, "Application")
    health = application["interventions"][0]
    assert health["key"] == "health"
    assert health["activities"] == ["Establish two service points", "Train volunteers", "Early actions: Preposition the kits"]
    assert health["indicators"][0]["target"] == 80

    updated = application_from_emergency(payload, "Operational update")
    assert updated["source"] == "operational_update"
    assert updated["interventions"][0]["budget"] == 9000


@pytest.fixture
def seeded(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")


def test_plan_uses_the_application_and_flags_unmatched_bank_rows(seeded):
    health = Sector(name="Health", display_order=1, is_active=True)
    db.session.add(health)
    db.session.flush()
    matched = IndicatorBank(
        name="People reached with health services",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": health.id},
    )
    wash = Sector(name="Water, Sanitation, and Hygiene", display_order=2, is_active=True)
    db.session.add(wash)
    db.session.flush()
    hygiene = IndicatorBank(
        name="Number of people covered with hygiene promotion activities",
        type="number",
        unit="People",
        emergency=False,
        archived=False,
        sector={"primary": wash.id},
    )
    db.session.add_all([matched, hygiene])
    db.session.commit()
    apply_rows(
        [
            _row(
                application={
                    "source": "application",
                    "interventions": [
                        {
                            "key": "health",
                            "label": "Health",
                            "budget": 8000,
                            "people_targeted": 80,
                            "indicators": [
                                {"title": "People reached with health services", "target": 80},
                                {"title": "Clinics opened this week", "target": 3},
                            ],
                            "activities": ["Establish two service points", "Train volunteers"],
                        },
                        {
                            "key": "water_sanitation_and_hygiene",
                            "label": "Water, Sanitation, and Hygiene",
                            "budget": 100,
                            "people_targeted": 10,
                            "indicators": [
                                {"title": "# of people covered with hygiene promotion activities", "target": 10},
                            ],
                            "activities": ["Promote handwashing"],
                        },
                        {
                            "key": "",
                            "label": "Custom sector",
                            "budget": 10,
                            "people_targeted": None,
                            "indicators": [{"title": "Something else", "target": 1}],
                            "activities": ["Do the thing"],
                        },
                    ],
                }
            )
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRAPP01").one()
    groups = {group.key: group for group in groups_for(latest_plan(operation.id).id)}
    health_group = groups["health"]
    assert health_group.unmatched is False
    assert health_group.bank_sector_id == health.id
    indicators = {row.title: row for row in indicators_for_group(health_group.id)}
    assert indicators["People reached with health services"].indicator_bank_id == matched.id
    assert indicators["People reached with health services"].unmatched is False
    assert indicators["People reached with health services"].bank_adapted is False
    assert indicators["Clinics opened this week"].unmatched is True
    assert indicators["Clinics opened this week"].bank_adapted is False
    assert indicators["Clinics opened this week"].indicator_bank_id is None
    wash_group = groups["water_sanitation_and_hygiene"]
    hygiene_row = indicators_for_group(wash_group.id)[0]
    assert hygiene_row.indicator_bank_id == hygiene.id
    assert hygiene_row.unmatched is False
    assert hygiene_row.bank_adapted is True
    titles = [row.title for row in activities_for(health_group.id)]
    assert titles == ["Establish two service points", "Train volunteers"]
    assert all(row.indicator_id is None for row in activities_for(health_group.id))
    health_rows = activities_for(health_group.id)
    health_rows[0].indicator_id = indicators["Clinics opened this week"].id
    health_rows[1].indicator_id = indicators["People reached with health services"].id
    db.session.flush()
    placed = {row["title"]: row for row in activities_by_section(operation)["health"]}
    assert placed[health_rows[0].title]["indicator_id"] == indicators["Clinics opened this week"].id
    assert placed[health_rows[0].title]["indicator_bank_id"] is None
    assert placed[health_rows[1].title]["indicator_id"] == indicators["People reached with health services"].id
    assert placed[health_rows[1].title]["indicator_bank_id"] == matched.id
    custom = next(group for key, group in groups.items() if key.startswith("other:"))
    assert custom.unmatched is True
    assert custom.label == "Custom sector"

    shown = plan_indicator_filter(operation)
    assert shown["filter_indicators"] is True
    assert shown["indicator_bank_ids"] == [matched.id, hygiene.id]
    assert "health" in shown["sector_keys"]

    missing = {row["title"]: row for row in indicators_missing_from_template(operation)}
    assert missing["Clinics opened this week"]["flag"] == "No match in the indicator bank"
    assert missing["Clinics opened this week"]["section_key"] == "health"
    assert missing["Clinics opened this week"]["target"] == "3"
    assert missing["Clinics opened this week"]["bank_id"] is None
    assert "Something else" in missing
    assert missing["Something else"]["section_key"].startswith("other:")
    assert "People reached with health services" not in missing
    assert "# of people covered with hygiene promotion activities" not in missing

    forced = {
        row["title"]: row
        for row in indicators_missing_from_template(operation, template_bank_ids={matched.id})
    }
    assert "People reached with health services" not in forced
    hygiene_title = "# of people covered with hygiene promotion activities"
    assert forced[hygiene_title]["flag"] == "Temporarily matched to the indicator bank"
    assert forced[hygiene_title]["bank_id"] == hygiene.id
    assert forced[hygiene_title]["bank_name"] == hygiene.name
    assert forced[hygiene_title]["target"] == "10"

    hygiene_row.unmatched = True
    hygiene_row.bank_adapted = False
    hygiene_row.indicator_bank_id = None
    db.session.commit()
    assert refresh_indicator_matches(latest_plan(operation.id).id) is True
    assert hygiene_row.bank_adapted is True
    assert hygiene_row.indicator_bank_id == hygiene.id
    assert refresh_indicator_matches(latest_plan(operation.id).id) is False
