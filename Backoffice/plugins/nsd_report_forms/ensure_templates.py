"""Create and publish the NSD CBF report templates when missing.

The master import and shared-slot schedule require published templates named in
``layout.TEMPLATE_NAMES``. Admins no longer need to build them by hand first —
this module creates a usable published structure (sections + items the importer
writes to) and fills any missing labels on an already-published version.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app import db
from app.models import FormItem, FormSection, FormTemplate, FormTemplateVersion
from app.models.enums import FormTemplateVersionStatusValue
from app.utils.datetime_helpers import utcnow

from plugins.nsd_report_forms.importer import layout

log = logging.getLogger(__name__)

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

_SPENDING_MATRIX = {
    "type": "matrix",
    "row_mode": "manual",
    "rows": [{"text": "Amount (CHF)"}],
    "columns": [
        {"name": "Expected spending (CHF)", "type": "number_decimal", "decimals": 2},
        {"name": "Actual amount spent to date (CHF)", "type": "number_decimal", "decimals": 2},
    ],
    "show_row_totals": False,
    "show_column_totals": False,
    "include_calculated_totals_in_api": True,
}

_PROJECT_INFO_FIELDS: Sequence[Tuple[str, str]] = (
    ("National Society", "text"),
    ("Title", "text"),
    ("Reference", "text"),
    ("Funding Modality", "text"),
    ("Categories/Thematics", "text"),
    ("Start Date", "text"),
    ("End Date", "text"),
    ("Amount Granted (in CHF)", "text"),
    ("NS Focal Person", "text"),
    ("IFRC Project Manager", "text"),
)


def _owner_id() -> Optional[int]:
    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False):
            return int(current_user.id)
    except Exception:
        pass
    return None


def _norm(s: str) -> str:
    return " ".join(str(s or "").casefold().split())


def _question(
    *,
    template: FormTemplate,
    section: FormSection,
    version: FormTemplateVersion,
    label: str,
    order: float,
    qtype: str = "text",
    options: Optional[Sequence[str]] = None,
) -> FormItem:
    item = FormItem(
        template_id=template.id,
        section_id=section.id,
        version_id=version.id,
        item_type="question",
        label=label,
        order=order,
        type=qtype,
        options_json=list(options) if options else None,
        config=dict(_BASE_CONFIG),
    )
    db.session.add(item)
    return item


def _matrix(
    *,
    template: FormTemplate,
    section: FormSection,
    version: FormTemplateVersion,
    label: str,
    order: float,
    matrix_config: Dict[str, Any],
) -> FormItem:
    cfg = dict(_BASE_CONFIG)
    cfg["matrix_config"] = matrix_config
    item = FormItem(
        template_id=template.id,
        section_id=section.id,
        version_id=version.id,
        item_type="matrix",
        label=label,
        order=order,
        type="matrix",
        config=cfg,
    )
    db.session.add(item)
    return item


def _plugin(
    *,
    template: FormTemplate,
    section: FormSection,
    version: FormTemplateVersion,
    label: str,
    order: float,
    plugin_type: str,
    plugin_config: Optional[Dict[str, Any]] = None,
) -> FormItem:
    cfg = dict(_BASE_CONFIG)
    cfg["plugin_type"] = plugin_type
    cfg["plugin_config"] = plugin_config or {}
    item = FormItem(
        template_id=template.id,
        section_id=section.id,
        version_id=version.id,
        item_type=f"plugin_{plugin_type}",
        label=label,
        order=order,
        config=cfg,
    )
    db.session.add(item)
    return item


def _section(
    *,
    template: FormTemplate,
    version: FormTemplateVersion,
    name: str,
    order: float,
    section_type: str = "standard",
) -> FormSection:
    existing = (
        FormSection.query.filter_by(version_id=version.id, archived=False)
        .filter(FormSection.name == name)
        .first()
    )
    if existing:
        return existing
    sec = FormSection(
        template_id=template.id,
        version_id=version.id,
        name=name,
        order=order,
        section_type=section_type,
    )
    db.session.add(sec)
    db.session.flush()
    return sec


def _existing_labels(version_id: int) -> set:
    return {
        _norm(label)
        for (label,) in db.session.query(FormItem.label).filter_by(
            version_id=version_id, archived=False
        )
    }


def _add_if_missing(
    labels: set,
    *,
    create_fn,
    label: str,
) -> None:
    if _norm(label) in labels:
        return
    create_fn()
    labels.add(_norm(label))


def _fill_project_info(
    labels: set,
    template: FormTemplate,
    version: FormTemplateVersion,
    section: FormSection,
    start_order: float = 1.0,
    extra: Sequence[Tuple[str, str]] = (),
) -> None:
    order = start_order
    for label, qtype in list(_PROJECT_INFO_FIELDS) + list(extra):
        _add_if_missing(
            labels,
            label=label,
            create_fn=lambda label=label, qtype=qtype, order=order: _question(
                template=template,
                section=section,
                version=version,
                label=label,
                order=order,
                qtype=qtype,
            ),
        )
        order += 1


def _build_quarter_structure(template: FormTemplate, version: FormTemplateVersion) -> None:
    labels = _existing_labels(version.id)
    info = _section(template=template, version=version, name="Project information", order=1)
    impl = _section(template=template, version=version, name="Implementation review", order=2)
    last_ap = _section(
        template=template,
        version=version,
        name="Last quarter action points (optional)",
        order=3,
        section_type="repeat",
    )
    next_ap = _section(
        template=template,
        version=version,
        name="Next quarter action points (optional)",
        order=4,
        section_type="repeat",
    )
    db.session.flush()

    _fill_project_info(labels, template, version, info)

    for label, qtype, options in (
        ("Review author(s)", "text", None),
        ("Review date", "date", None),
        ("Overall implementation assessment", "single_choice", layout.OVERALL_ASSESSMENT),
        ("Activities' implementation according to the plan", "single_choice", layout.ACTIVITIES_STATUS),
        ("OPTIONAL extra KPI (if helpful)", "textarea", None),
        ("OPTIONAL Comments", "textarea", None),
    ):
        _add_if_missing(
            labels,
            label=label,
            create_fn=lambda label=label, qtype=qtype, options=options, order=len(labels) + 1: _question(
                template=template,
                section=impl,
                version=version,
                label=label,
                order=float(order),
                qtype=qtype,
                options=options,
            ),
        )

    _add_if_missing(
        labels,
        label="Spending",
        create_fn=lambda: _matrix(
            template=template,
            section=impl,
            version=version,
            label="Spending",
            order=float(len(labels) + 1),
            matrix_config=dict(_SPENDING_MATRIX),
        ),
    )

    # Repeat sections may reuse labels; scope presence checks to the section.
    def _ensure_in_section(section: FormSection, fields: Sequence[Tuple[str, str]]) -> None:
        present = {
            _norm(it.label)
            for it in FormItem.query.filter_by(section_id=section.id, archived=False).all()
        }
        for order, (label, qtype) in enumerate(fields, start=1):
            if _norm(label) in present:
                continue
            _question(
                template=template,
                section=section,
                version=version,
                label=label,
                order=float(order),
                qtype=qtype,
            )
            present.add(_norm(label))

    _ensure_in_section(
        last_ap,
        (("Action point", "textarea"), ("Follow up / comments", "text")),
    )
    _ensure_in_section(
        next_ap,
        (
            ("Action point", "textarea"),
            ("By whom (names)", "text"),
            ("By when", "text"),
        ),
    )


def _build_final_structure(template: FormTemplate, version: FormTemplateVersion) -> None:
    labels = _existing_labels(version.id)
    info = _section(template=template, version=version, name="Project information", order=1)
    results = _section(template=template, version=version, name="Results and impact", order=2)
    collab = _section(template=template, version=version, name="Collaboration", order=3)
    learning = _section(template=template, version=version, name="Learning", order=4)
    db.session.flush()

    _fill_project_info(
        labels,
        template,
        version,
        info,
        extra=(("Overview of the initiative as planned", "textarea"),),
    )

    for label, qtype, options in (
        ("Review author(s)", "text", None),
        ("Review date", "date", None),
        ("Overview of achieved results", "textarea", None),
        ("Major changes from the original plan", "textarea", None),
        ("Overall implementation assessment", "single_choice", layout.FINAL_OVERALL),
        ("Activities' implementation", "single_choice", layout.FINAL_ACTIVITIES),
        ("To the National Society development", "textarea", None),
        (
            "To the National Society humanitarian impacts and resilience of communities",
            "textarea",
            None,
        ),
        ("Unexpected outcomes or impacts", "textarea", None),
        ("Actual beneficiaries reached", "textarea", None),
    ):
        _add_if_missing(
            labels,
            label=label,
            create_fn=lambda label=label, qtype=qtype, options=options, order=len(labels) + 1: _question(
                template=template,
                section=results,
                version=version,
                label=label,
                order=float(order),
                qtype=qtype,
                options=options,
            ),
        )

    _add_if_missing(
        labels,
        label="Outcomes and outputs",
        create_fn=lambda: _plugin(
            template=template,
            section=results,
            version=version,
            label="Outcomes and outputs",
            order=float(len(labels) + 1),
            plugin_type="nsd_logframe",
            plugin_config={"mode": "report"},
        ),
    )

    _add_if_missing(
        labels,
        label="Home government",
        create_fn=lambda: _question(
            template=template,
            section=collab,
            version=version,
            label="Home government",
            order=1,
            qtype="single_choice",
            options=("Yes", "No"),
        ),
    )
    _add_if_missing(
        labels,
        label="RCRC partners",
        create_fn=lambda: _question(
            template=template,
            section=collab,
            version=version,
            label="RCRC partners",
            order=2,
            qtype="textarea",
        ),
    )
    _add_if_missing(
        labels,
        label="Other partners",
        create_fn=lambda: _plugin(
            template=template,
            section=collab,
            version=version,
            label="Other partners",
            order=3,
            plugin_type="nsd_list",
            plugin_config={
                "add_label": "Add partner",
                "columns": [{"key": "name", "label": "Name", "type": "text"}],
            },
        ),
    )
    _add_if_missing(
        labels,
        label="New partnerships",
        create_fn=lambda: _plugin(
            template=template,
            section=collab,
            version=version,
            label="New partnerships",
            order=4,
            plugin_type="nsd_list",
            plugin_config={
                "add_label": "Add partnership",
                "columns": [
                    {
                        "key": "type",
                        "label": "Type",
                        "type": "select",
                        "options": list(layout.PARTNER_TYPES),
                    },
                    {"key": "who", "label": "Who", "type": "text"},
                    {"key": "purpose", "label": "Purpose", "type": "text"},
                ],
            },
        ),
    )

    for order, label in enumerate(
        (
            "Share key lessons learned from the implementation and results of the initiative",
            "What would you do differently next time?",
            "Any tips or tools you would like to share with other National Societies?",
            "Additional information",
        ),
        start=1,
    ):
        _add_if_missing(
            labels,
            label=label,
            create_fn=lambda label=label, order=order: _question(
                template=template,
                section=learning,
                version=version,
                label=label,
                order=float(order),
                qtype="textarea",
            ),
        )


_BUILDERS = {
    "CBF quarter": _build_quarter_structure,
    "CBF final report": _build_final_structure,
}


def _get_or_create_published(name: str, description: str, owner_id: Optional[int]) -> Tuple[FormTemplate, FormTemplateVersion, bool]:
    """Return published (template, version). Creates or promotes when needed."""
    version = (
        FormTemplateVersion.query.filter(FormTemplateVersion.name == name)
        .order_by(FormTemplateVersion.id.desc())
        .first()
    )
    created = False
    if version is None:
        template = FormTemplate(created_by=owner_id, owned_by=owner_id)
        db.session.add(template)
        db.session.flush()
        now = utcnow()
        version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status=FormTemplateVersionStatusValue.published,
            name=name,
            description=description,
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
        created = True
        log.info("NSD templates: created published template %r (id=%s)", name, template.id)
        return template, version, created

    template = version.template
    if template is None:
        raise RuntimeError(f"FormTemplateVersion {version.id} has no template")

    changed = False
    if version.status != FormTemplateVersionStatusValue.published:
        version.status = FormTemplateVersionStatusValue.published
        changed = True
    if template.published_version_id != version.id:
        template.published_version_id = version.id
        changed = True
    if changed:
        log.info("NSD templates: published existing version for %r (id=%s)", name, template.id)
    return template, version, created


def ensure_cbf_report_templates(*, commit: bool = True) -> Dict[str, int]:
    """Ensure quarter + final CBF templates exist and are published with required fields.

    Returns ``{template_key: template_id}`` for the required report templates.
    """
    owner_id = _owner_id()
    out: Dict[str, int] = {}
    dirty = False

    specs = (
        (
            "CBF quarter",
            layout.TEMPLATE_NAMES["CBF quarter"],
            "NSD CBF quarterly progress report (auto-created for master import).",
        ),
        (
            "CBF final report",
            layout.TEMPLATE_NAMES["CBF final report"],
            "NSD CBF final report (auto-created for master import).",
        ),
    )

    for key, name, description in specs:
        before_items = 0
        template, version, created = _get_or_create_published(name, description, owner_id)
        before_items = FormItem.query.filter_by(version_id=version.id, archived=False).count()
        builder = _BUILDERS[key]
        builder(template, version)
        db.session.flush()
        after_items = FormItem.query.filter_by(version_id=version.id, archived=False).count()
        if created or after_items > before_items:
            dirty = True
            log.info(
                "NSD templates: ensured %r structure (%s -> %s items)",
                name,
                before_items,
                after_items,
            )
        out[key] = int(template.id)

    if dirty and commit:
        db.session.commit()
    return out
