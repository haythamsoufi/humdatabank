"""Sectoral Interventions import: users, the Global Award access group, and project contacts."""

from __future__ import annotations

import io

import openpyxl
import pytest

from app.models import Country, Project, User
from app.models.core import UserEntityPermission
from app.models.rbac import ROLE_KIND_GROUP, RbacRole, RbacUserRole
from plugins.global_award.constants import ACCESS_GROUP_CODE, DEFAULT_USER_ROLE_CODE
from plugins.global_award.importer.contacts import PersonRecord
from plugins.global_award.importer.sectoral_apply import import_sectoral
from plugins.global_award.importer.users import sync_users

pytestmark = pytest.mark.db


def _members(db_session):
    group = RbacRole.query.filter_by(code=ACCESS_GROUP_CODE).one()
    return group, {row.user_id for row in RbacUserRole.query.filter_by(role_id=group.id)}


def test_new_users_join_the_group_and_existing_ones_are_reported(db_session):
    db_session.add(RbacRole(code=DEFAULT_USER_ROLE_CODE, name="Viewer"))
    present = User(email="present@ifrc.org", name="Present Person", active=True)
    db_session.add(present)
    db_session.flush()

    people = {
        "fresh@ifrc.org": PersonRecord("fresh@ifrc.org", "Fresh Person", ["Project manager"], [7, 8]),
        "present@ifrc.org": PersonRecord("present@ifrc.org", "Different Name", ["PMER focal point"], [7]),
    }
    result = sync_users(people, grant_country_ids={7})

    assert result["group_created"] is True
    assert [row["email"] for row in result["created"]] == ["fresh@ifrc.org"]
    assert [row["email"] for row in result["existing"]] == ["present@ifrc.org"]
    group, members = _members(db_session)
    assert group.kind == ROLE_KIND_GROUP and group.name == "Global Award"
    fresh = User.query.filter_by(email="fresh@ifrc.org").one()
    assert members == {fresh.id, present.id}
    # An existing user keeps their name; a new one has no password and a default role.
    assert present.name == "Present Person"
    assert fresh.password_hash is None
    assert RbacUserRole.query.filter_by(user_id=fresh.id).count() == 2
    assert RbacUserRole.query.filter_by(user_id=present.id).count() == 1
    # Country 8 has no project, so it is not granted.
    assert {row.entity_id for row in UserEntityPermission.query.filter_by(user_id=fresh.id)} == {7}
    assert {row.entity_id for row in UserEntityPermission.query.filter_by(user_id=present.id)} == {7}

    again = sync_users(people, grant_country_ids={7})
    assert again["group_created"] is False
    assert again["created"] == []
    assert len(again["existing"]) == 2
    assert again["group_added"] == 0 and again["country_access_added"] == 0
    assert all(not row["joined_group"] for row in again["existing"])


def _workbook_bytes():
    book = openpyxl.Workbook()
    sectors = book.active
    sectors.title = "Sectoral interventions"
    sectors.append([])
    sectors.append([])
    sectors.append([None, "Region", "Country", None, "WASH", "Health", "Pillar", None, None])
    sectors.append([None, "Africa", "Testland", None, "X", None, 1, "Source:", "award narrative"])
    sectors.append([None, None, "Otherland", None, None, "X", 2, "Source:", "award narrative"])
    pmer = book.create_sheet("PMER Focal Points")
    pmer.append(["Sequence", "Region / Country", "Name", "Email", "Entity / Office", "Pillar", "Remark"])
    pmer.append([1, "Africa – Regional", "Reg Pmer", "reg.pmer@ifrc.org", "Office", None, None])
    pmer.append([2, "Testland", None, None, None, "Pillar 1", None])
    pmer.append([3, "Otherland", "Own Pmer", "own.pmer@ifrc.org", None, "Pillar 2", None])
    managers = book.create_sheet("Project Managers")
    managers.append(["Pillar", "Region", "SubRegion", "Country", "project manager", "email"])
    managers.append(["Pillar 1", "Africa", "Africa", "Testland", "Test Pm", "test.pm@ifrc.org"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_import_updates_projects_with_the_regional_fallback_and_survives_a_logframe_reimport(db_session):
    db_session.add(RbacRole(code=DEFAULT_USER_ROLE_CODE, name="Viewer"))
    testland = Country(name="Testland", iso3="TLD", region="Africa")
    otherland = Country(name="Otherland", iso3="OTH", region="Africa")
    db_session.add_all([testland, otherland])
    db_session.flush()
    for country in (testland, otherland):
        db_session.add(
            Project(
                reference=f"GA-{country.iso3}",
                portfolio="Global Award",
                title=f"Global Award — {country.name}",
                country_id=country.id,
                plan_data={"source": "marc_logframe", "indicators": []},
            )
        )
    db_session.add(User(email="own.pmer@ifrc.org", name="Own Pmer", active=True))
    db_session.commit()

    data = _workbook_bytes()
    preview = import_sectoral(data, dry_run=True)
    assert preview["dry_run"] is True
    assert User.query.filter_by(email="reg.pmer@ifrc.org").count() == 0
    assert RbacRole.query.filter_by(code=ACCESS_GROUP_CODE).count() == 0

    report = import_sectoral(data)

    assert report["pmer_regional"] == ["Testland"]
    assert report["projects_updated"] == 2
    assert [row["email"] for row in report["users_existing"]] == ["own.pmer@ifrc.org"]
    assert {row["email"] for row in report["users_created"]} == {"reg.pmer@ifrc.org", "test.pm@ifrc.org"}
    # Otherland has no project manager and its region office lists none either.
    assert report["warnings"] == ["No project manager, not even a regional one, for: Otherland"]

    project = Project.query.filter_by(reference="GA-TLD").one()
    assert project.plan_data["sectoral"]["sectors"] == ["WASH"]
    assert project.plan_data["sectoral"]["pillar"] == "1"
    assert project.plan_data["contacts"]["pmer"]["source"] == "regional"
    assert project.focal_email == "reg.pmer@ifrc.org"
    assert project.manager_email == "test.pm@ifrc.org"
    # The logframe's own part of the plan is still there.
    assert project.plan_data["indicators"] == []
    other = Project.query.filter_by(reference="GA-OTH").one()
    assert other.focal_email == "own.pmer@ifrc.org"
    assert other.manager_email is None

    reg = User.query.filter_by(email="reg.pmer@ifrc.org").one()
    assert {row.entity_id for row in UserEntityPermission.query.filter_by(user_id=reg.id)} == {testland.id}

    # Importing the same file again changes nothing and still lists the existing users.
    second = import_sectoral(data)
    assert second["users_created"] == []
    assert len(second["users_existing"]) == 3
    assert [row for row in second["changes"] if row["op"] in ("insert", "update")] == []
