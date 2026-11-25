"""Apply the Sectoral Interventions workbook: sectors and contacts on each country project, and users."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app import db
from app.models import Project

from plugins.global_award.constants import PORTFOLIO
from plugins.global_award.importer.apply import _country_index, _project_reference
from plugins.global_award.importer.contacts import (
    SOURCE_COUNTRY,
    SOURCE_NONE,
    SOURCE_REGIONAL,
    CountryContacts,
    resolve_contacts,
)
from plugins.global_award.importer.sectoral import ParsedSectoral, Person, load_sectoral
from plugins.global_award.importer.users import sync_users

log = logging.getLogger(__name__)

_SOURCE_LABEL = {
    SOURCE_COUNTRY: "",
    SOURCE_REGIONAL: " (regional)",
    SOURCE_NONE: "",
}


class _Log:
    """Rows for the change log."""

    def __init__(self) -> None:
        self.rows: List[dict] = []
        self.tally: Dict[str, Dict[str, int]] = {
            entity: {"new": 0, "changed": 0, "unchanged": 0} for entity in ("projects", "users")
        }

    def add(self, op: str, label: str, *, old: Any = None, new: Any = None, iso3: Optional[str] = None) -> None:
        self.rows.append({
            "op": op,
            "kpi": None,
            "iso3": iso3 or None,
            "label": (label or "")[:200],
            "old_value": old,
            "new_value": new,
        })

    def diff(
        self,
        entity: str,
        before: Optional[Dict[str, str]],
        after: Dict[str, str],
        *,
        label: str,
        iso3: Optional[str],
    ) -> None:
        if before is None:
            self.tally[entity]["new"] += 1
            self.add("insert", label, iso3=iso3, new=after.get("Sectors") or None)
            return
        changed = [key for key in after if (before.get(key) or "") != (after.get(key) or "")]
        if not changed:
            self.tally[entity]["unchanged"] += 1
            return
        self.tally[entity]["changed"] += 1
        for key in changed:
            self.add(
                "update",
                f"{label} · {key}",
                iso3=iso3,
                old=(before.get(key) or None),
                new=(after.get(key) or None),
            )


def _people(people: List[Person]) -> List[Dict[str, str]]:
    return [{"name": person.name, "email": person.email} for person in people]


def _people_text(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    names = "; ".join(
        f"{row.get('name')} <{row.get('email')}>" for row in block.get("people") or [] if isinstance(row, dict)
    )
    if not names:
        return ""
    return names + _SOURCE_LABEL.get(block.get("source"), "")


def _state(sectoral: Any, contacts: Any) -> Dict[str, str]:
    sectoral = sectoral if isinstance(sectoral, dict) else {}
    contacts = contacts if isinstance(contacts, dict) else {}
    return {
        "Sectors": ", ".join(sectoral.get("sectors") or []) or ("missing data" if sectoral.get("missing_data") else ""),
        "Pillar": str(sectoral.get("pillar") or ""),
        "Sector source": str(sectoral.get("source") or ""),
        "PMER focal points": _people_text(contacts.get("pmer")),
        "Project managers": _people_text(contacts.get("project_managers")),
        "Data updated on": str(sectoral.get("updated_on") or ""),
    }


def _sectoral_block(parsed: ParsedSectoral, row: CountryContacts) -> Dict[str, Any]:
    country = row.country
    return {
        "region": country.region,
        "group": country.group or None,
        "pillar": country.pillar,
        "sectors": list(country.sectors),
        "source": country.source,
        "missing_data": country.missing,
        "updated_on": parsed.updated_on or None,
    }


def _contacts_block(row: CountryContacts) -> Dict[str, Any]:
    return {
        "pmer": {"source": row.pmer_source, "people": _people(row.pmer)},
        "project_managers": {"source": row.managers_source, "people": _people(row.managers)},
    }


def import_sectoral(source, *, dry_run: bool = False) -> Dict[str, Any]:
    """Parse ``source`` (path or xlsx bytes), update the projects and create the users.

    A dry run rolls the session back after building the same rows.
    """
    parsed = load_sectoral(source)
    try:
        report = _apply(parsed)
        report["dry_run"] = dry_run
        if dry_run:
            db.session.rollback()
            return report
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return report


def _apply(parsed: ParsedSectoral) -> Dict[str, Any]:
    resolved = resolve_contacts(parsed, _country_index())
    changes = _Log()
    warnings: List[str] = []

    projects_by_country: Dict[int, Project] = {}
    missing_projects: List[str] = []
    for row in resolved.countries:
        project = Project.query.filter_by(reference=_project_reference(row.ref)).first()
        if project is None or (project.portfolio or "") != PORTFOLIO:
            missing_projects.append(row.country.name)
            changes.add("skip", row.country.name, iso3=row.ref.iso3, new="No Global Award project yet")
            continue
        projects_by_country[row.ref.id] = project
        _update_project(parsed, row, project, changes)

    users = sync_users(resolved.people, grant_country_ids=set(projects_by_country))
    _log_users(users, changes)

    def named(source: str, field: str) -> List[str]:
        return [row.country.name for row in resolved.countries if getattr(row, field) == source]

    if resolved.unmatched_countries:
        warnings.append("No country row for: " + ", ".join(resolved.unmatched_countries))
    if resolved.unmatched_contacts:
        warnings.append("Contact rows with no matching country: " + ", ".join(resolved.unmatched_contacts))
    if missing_projects:
        warnings.append(
            "No Global Award project yet for: " + ", ".join(missing_projects)
            + ". Import the logframe first, then import this file again."
        )
    no_pmer = named(SOURCE_NONE, "pmer_source")
    if no_pmer:
        warnings.append("No PMER focal point, not even a regional one, for: " + ", ".join(no_pmer))
    no_manager = named(SOURCE_NONE, "managers_source")
    if no_manager:
        warnings.append("No project manager, not even a regional one, for: " + ", ".join(no_manager))
    warnings.extend(users["warnings"])
    for line in users["skipped"]:
        warnings.append(f"User not created: {line}")

    return {
        "countries": len(resolved.countries),
        "sectors": len(parsed.sectors),
        "projects_updated": len(projects_by_country),
        "missing_projects": missing_projects,
        "unmatched_countries": resolved.unmatched_countries,
        "unmatched_contacts": resolved.unmatched_contacts,
        "pmer_regional": named(SOURCE_REGIONAL, "pmer_source"),
        "pmer_none": no_pmer,
        "managers_regional": named(SOURCE_REGIONAL, "managers_source"),
        "managers_none": no_manager,
        "users": users,
        "users_created": users["created"],
        "users_existing": users["existing"],
        "group_name": users["group_name"],
        "warnings": warnings,
        "changes": changes.rows,
        "change_tally": changes.tally,
    }


def _update_project(parsed: ParsedSectoral, row: CountryContacts, project: Project, changes: _Log) -> None:
    old_plan = project.plan_data if isinstance(project.plan_data, dict) else {}
    sectoral = _sectoral_block(parsed, row)
    contacts = _contacts_block(row)
    before = _state(old_plan["sectoral"], old_plan.get("contacts")) if "sectoral" in old_plan else None
    after = _state(sectoral, contacts)
    if old_plan.get("sectoral") != sectoral or old_plan.get("contacts") != contacts:
        project.plan_data = {**old_plan, "sectoral": sectoral, "contacts": contacts}
    if row.managers:
        lead = row.managers[0]
        if project.manager_email != lead.email:
            project.manager_email = lead.email
        if project.manager_name != lead.name:
            project.manager_name = lead.name
    if row.pmer:
        lead = row.pmer[0]
        if project.focal_email != lead.email:
            project.focal_email = lead.email
        if project.focal_name != lead.name:
            project.focal_name = lead.name
    changes.diff("projects", before, after, label=project.title or project.reference, iso3=row.ref.iso3)


def _log_users(users: Dict[str, Any], changes: _Log) -> None:
    for row in users["created"]:
        changes.tally["users"]["new"] += 1
        changes.add(
            "insert",
            row["email"],
            new=f"{row['name']} · {', '.join(row['roles'])} · new user in {users['group_name']}",
        )
    for row in users["existing"]:
        if row["joined_group"] or row["countries_added"]:
            changes.tally["users"]["changed"] += 1
        else:
            changes.tally["users"]["unchanged"] += 1
        added = []
        if row["joined_group"]:
            added.append(f"added to {users['group_name']}")
        if row["countries_added"]:
            added.append(f"{row['countries_added']} countries added")
        changes.add(
            "exists",
            row["email"],
            old="user already existed",
            new=", ".join(added) or f"already in {users['group_name']}",
        )
