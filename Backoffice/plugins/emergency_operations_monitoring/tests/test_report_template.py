"""The cycle template is the master form: every sector, and every emergency indicator."""

from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.assignments import AssignedForm
from app.models.form_items import FormItem
from app.models.forms import FormSection, FormTemplateVersion
from app.models.indicator_bank import IndicatorBank, Sector
from plugins.emergency_operations_monitoring.access import Actor
from plugins.emergency_operations_monitoring.models import DrefOperation
from plugins.emergency_operations_monitoring.scripts import report_questions
from plugins.emergency_operations_monitoring.services.go_sync import apply_rows
from plugins.emergency_operations_monitoring.services.plans import validate_plan
from plugins.emergency_operations_monitoring.services.report_template import ensure_operation_template
from tests.factories import create_test_country, create_test_user

pytestmark = pytest.mark.db


def _row(**overrides):
    base = {
        "id": "Dref-tpl",
        "appeal_code": "MDRTPL01",
        "appeal_type": "DREF",
        "pillar": "Response",
        "country": "Zedland",
        "country_iso3": "ZZZ",
        "disaster_definition": "Flood",
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


def _manager(user_id):
    return Actor(user_id, True, frozenset(), frozenset(), {})


@pytest.fixture
def seeded(db_session):
    import plugins.emergency_operations_monitoring.models  # noqa: F401

    country = create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    user = create_test_user(db_session, email="dref-template@example.com")
    return country, user


def _items(section_id: int) -> list[FormItem]:
    return (
        FormItem.query.filter_by(section_id=section_id, archived=False)
        .order_by(FormItem.order.asc())
        .all()
    )


def test_selected_sectors_use_emergency_indicators_and_scripted_questions(seeded, monkeypatch):
    _country, user = seeded
    health = Sector(name="Health", display_order=1, is_active=True)
    wash = Sector(name="WASH", display_order=2, is_active=True)
    db.session.add_all([health, wash])
    db.session.flush()
    reached = IndicatorBank(
        name="DREF template people reached with health services",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": health.id},
        monitoring_questions=["Were the kits used?"],
    )
    ordinary = IndicatorBank(
        name="DREF template health volunteers trained",
        type="number",
        unit="People",
        emergency=False,
        archived=False,
        sector={"primary": health.id},
    )
    archived = IndicatorBank(
        name="DREF template archived health indicator",
        type="number",
        unit="People",
        emergency=True,
        archived=True,
        sector={"primary": health.id},
    )
    wash_indicator = IndicatorBank(
        name="DREF template people reached with wash",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": wash.id},
    )
    db.session.add_all([reached, ordinary, archived, wash_indicator])
    db.session.commit()

    def customize(questions, *, sector_key=None, indicator=None):
        kept = []
        for question in questions:
            if question.get("key") == "disaggregation_na":
                continue
            kept.append(question)
        return kept

    monkeypatch.setattr(report_questions, "customize_questions", customize)
    apply_rows([_row()])
    operation = DrefOperation.query.filter_by(appeal_code="MDRTPL01").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None

    cycle = AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle").first()
    version = FormTemplateVersion.query.filter_by(template_id=cycle.template_id).one()
    assert version.name == "Emergency Operations"
    assert FormTemplateVersion.query.filter(FormTemplateVersion.name.like("Emergency Operations · %")).count() == 0
    sections = (
        FormSection.query.filter_by(version_id=version.id, archived=False, parent_section_id=None)
        .order_by(FormSection.order.asc())
        .all()
    )
    from plugins.emergency_operations_monitoring.constants import SECTORS

    assert [section.name for section in sections] == [label for _key, label in SECTORS] + ["Notes"]
    health_section = next(section for section in sections if section.config["dref_sector_key"] == "health")
    assert health_section.config["entry_render"] == "dref-sector"
    assert health_section.config["entry_key"] == "health"
    assert health_section.config["indicator_entry"] == "target"

    health_items = _items(health_section.id)
    labels = [item.label for item in health_items]
    assert labels[:2] == ["Budget (CHF)", "People targeted"]
    indicator_item = next(item for item in health_items if item.indicator_bank_id == reached.id)
    assert indicator_item.item_type == "indicator"
    assert indicator_item.config["indicator_entry"] == "target"
    assert indicator_item.config["allowed_disaggregation_options"] == ["total"]
    assert labels.index("Budget (CHF)") < labels.index(reached.name)
    assert indicator_item.order == int(indicator_item.order)
    assert all(item.order == int(item.order) for item in health_items)
    assert "Were the kits used?" not in labels
    assert "Status" not in labels
    assert "Percent complete" not in labels
    assert ordinary.name not in labels
    assert archived.name not in labels
    assert wash_indicator.name not in labels
    assert all(not item.item_type.startswith("plugin_") for item in health_items)
    assert FormSection.query.filter_by(version_id=version.id, parent_section_id=health_section.id, archived=False).count() == 0

    from plugins.emergency_operations_monitoring.services.entry_activities import activities_by_section

    cards = activities_by_section(operation)["health"]
    assert cards[0]["title"].startswith("Deliver")

    report = next(section for section in sections if section.config["dref_sector_key"] == "__report__")
    report_labels = [item.label for item in _items(report.id)]
    assert report.name == "Notes"
    assert report_labels == ["Notes"]
    assert report.config["entry_render"] == "dref-report"
    assert report.config["hide_section_header"] is True
    assert report.hide_section_header is True

    from plugins.emergency_operations_monitoring.plugin import EmergencyOperationsMonitoringPlugin

    assets = EmergencyOperationsMonitoringPlugin().get_entry_form_assets(cycle.template_id)
    assert [asset["kind"] for asset in assets] == ["stylesheet", "script", "script"]
    import re

    assert re.search(r"css/sector_section\.css\?v=\d+$", assets[0]["url"])
    assert re.search(r"js/sector_section\.js\?v=\d+$", assets[1]["url"])
    assert re.search(r"js/report_actions\.js\?v=\d+$", assets[2]["url"])

    before = FormItem.query.filter_by(version_id=version.id).count()
    ensure_operation_template(operation)
    db.session.flush()
    assert FormItem.query.filter_by(version_id=version.id).count() == before
    names = [
        section.name
        for section in FormSection.query.filter_by(version_id=version.id, archived=False)
        .order_by(FormSection.order)
        .all()
    ]
    assert names == [label for _key, label in SECTORS] + ["Notes"]


def test_a_script_alias_places_indicators_when_the_sector_name_differs(seeded, monkeypatch):
    _country, user = seeded
    wash = Sector(name="WASH", display_order=1, is_active=True)
    db.session.add(wash)
    db.session.flush()
    indicator = IndicatorBank(
        name="DREF template households receiving wash support",
        type="number",
        unit="Households",
        emergency=True,
        archived=False,
        sector={"primary": str(wash.id)},
    )
    db.session.add(indicator)
    db.session.commit()
    monkeypatch.setitem(report_questions.SECTOR_NAME_TO_KEY, "WASH", "water_sanitation_and_hygiene")
    apply_rows(
        [
            _row(
                id="Dref-wash",
                appeal_code="MDRTPL02",
                sector_health=False,
                sector_health_budget=None,
                sector_health_people_targeted=None,
                sector_water_sanitation_and_hygiene=True,
                sector_water_sanitation_and_hygiene_budget=500,
            )
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRTPL02").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    cycle = AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle").first()
    version = FormTemplateVersion.query.filter_by(template_id=cycle.template_id).one()
    section = FormSection.query.filter_by(version_id=version.id, name="Water, sanitation and hygiene", archived=False).one()
    labels = [item.label for item in _items(section.id)]
    assert indicator.name in labels
    wash_item = next(item for item in _items(section.id) if item.indicator_bank_id == indicator.id)
    assert wash_item.config["indicator_entry"] == "target"
    assert wash_item.config["allowed_disaggregation_options"] == ["total"]


def test_fold_strips_parentheticals_and_containment_is_unique():
    from plugins.emergency_operations_monitoring.services.report_template import _fold, _unique_contained_sector

    assert _fold("Protection, Gender and Inclusion (PGI)") == _fold("Protection, gender and inclusion")
    assert _fold("Community Engagement and Accountability (CEA)") == _fold(
        "Community engagement and accountability"
    )
    assert _fold("Shelter") != _fold("Shelter and basic household items")

    class _Sector:
        def __init__(self, id):
            self.id = id

    shelter = _Sector(1)
    household = _Sector(2)
    food = _Sector(3)
    assert _unique_contained_sector("shelterandbasichouseholditems", {"shelter": shelter}).id == 1
    assert _unique_contained_sector("livelihoods", {"foodsecurityandlivelihoods": food}).id == 3
    assert (
        _unique_contained_sector(
            "shelterandbasichouseholditems",
            {"shelter": shelter, "basichouseholditems": household},
        )
        is None
    )


def test_shelter_and_livelihoods_match_bank_names_that_differ(seeded, monkeypatch):
    _country, user = seeded
    monkeypatch.setattr(report_questions, "SECTOR_NAME_TO_KEY", {})
    shelter = Sector(name="Shelter", display_order=1, is_active=True)
    food = Sector(name="Food security and livelihoods", display_order=2, is_active=True)
    db.session.add_all([shelter, food])
    db.session.flush()
    shelter_indicator = IndicatorBank(
        name="DREF template households receiving shelter",
        type="number",
        unit="Households",
        emergency=True,
        archived=False,
        sector={"primary": shelter.id},
    )
    live_indicator = IndicatorBank(
        name="DREF template people reached with livelihoods",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": food.id},
    )
    db.session.add_all([shelter_indicator, live_indicator])
    db.session.commit()
    apply_rows(
        [
            _row(
                id="Dref-shelter-live",
                appeal_code="MDRTPL03",
                sector_health=False,
                sector_health_budget=None,
                sector_health_people_targeted=None,
                sector_shelter_and_basic_household_items=True,
                sector_shelter_and_basic_household_items_budget=400,
                sector_livelihoods=True,
                sector_livelihoods_budget=300,
            )
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRTPL03").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    cycle = AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle").first()
    version = FormTemplateVersion.query.filter_by(template_id=cycle.template_id).one()
    shelter_section = FormSection.query.filter_by(
        version_id=version.id, name="Shelter and basic household items", archived=False
    ).one()
    live_section = FormSection.query.filter_by(version_id=version.id, name="Livelihoods", archived=False).one()
    assert shelter_indicator.name in [item.label for item in _items(shelter_section.id)]
    assert live_indicator.name in [item.label for item in _items(live_section.id)]
    assert live_indicator.name not in [item.label for item in _items(shelter_section.id)]
    assert shelter_indicator.name not in [item.label for item in _items(live_section.id)]


def test_renamed_and_parenthetical_bank_sectors_place_indicators(seeded):
    _country, user = seeded
    pgi = Sector(name="Protection, Gender and Inclusion (PGI)", display_order=1, is_active=True)
    cva = Sector(name="Cash and voucher assistance (CVA)", display_order=2, is_active=True)
    db.session.add_all([pgi, cva])
    db.session.flush()
    pgi_indicator = IndicatorBank(
        name="DREF template people reached with protection services",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": pgi.id},
    )
    cva_indicator = IndicatorBank(
        name="DREF template households receiving multipurpose cash",
        type="number",
        unit="Households",
        emergency=True,
        archived=False,
        sector={"primary": cva.id},
    )
    db.session.add_all([pgi_indicator, cva_indicator])
    db.session.commit()
    apply_rows(
        [
            _row(
                id="Dref-pgi-cva",
                appeal_code="MDRTPL04",
                sector_health=False,
                sector_health_budget=None,
                sector_health_people_targeted=None,
                sector_protection_gender_and_inclusion=True,
                sector_protection_gender_and_inclusion_budget=200,
                sector_multi_purpose_cash_grants=True,
                sector_multi_purpose_cash_grants_budget=150,
            )
        ]
    )
    operation = DrefOperation.query.filter_by(appeal_code="MDRTPL04").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    cycle = AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle").first()
    version = FormTemplateVersion.query.filter_by(template_id=cycle.template_id).one()
    pgi_section = FormSection.query.filter_by(
        version_id=version.id, name="Protection, gender and inclusion", archived=False
    ).one()
    cash_section = FormSection.query.filter_by(
        version_id=version.id, name="Multi-purpose cash grants", archived=False
    ).one()
    assert pgi_indicator.name in [item.label for item in _items(pgi_section.id)]
    assert cva_indicator.name in [item.label for item in _items(cash_section.id)]


def test_a_cycle_stores_the_indicator_figure_as_a_plan_target(seeded, monkeypatch):
    from app.models.assignments import AssignmentEntityStatus
    from plugins.emergency_operations_monitoring.models import DrefIndicator
    from plugins.emergency_operations_monitoring.services.entry_activities import overlay_plan_targets, save_posted_targets
    from plugins.emergency_operations_monitoring.services.plans import groups_for, latest_plan

    _country, user = seeded
    health = Sector(name="Health", display_order=1, is_active=True)
    db.session.add(health)
    db.session.flush()
    reached = IndicatorBank(
        name="DREF target people reached with health services",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": health.id},
    )
    other = IndicatorBank(
        name="DREF target clinics opened",
        type="number",
        unit="Clinics",
        emergency=True,
        archived=False,
        sector={"primary": health.id},
    )
    db.session.add_all([reached, other])
    db.session.commit()
    apply_rows([_row(id="Dref-target", appeal_code="MDRTGT01")])
    operation = DrefOperation.query.filter_by(appeal_code="MDRTGT01").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    group = next(row for row in groups_for(latest_plan(operation.id).id) if row.key == "health")
    linked = DrefIndicator(
        group_id=group.id,
        title=reached.name,
        indicator_bank_id=reached.id,
        standard_code="PEOPLE_REACHED",
        target=5,
    )
    db.session.add(linked)
    db.session.commit()

    cycle = (
        AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle")
        .order_by(AssignedForm.id)
        .first()
    )
    aes = AssignmentEntityStatus.query.filter_by(assigned_form_id=cycle.id).one()
    item = FormItem.query.filter_by(indicator_bank_id=reached.id, archived=False).one()
    other_item = FormItem.query.filter_by(indicator_bank_id=other.id, archived=False).one()

    shown = {}
    overlay_plan_targets(aes, shown)
    assert shown[f"field_value[{item.id}]"]["values"]["total"] == "5"
    assert f"field_value[{other_item.id}]" not in shown

    from plugins.emergency_operations_monitoring import access

    nobody = Actor(user.id, False, frozenset(), frozenset(), {})
    monkeypatch.setattr(access, "current_actor", lambda: nobody)
    assert save_posted_targets(aes, {f"indicator_{item.id}_total_value": "40"})
    assert linked.target == 5
    # Posting the unchanged figure needs no access, so a plain cycle save still works.
    assert save_posted_targets(aes, {f"indicator_{item.id}_total_value": "5"}) is None

    monkeypatch.setattr(access, "current_actor", lambda: _manager(user.id))
    assert save_posted_targets(aes, {f"indicator_{item.id}_total_value": "40"}) is None
    assert linked.target == 40

    refused = save_posted_targets(aes, {f"indicator_{item.id}_total_value": "90"})
    assert refused
    assert linked.target == 40

    assert save_posted_targets(aes, {f"indicator_{item.id}_total_value": "-1"})
    assert linked.target == 40

    assert save_posted_targets(aes, {f"indicator_{item.id}_total_value": ""}) is None
    assert linked.target is None

    assert save_posted_targets(aes, {f"indicator_{other_item.id}_total_value": "3"}) is None
    assert linked.target is None


def test_the_assignment_form_omits_indicators_that_are_not_on_the_plan(seeded):
    from app.models.assignments import AssignmentEntityStatus
    from plugins.emergency_operations_monitoring.models import DrefIndicator
    from plugins.emergency_operations_monitoring.services.entry_activities import limit_entry_fields
    from plugins.emergency_operations_monitoring.services.plans import groups_for, latest_plan

    _country, user = seeded
    health = Sector(name="Health", display_order=1, is_active=True)
    db.session.add(health)
    db.session.flush()
    reached = IndicatorBank(
        name="DREF entry people reached with health services",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": health.id},
    )
    other = IndicatorBank(
        name="DREF entry people reached with restoring family links",
        type="number",
        unit="People",
        emergency=True,
        archived=False,
        sector={"primary": health.id},
    )
    db.session.add_all([reached, other])
    db.session.commit()
    apply_rows([_row(id="Dref-entry-limit", appeal_code="MDRENTRY1")])
    operation = DrefOperation.query.filter_by(appeal_code="MDRENTRY1").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None
    group = next(row for row in groups_for(latest_plan(operation.id).id) if row.key == "health")
    db.session.add(
        DrefIndicator(
            group_id=group.id,
            title=reached.name,
            indicator_bank_id=reached.id,
            unmatched=False,
            target=5,
        )
    )
    db.session.commit()

    cycle = (
        AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle")
        .order_by(AssignedForm.id)
        .first()
    )
    aes = AssignmentEntityStatus.query.filter_by(assigned_form_id=cycle.id).one()
    version = FormTemplateVersion.query.filter_by(template_id=cycle.template_id).one()
    health_section = FormSection.query.filter_by(version_id=version.id, name="Health", archived=False).one()
    shelter_section = FormSection.query.filter_by(
        version_id=version.id, name="Shelter and basic household items", archived=False
    ).one()
    health_section.fields_ordered = _items(health_section.id)
    shelter_section.fields_ordered = _items(shelter_section.id)

    limit_entry_fields(aes)

    kept = [item.indicator_bank_id for item in health_section.fields_ordered if item.item_type == "indicator"]
    assert kept == [reached.id]
    assert shelter_section.fields_ordered == []


def test_a_generated_people_reached_plan_does_not_list_the_emergency_catalog(seeded):
    from app.models.assignments import AssignmentEntityStatus
    from plugins.emergency_operations_monitoring.services.entry_activities import limit_entry_fields, plan_indicator_filter

    _country, user = seeded
    health = Sector(name="Health", display_order=1, is_active=True)
    db.session.add(health)
    db.session.flush()
    db.session.add_all(
        [
            IndicatorBank(
                name="DREF catalog people reached with health services",
                type="number",
                unit="People",
                emergency=True,
                archived=False,
                sector={"primary": health.id},
            ),
            IndicatorBank(
                name="DREF catalog households receiving hygiene kits",
                type="number",
                unit="Households",
                emergency=True,
                archived=False,
                sector={"primary": health.id},
            ),
        ]
    )
    db.session.commit()
    apply_rows([_row(id="Dref-catalog", appeal_code="MDRCAT01")])
    operation = DrefOperation.query.filter_by(appeal_code="MDRCAT01").one()
    assert validate_plan(operation, _manager(user.id), date(2026, 1, 10)) is None

    from plugins.emergency_operations_monitoring.services.plans import (
        go_source_notices,
        groups_for,
        indicators_for_group,
        latest_baseline,
        latest_plan,
    )

    people = indicators_for_group(
        next(row.id for row in groups_for(latest_plan(operation.id).id) if row.key == "health")
    )
    assert people == []
    notices = go_source_notices(latest_baseline(operation.id))
    assert len(notices) == 1
    assert "did not publish the planned indicators" in notices[0]

    shown = plan_indicator_filter(operation)
    assert shown["filter_indicators"] is True
    assert shown["indicator_bank_ids"] == []
    assert "health" in shown["sector_keys"]

    cycle = (
        AssignedForm.query.filter_by(project_id=operation.project_id, scope="project_cycle")
        .order_by(AssignedForm.id)
        .first()
    )
    aes = AssignmentEntityStatus.query.filter_by(assigned_form_id=cycle.id).one()
    version = FormTemplateVersion.query.filter_by(template_id=cycle.template_id).one()
    health_section = FormSection.query.filter_by(version_id=version.id, name="Health", archived=False).one()
    shelter_section = FormSection.query.filter_by(
        version_id=version.id, name="Shelter and basic household items", archived=False
    ).one()
    health_section.fields_ordered = _items(health_section.id)
    shelter_section.fields_ordered = _items(shelter_section.id)

    limit_entry_fields(aes)

    assert [item for item in health_section.fields_ordered if item.item_type == "indicator"] == []
    assert any(item.item_type == "question" for item in health_section.fields_ordered)
    assert shelter_section.fields_ordered == []
