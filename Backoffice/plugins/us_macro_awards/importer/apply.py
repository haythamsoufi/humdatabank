"""Create the US Macro Awards template and one project per country in the logframe."""

from __future__ import annotations

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
    Project,
)
from app.models.enums import FormTemplateVersionStatusValue
from app.services.indicators.bank_service import indicator_bank_supports_disaggregation
from app.utils.common.datetime_helpers import utcnow

from plugins.us_macro_awards.constants import (
    FUND,
    PORTFOLIO,
    PROJECT_REFERENCE_PREFIX,
    TEMPLATE_NAME,
)
from plugins.us_macro_awards.importer.countries import CountryIndex, CountryRef
from plugins.us_macro_awards.importer.match import (
    BankIndex,
    BankRow,
    IndicatorMatch,
    disaggregation_for_question,
    question_type_for,
)
from plugins.us_macro_awards.importer.workbook import LogframeIndicator, ParsedLogframe, load_logframe

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


def _apply(parsed: ParsedLogframe) -> Dict[str, Any]:
    bank = _bank_index()
    countries = _country_index()
    template, version = _ensure_template()
    sections = _upsert_sections(template, version, parsed)
    linked, questions = _upsert_items(template, version, parsed, sections, bank)
    _archive_removed(version, parsed)
    projects, unmatched = _upsert_projects(parsed, countries)
    db.session.flush()
    return {
        "template_id": template.id,
        "template_name": TEMPLATE_NAME,
        "sections": len(parsed.sections),
        "linked": len(linked),
        "questions": len(questions),
        "projects_upserted": len(projects),
        "unmatched_countries": unmatched,
        "links": linked,
        "created_questions": questions,
        "warnings": list(unmatched and [
            "No country row for: " + ", ".join(unmatched)
        ] or []),
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
                "US Macro Awards (IFRC MARC) logframe. Lines that match the indicator "
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
        log.info("US Macro Awards: created template id=%s", template.id)
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


def _upsert_sections(template, version, parsed: ParsedLogframe) -> Dict[str, FormSection]:
    existing = {
        _marc(section.config).get("key"): section
        for section in FormSection.query.filter_by(version_id=version.id).all()
        if _marc(section.config).get("key")
    }
    by_key: Dict[str, FormSection] = {}
    for section_row in parsed.sections:
        section = existing.get(section_row.key)
        config = {
            "marc": {
                "key": section_row.key,
                "statement": section_row.statement,
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
        by_key[section_row.key] = section
    db.session.flush()
    return by_key


def _item_label(indicator: LogframeIndicator) -> str:
    code = indicator.display_code
    if code and not indicator.label.casefold().startswith(code.casefold()):
        return f"{code}. {indicator.label}"
    return indicator.label


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
    if indicator.definition:
        parts.append(indicator.definition)
    if indicator.disaggregation:
        parts.append(f"Disaggregation: {indicator.disaggregation}")
    if indicator.frequency:
        parts.append(f"Frequency: {indicator.frequency}")
    if indicator.scope:
        parts.append(f"Scope: {indicator.scope}")
    return "\n\n".join(parts)


def _marc_block(indicator: LogframeIndicator, match) -> dict:
    return {
        "key": indicator.key,
        "code": indicator.display_code,
        "reference": indicator.reference,
        "source": indicator.source,
        "unit": indicator.unit,
        "section": indicator.section_key,
        "match": match.method if match.linked else "question",
        "bank_id": match.bank_id,
        "bank_name": match.bank_name,
    }


def _upsert_items(template, version, parsed, sections, bank: BankIndex):
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
        config = dict(_BASE_CONFIG)
        if item is not None and isinstance(item.config, dict):
            config = dict(item.config)
        config["allowed_disaggregation_options"] = disaggregation
        config["marc"] = _marc_block(indicator, match)
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
    return linked, questions


def _archive_removed(version, parsed: ParsedLogframe) -> None:
    item_keys = {indicator.key for indicator in parsed.indicators}
    section_keys = {section.key for section in parsed.sections}
    for item in FormItem.query.filter_by(version_id=version.id, archived=False).all():
        key = _marc(item.config).get("key")
        if key and key not in item_keys:
            item.archived = True
    for section in FormSection.query.filter_by(version_id=version.id, archived=False).all():
        key = _marc(section.config).get("key")
        if key and key not in section_keys:
            section.archived = True


def _project_reference(country: CountryRef) -> str:
    iso3 = (country.iso3 or "").upper()
    if iso3:
        return f"{PROJECT_REFERENCE_PREFIX}{iso3}"
    token = "".join(ch for ch in country.name.upper() if ch.isalnum())[:12] or "NS"
    return f"{PROJECT_REFERENCE_PREFIX}{token}"


def _upsert_projects(parsed: ParsedLogframe, countries: CountryIndex):
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

    touched = []
    unmatched = []
    for country_name, lines in by_country.items():
        country = countries.match(country_name)
        if country is None:
            unmatched.append(country_name)
            continue
        reference = _project_reference(country)
        title = f"{TEMPLATE_NAME} — {country.name}"
        plan = {
            "source": "marc_logframe",
            "portfolio": PORTFOLIO,
            "country": country.name,
            "indicators": lines,
        }
        project = Project.query.filter_by(reference=reference).first()
        if project is None:
            project = Project(
                reference=reference,
                portfolio=PORTFOLIO,
                fund=FUND,
                title=title[:500],
                country_id=country.id,
                organization_name=country.name,
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
            project.portfolio = PORTFOLIO
            project.fund = project.fund or FUND
            project.title = title[:500]
            project.country_id = country.id
            if not project.organization_name:
                project.organization_name = country.name
            project.categories = project.categories or PORTFOLIO
            project.planned_overview = parsed.goal or project.planned_overview
            project.plan_data = plan
            if not project.status:
                project.status = "Open"
        touched.append(reference)
    return touched, unmatched


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
        log.warning("US Macro Awards: project.id has no nextval default; left the sequence alone")
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
            return "Template saved. Activate the US Macro Awards plugin to open its settings page."
        if "us_macro_awards" not in getattr(manager, "plugins", {}):
            # `flask` commands in debug boot a manager but do not load plugins.
            manager.load_plugins()
        if "us_macro_awards" not in manager.plugins:
            return "Template saved. Activate the US Macro Awards plugin to open its settings page."
        if manager.is_plugin_active("us_macro_awards"):
            return ""
        if not manager.activate_plugin("us_macro_awards"):
            return "Template saved. The plugin could not be activated automatically."
    except Exception:
        log.exception("US Macro Awards: plugin activation failed")
        return "Template saved. The plugin could not be activated automatically."
    return ""
