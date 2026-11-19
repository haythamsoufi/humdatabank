"""Create the Global Awards template and one project per country in the logframe."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from app import db
from app.models import (
    Country,
    FormItem,
    FormSection,
    FormTemplate,
    FormTemplateVersion,
    IndicatorBank,
    NationalSociety,
    Project,
)
from app.models.enums import FormTemplateVersionStatusValue
from app.services.indicators.bank_service import indicator_bank_supports_disaggregation
from app.utils.common.datetime_helpers import utcnow

from plugins.global_awards.constants import (
    FUND,
    PLUGIN_ID,
    PORTFOLIO,
    PROJECT_REFERENCE_PREFIX,
    TEMPLATE_NAME,
)
from plugins.global_awards.importer.countries import CountryIndex, CountryRef
from plugins.global_awards.importer.societies import pick_national_society
from plugins.global_awards.importer.match import (
    BankIndex,
    BankRow,
    IndicatorMatch,
    disaggregation_for_question,
    question_type_for,
)
from plugins.global_awards.importer.schedule import (
    AWARD_END,
    AWARD_START,
    official_cycles,
    relevance_for_countries,
)
from plugins.global_awards.importer.workbook import LogframeIndicator, ParsedLogframe, load_logframe

log = logging.getLogger(__name__)

_PUBLISHED = FormTemplateVersionStatusValue.published.value

_BASE_CONFIG: Dict[str, Any] = {
    "is_required": False,
    "layout_column_width": 12,
    "layout_break_after": False,
    "allowed_disaggregation_options": ["total"],
    "age_groups_config": None,
    "default_value": None,
    "allow_data_not_available": False,
    "allow_not_applicable": False,
    "allow_disability_questions": False,
    "indirect_reach": False,
    "exclude_from_completion_rate": False,
    "privacy": "ifrc_network",
}


def import_logframe(source, *, dry_run: bool = False, activate: bool = True) -> Dict[str, Any]:
    """Parse ``source`` (path or xlsx bytes) and upsert the template and projects.

    A dry run rolls the session back after building the same rows, so the
    report shows what a real import would write.
    """
    parsed = load_logframe(source)
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
    if activate:
        warning = _activate_plugin()
        if warning:
            report["warnings"].append(warning)
    return report


_LONG_VALUE = 200
_EXCERPT = 120


def _shown_change(field: str, old: str, new: str) -> tuple[str, str]:
    """Before/after text for the change log that always shows what differs.

    The log keeps about 240 characters per value, so a long value that changed near
    its end would otherwise look unchanged. Country lists are summarised by what was
    added and removed; other long text is cut around the first difference.
    """
    if field == "Applies to":
        before = [code for code in old.split(", ") if code and code != "no country"]
        after = [code for code in new.split(", ") if code and code != "no country"]
        added = [code for code in after if code not in before]
        removed = [code for code in before if code not in after]
        detail = "; ".join(
            part
            for part in (
                f"added {', '.join(added)}" if added else "",
                f"removed {', '.join(removed)}" if removed else "",
            )
            if part
        )
        return f"{len(before)} countries", f"{len(after)} countries" + (f" ({detail})" if detail else "")
    if len(old) <= _LONG_VALUE and len(new) <= _LONG_VALUE:
        return old, new
    common = 0
    for left, right in zip(old, new):
        if left != right:
            break
        common += 1
    start = max(0, common - 30)
    lead = "…" if start else ""
    return (
        lead + old[start:start + _EXCERPT] + ("…" if len(old) > start + _EXCERPT else ""),
        lead + new[start:start + _EXCERPT] + ("…" if len(new) > start + _EXCERPT else ""),
    )


class _Changes:
    """What this import changed, as before/after rows for the change log.

    Rows are only recorded when the stored value differs, so importing the same
    workbook twice records nothing the second time.
    """

    def __init__(self) -> None:
        self.rows: List[dict] = []
        self.tally: Dict[str, Dict[str, int]] = {
            entity: {"new": 0, "changed": 0, "unchanged": 0}
            for entity in ("sections", "items", "projects", "targets")
        }

    def add(
        self,
        op: str,
        *,
        label: str,
        old: Any = None,
        new: Any = None,
        kpi: Optional[str] = None,
        iso3: Optional[str] = None,
    ) -> None:
        self.rows.append({
            "op": op,
            "kpi": kpi or None,
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
        kpi: Optional[str] = None,
        iso3: Optional[str] = None,
        insert_value: str = "",
    ) -> None:
        """Record a new entity, or one row per field that differs from ``before``."""
        if before is None:
            self.tally[entity]["new"] += 1
            self.add("insert", label=label, kpi=kpi, iso3=iso3, new=insert_value or None)
            return
        changed = [field for field in after if (before.get(field) or "") != (after.get(field) or "")]
        if not changed:
            self.tally[entity]["unchanged"] += 1
            return
        self.tally[entity]["changed"] += 1
        for field in changed:
            old, new = _shown_change(field, before.get(field) or "", after.get(field) or "")
            self.add(
                "update",
                label=f"{label} · {field}",
                kpi=kpi,
                iso3=iso3,
                old=old or None,
                new=new or None,
            )


def _apply(parsed: ParsedLogframe) -> Dict[str, Any]:
    bank = _bank_index()
    countries = _country_index()
    template, version = _ensure_template()
    changes = _Changes()
    section_names_before = {
        row.id: row.name for row in FormSection.query.filter_by(version_id=version.id).all()
    }
    sections = _upsert_sections(template, version, parsed, changes)
    linked, questions = _upsert_items(
        template, version, parsed, sections, bank, countries, changes, section_names_before
    )
    _archive_removed(version, parsed, changes)
    projects, unmatched = _upsert_projects(parsed, countries, changes)
    cycles = official_cycles()
    cycle_count = _ensure_cycles(projects, template, cycles)
    removed = _retire_replaced_cycles(projects, template, {cycle.slot for cycle in cycles})
    db.session.flush()
    warnings = []
    if unmatched:
        warnings.append("No country row for: " + ", ".join(unmatched))
    if removed:
        warnings.append(f"Removed {removed} reporting cycles that are not on the DHR calendar.")
    return {
        "template_id": template.id,
        "template_name": TEMPLATE_NAME,
        "sections": len(parsed.sections),
        "linked": len(linked),
        "questions": len(questions),
        "projects_upserted": len(projects),
        "cycles_per_project": len(cycles),
        "cycle_assignments": cycle_count,
        "award_start": AWARD_START.isoformat(),
        "award_end": AWARD_END.isoformat(),
        "cycles_removed": removed,
        "timeframe_note": parsed.timeframe_note,
        "unmatched_countries": unmatched,
        "links": linked,
        "created_questions": questions,
        "warnings": warnings,
        "changes": changes.rows,
        "change_tally": changes.tally,
    }


def _bank_index() -> BankIndex:
    rows = [
        BankRow(id=row.id, name=row.name or "", archived=bool(row.archived))
        for row in db.session.query(IndicatorBank.id, IndicatorBank.name, IndicatorBank.archived)
    ]
    return BankIndex(rows)


def _country_index() -> CountryIndex:
    refs = [
        CountryRef(id=row.id, name=row.name or "", iso3=(row.iso3 or "").upper())
        for row in db.session.query(Country.id, Country.name, Country.iso3)
    ]
    return CountryIndex(refs)


def _owner_id() -> Optional[int]:
    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False):
            return int(current_user.id)
    except Exception:
        return None
    return None


def _status_value(version: FormTemplateVersion) -> str:
    status = version.status
    return str(getattr(status, "value", status) or "")


def _ensure_template() -> tuple[FormTemplate, FormTemplateVersion]:
    version = (
        FormTemplateVersion.query.filter(FormTemplateVersion.name == TEMPLATE_NAME)
        .order_by(FormTemplateVersion.id.desc())
        .first()
    )
    owner_id = _owner_id()
    if version is None:
        template = FormTemplate(created_by=owner_id, owned_by=owner_id)
        db.session.add(template)
        db.session.flush()
        now = utcnow()
        version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status=FormTemplateVersionStatusValue.published,
            name=TEMPLATE_NAME,
            description=(
                "Global Awards (IFRC MARC) logframe. Lines that match the indicator "
                "bank are indicators; the other lines are questions."
            ),
            created_by=owner_id,
            updated_by=owner_id,
            created_at=now,
            updated_at=now,
            enable_export_pdf=True,
            enable_export_excel=True,
        )
        db.session.add(version)
        db.session.flush()
        template.published_version_id = version.id
        log.info("Global Awards: created template id=%s", template.id)
        return template, version

    template = version.template
    if template is None:
        raise RuntimeError(f"Form template version {version.id} has no template.")
    if _status_value(version) != _PUBLISHED:
        version.status = FormTemplateVersionStatusValue.published
    if template.published_version_id != version.id:
        template.published_version_id = version.id
    version.updated_at = utcnow()
    if owner_id is not None:
        version.updated_by = owner_id
    return template, version


def _marc(config: Optional[dict]) -> dict:
    if not isinstance(config, dict):
        return {}
    block = config.get("marc")
    return block if isinstance(block, dict) else {}


def _section_state(section: FormSection) -> Dict[str, str]:
    marc = _marc(section.config)
    return {
        "Name": section.name or "",
        "Statement": str(marc.get("statement") or ""),
        "Parent": str(marc.get("parent") or ""),
        "Status": "archived" if section.archived else "active",
    }


def _upsert_sections(template, version, parsed: ParsedLogframe, changes: _Changes) -> Dict[str, FormSection]:
    existing = {
        _marc(section.config).get("key"): section
        for section in FormSection.query.filter_by(version_id=version.id).all()
        if _marc(section.config).get("key")
    }
    by_key: Dict[str, FormSection] = {}
    for section_row in parsed.sections:
        section = existing.get(section_row.key)
        before = _section_state(section) if section is not None else None
        config = {
            "marc": {
                "key": section_row.key,
                "statement": section_row.statement,
                "parent": section_row.parent_key or None,
                "kind": section_row.kind or None,
            }
        }
        if section is None:
            section = FormSection(
                template_id=template.id,
                version_id=version.id,
                name=section_row.name[:100],
                order=float(section_row.order),
                section_type="standard",
                config=config,
            )
            db.session.add(section)
        else:
            section.name = section_row.name[:100]
            section.order = float(section_row.order)
            section.archived = False
            section.section_type = section.section_type or "standard"
            kept = dict(section.config or {})
            kept["marc"] = config["marc"]
            section.config = kept
        changes.diff(
            "sections",
            before,
            _section_state(section),
            label=section_row.name,
            insert_value="subsection" if section_row.parent_key else "section",
        )
        by_key[section_row.key] = section
    db.session.flush()
    for section_row in parsed.sections:
        section = by_key[section_row.key]
        parent = by_key.get(section_row.parent_key) if section_row.parent_key else None
        section.parent_section_id = parent.id if parent is not None else None
    return by_key


def _item_label(indicator: LogframeIndicator) -> str:
    """Question/indicator title as written, without the logframe code prefix."""
    label = indicator.label or ""
    code = (indicator.display_code or "").strip()
    if not code:
        return label
    if label.casefold().startswith(code.casefold()):
        rest = label[len(code) :].lstrip(" .:-")
        return rest or label
    return label


def _definition(indicator: LogframeIndicator) -> str:
    parts: List[str] = []
    meta = []
    if indicator.display_code:
        meta.append(f"Logframe: {indicator.display_code}")
    if indicator.source:
        meta.append(indicator.source)
    if indicator.unit:
        meta.append(f"Unit: {indicator.unit}")
    if meta:
        parts.append(" · ".join(meta))
    if indicator.topic:
        parts.append(f"Group: {indicator.topic}")
    if indicator.definition:
        parts.append(indicator.definition)
    if indicator.disaggregation:
        parts.append(f"Disaggregation: {indicator.disaggregation}")
    if indicator.frequency:
        parts.append(f"Frequency: {indicator.frequency}")
    if indicator.scope:
        parts.append(f"Scope: {indicator.scope}")
    if indicator.targets:
        parts.append("Applies to: " + ", ".join(indicator.targets))
    else:
        parts.append("Applies to: no country target in the logframe yet.")
    return "\n\n".join(parts)


def _marc_block(indicator: LogframeIndicator, match, iso3: List[str]) -> dict:
    return {
        "key": indicator.key,
        "code": indicator.display_code,
        "reference": indicator.reference,
        "source": indicator.source,
        "unit": indicator.unit,
        "section": indicator.section_key,
        "topic": indicator.topic or None,
        "match": match.method if match.linked else "question",
        "bank_id": match.bank_id,
        "bank_name": match.bank_name,
        "countries": list(indicator.targets),
        "country_iso3": iso3,
    }


def _iso3_for(indicator: LogframeIndicator, countries: CountryIndex) -> List[str]:
    codes: List[str] = []
    for name in indicator.targets:
        country = countries.match(name)
        code = (country.iso3 if country else "").upper()
        if code and code not in codes:
            codes.append(code)
    return codes


def _item_state(item: FormItem, section_names: Dict[int, str]) -> Dict[str, str]:
    marc = _marc(item.config)
    if item.item_type == "indicator" and item.indicator_bank_id:
        kind = f"indicator · bank #{item.indicator_bank_id}"
    else:
        kind = f"question · {item.type or 'text'}"
    return {
        "Wording": item.label or "",
        "Type": kind,
        "Section": section_names.get(item.section_id, ""),
        "Applies to": ", ".join(marc.get("country_iso3") or []) or "no country",
        "Definition": item.definition or "",
        "Status": "archived" if item.archived else "active",
    }


def _upsert_items(
    template,
    version,
    parsed,
    sections,
    bank: BankIndex,
    countries: CountryIndex,
    changes: _Changes,
    section_names_before: Dict[int, str],
):
    existing = {
        _marc(item.config).get("key"): item
        for item in FormItem.query.filter_by(version_id=version.id).all()
        if _marc(item.config).get("key")
    }
    matched_ids = []
    decisions = []
    for order, indicator in enumerate(parsed.indicators, start=1):
        match = bank.match(
            label=indicator.label,
            source=indicator.source,
            reference=indicator.reference,
            cited_bank_id=indicator.cited_bank_id,
        )
        decisions.append((order, indicator, match))
        if match.linked and match.bank_id is not None:
            matched_ids.append(match.bank_id)

    bank_rows = {}
    if matched_ids:
        from sqlalchemy.orm import joinedload

        bank_rows = {
            row.id: row
            for row in IndicatorBank.query.options(joinedload(IndicatorBank.measurement_unit))
            .filter(IndicatorBank.id.in_(set(matched_ids)))
            .all()
        }

    linked: List[dict] = []
    questions: List[dict] = []
    section_names_after = {section.id: section.name for section in sections.values()}
    for order, indicator, match in decisions:
        section = sections[indicator.section_key]
        bank_row = bank_rows.get(match.bank_id) if match.linked else None
        if match.linked and bank_row is None:
            match = IndicatorMatch(None, "none", "", match.note or "Indicator bank row could not be loaded.")
        question_type = question_type_for(indicator.unit, indicator.label)
        if bank_row is not None and indicator_bank_supports_disaggregation(bank_row):
            disaggregation = ["total", "sex", "age", "sex_age"]
        elif bank_row is not None:
            disaggregation = ["total"]
        else:
            disaggregation = disaggregation_for_question(question_type, indicator.unit)

        item = existing.get(indicator.key)
        before = _item_state(item, section_names_before) if item is not None else None
        config = dict(_BASE_CONFIG)
        if item is not None and isinstance(item.config, dict):
            config = dict(item.config)
        iso3 = _iso3_for(indicator, countries)
        config["allowed_disaggregation_options"] = disaggregation
        config["marc"] = _marc_block(indicator, match, iso3)
        label = _item_label(indicator)
        if item is None:
            item = FormItem(
                template_id=template.id,
                section_id=section.id,
                version_id=version.id,
                label=label,
                order=float(order),
                definition=_definition(indicator),
                config=config,
            )
            db.session.add(item)
        else:
            item.section_id = section.id
            item.label = label
            item.order = float(order)
            item.definition = _definition(indicator)
            item.archived = False
            item.config = config
        item.relevance_condition = relevance_for_countries(iso3)

        if bank_row is not None:
            item.item_type = "indicator"
            item.indicator_bank_id = bank_row.id
            item.type = bank_row.type
            item.unit = (bank_row.unit or "")[:50] or None
            item.indicator_type_id = bank_row.indicator_type_id
            item.indicator_unit_id = bank_row.indicator_unit_id
            item.options_json = None
            linked.append({
                "code": indicator.display_code,
                "label": indicator.label,
                "section": indicator.section_name,
                "bank_id": bank_row.id,
                "bank_name": bank_row.name,
                "method": match.method,
                "note": match.note,
            })
        else:
            item.item_type = "question"
            item.indicator_bank_id = None
            item.indicator_type_id = None
            item.indicator_unit_id = None
            item.type = question_type
            item.unit = (indicator.unit or "")[:50] or None
            item.options_json = None
            questions.append({
                "code": indicator.display_code,
                "label": indicator.label,
                "section": indicator.section_name,
                "question_type": question_type,
                "note": match.note,
            })
        after = _item_state(item, section_names_after)
        changes.diff(
            "items",
            before,
            after,
            label=_item_label(indicator),
            kpi=indicator.display_code,
            insert_value=f"{after['Type']} · {after['Section']}",
        )
    _apply_section_relevance(sections, parsed, countries)
    return linked, questions


def _apply_section_relevance(sections, parsed: ParsedLogframe, countries: CountryIndex) -> None:
    """Hide a section unless the country has at least one of its indicators.

    Objective sections inherit the countries of their outcome subsections so a
    parent is not hidden when only the children apply.
    """
    codes_by_section: Dict[str, List[str]] = {}
    for indicator in parsed.indicators:
        bucket = codes_by_section.setdefault(indicator.section_key, [])
        for code in _iso3_for(indicator, countries):
            if code not in bucket:
                bucket.append(code)
    for section_row in parsed.sections:
        if not section_row.parent_key:
            continue
        parent_bucket = codes_by_section.setdefault(section_row.parent_key, [])
        for code in codes_by_section.get(section_row.key, []):
            if code not in parent_bucket:
                parent_bucket.append(code)
    for key, section in sections.items():
        section.relevance_condition = relevance_for_countries(codes_by_section.get(key, []))


def _archive_removed(version, parsed: ParsedLogframe, changes: _Changes) -> None:
    item_keys = {indicator.key for indicator in parsed.indicators}
    section_keys = {section.key for section in parsed.sections}
    for item in FormItem.query.filter_by(version_id=version.id, archived=False).all():
        key = _marc(item.config).get("key")
        if key and key not in item_keys:
            item.archived = True
            changes.tally["items"]["changed"] += 1
            changes.add(
                "archive",
                label=item.label,
                kpi=str(_marc(item.config).get("code") or "") or None,
                old="active",
                new="archived (no longer in the workbook)",
            )
    for section in FormSection.query.filter_by(version_id=version.id, archived=False).all():
        key = _marc(section.config).get("key")
        if key and key not in section_keys:
            section.archived = True
            changes.tally["sections"]["changed"] += 1
            changes.add(
                "archive",
                label=section.name,
                old="active",
                new="archived (no longer in the workbook)",
            )


def _project_reference(country: CountryRef) -> str:
    iso3 = (country.iso3 or "").upper()
    if iso3:
        return f"{PROJECT_REFERENCE_PREFIX}{iso3}"
    token = "".join(ch for ch in country.name.upper() if ch.isalnum())[:12] or "NS"
    return f"{PROJECT_REFERENCE_PREFIX}{token}"


def _day(value) -> str:
    if isinstance(value, dt.datetime):
        value = value.date()
    return value.isoformat() if isinstance(value, dt.date) else ""


def _project_state(project: Project) -> Dict[str, str]:
    return {
        "Title": project.title or "",
        "National Society": project.organization_name or "",
        "Start date": _day(project.start_date),
        "End date": _day(project.end_date),
    }


def _plan_targets(plan: Any) -> Dict[str, dict]:
    """Logframe lines of a project plan by indicator key."""
    lines = plan.get("indicators") if isinstance(plan, dict) else None
    return {
        str(line["key"]): line
        for line in lines or []
        if isinstance(line, dict) and line.get("key")
    }


def _record_target_changes(
    changes: _Changes,
    country: CountryRef,
    old_plan: Any,
    new_lines: List[dict],
) -> None:
    """One row per indicator whose target for this country was added, changed or dropped."""
    old = _plan_targets(old_plan)
    new = {str(line["key"]): line for line in new_lines}
    for key in [*new, *(key for key in old if key not in new)]:
        before = old.get(key)
        after = new.get(key)
        old_target = str(before.get("target") or "") if before else ""
        new_target = str(after.get("target") or "") if after else ""
        if old_target == new_target:
            changes.tally["targets"]["unchanged"] += 1
            continue
        line = after or before or {}
        label = str(line.get("label") or key)
        if not before:
            op, bucket = "insert", "new"
        elif not after:
            op, bucket = "remove", "changed"
        else:
            op, bucket = "update", "changed"
        changes.tally["targets"][bucket] += 1
        changes.add(
            op,
            label=label,
            kpi=str(line.get("code") or "") or None,
            iso3=(country.iso3 or "").upper() or None,
            old=old_target or None,
            new=new_target or None,
        )


def _upsert_projects(parsed: ParsedLogframe, countries: CountryIndex, changes: _Changes):
    _sync_project_id_sequence()
    by_country: Dict[str, List[dict]] = {}
    for indicator in parsed.indicators:
        for country_name, target in indicator.targets.items():
            by_country.setdefault(country_name, []).append({
                "key": indicator.key,
                "code": indicator.display_code,
                "label": indicator.label,
                "unit": indicator.unit,
                "target": target,
            })

    touched: List[Project] = []
    unmatched = []
    for country_name in parsed.countries:
        lines = by_country.get(country_name, [])
        country = countries.match(country_name)
        if country is None:
            unmatched.append(country_name)
            continue
        reference = _project_reference(country)
        title = f"{TEMPLATE_NAME} — {country.name}"
        society = pick_national_society(
            NationalSociety.query.filter_by(country_id=country.id).all()
        )
        if society is None:
            unmatched.append(f"{country_name} (no single National Society)")
        plan = {
            "source": "marc_logframe",
            "portfolio": PORTFOLIO,
            "country": country.name,
            "national_society_id": society.id if society is not None else None,
            "indicators": lines,
        }
        project = Project.query.filter_by(reference=reference).first()
        before = None
        old_plan = None
        if project is None:
            project = Project(
                reference=reference,
                portfolio=PORTFOLIO,
                fund=FUND,
                title=title[:500],
                country_id=country.id,
                national_society_id=society.id if society is not None else None,
                organization_name=society.name if society is not None else None,
                status="Open",
                categories=PORTFOLIO,
                planned_overview=parsed.goal or None,
                plan_data=plan,
            )
            db.session.add(project)
        else:
            if (project.portfolio or "") not in ("", PORTFOLIO):
                unmatched.append(f"{country_name} (reference {reference} belongs to {project.portfolio})")
                continue
            before = _project_state(project)
            old_plan = project.plan_data
            project.portfolio = PORTFOLIO
            project.fund = project.fund or FUND
            project.title = title[:500]
            project.country_id = country.id
            project.national_society_id = society.id if society is not None else None
            project.organization_name = society.name if society is not None else None
            project.categories = project.categories or PORTFOLIO
            project.planned_overview = parsed.goal or project.planned_overview
            project.plan_data = plan
            if not project.status:
                project.status = "Open"
        project.start_date = AWARD_START
        project.end_date = AWARD_END
        changes.diff(
            "projects",
            before,
            _project_state(project),
            label=title,
            iso3=(country.iso3 or "").upper() or None,
            insert_value=f"project {reference} · {len(lines)} indicator targets",
        )
        if before is not None:
            _record_target_changes(changes, country, old_plan, lines)
        touched.append(project)
    db.session.flush()
    return touched, unmatched


def _ensure_cycles(projects: List[Project], template: FormTemplate, cycles) -> int:
    if not projects or not cycles:
        return 0
    from app.services.projects.service import ensure_project_cycle_assignment

    created = 0
    for project in projects:
        for cycle in cycles:
            ensure_project_cycle_assignment(
                project,
                template.id,
                cycle.slot,
                period_start=cycle.start,
                period_end=cycle.end,
                due_date=dt.datetime.combine(cycle.country_due, dt.time.min),
            )
            created += 1
    return created


def _retire_replaced_cycles(projects: List[Project], template: FormTemplate, keep_slots: set[str]) -> int:
    """Drop cycles from the earlier month-grid import when they have no answers."""
    from app.models import AssignmentEntityStatus, FormData
    from app.models.assignments import AssignedForm
    from app.models.enums import AssignmentScope
    from app.services.projects.service import parse_cycle_slot

    removed = 0
    for project in projects:
        assignments = AssignedForm.query.filter_by(
            project_id=project.id,
            template_id=template.id,
            scope=AssignmentScope.project_cycle.value,
        ).all()
        for assignment in assignments:
            slot = parse_cycle_slot(assignment.period_name)
            if slot in keep_slots:
                continue
            aes_ids = [
                row.id
                for row in AssignmentEntityStatus.query.filter_by(assigned_form_id=assignment.id).all()
            ]
            if aes_ids and FormData.query.filter(FormData.assignment_entity_status_id.in_(aes_ids)).count():
                continue
            db.session.delete(assignment)
            removed += 1
    return removed


def _sync_project_id_sequence() -> None:
    """Point the sequence that ``project.id`` actually calls at MAX(id).

    ``pg_get_serial_sequence`` still names ``nsd_project_id_seq`` after the
    table rename, while the column default is ``project_id_seq``. Inserts
    follow the default, so that is the sequence that has to move.
    """
    import re

    from sqlalchemy import text

    default = db.session.execute(
        text(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'project'
              AND column_name = 'id'
            """
        )
    ).scalar()
    match = re.search(r"nextval\('([A-Za-z_][A-Za-z0-9_]*)'", default or "")
    if not match:
        log.warning("Global Awards: project.id has no nextval default; left the sequence alone")
        return
    db.session.execute(
        text(
            "SELECT setval(to_regclass(:seq), COALESCE((SELECT MAX(id) FROM project), 1), true)"
        ),
        {"seq": match.group(1)},
    )


def _activate_plugin() -> str:
    try:
        from flask import current_app

        manager = getattr(current_app, "plugin_manager", None)
        if manager is None:
            return "Template saved. Activate the Global Awards plugin to open its settings page."
        if PLUGIN_ID not in getattr(manager, "plugins", {}):
            # `flask` commands in debug boot a manager but do not load plugins.
            manager.load_plugins()
        if PLUGIN_ID not in manager.plugins:
            return "Template saved. Activate the Global Awards plugin to open its settings page."
        if manager.is_plugin_active(PLUGIN_ID):
            return ""
        if not manager.activate_plugin(PLUGIN_ID):
            return "Template saved. The plugin could not be activated automatically."
    except Exception:
        log.exception("Global Awards: plugin activation failed")
        return "Template saved. The plugin could not be activated automatically."
    return ""
