"""Fill the DREF operational monitoring template.

The template is one master form: every sector, then every indicator-bank row
marked Emergency. A country assignment does not use that whole list. The entry
form keeps the indicators that match the operation's monitoring plan, and lists
the planned activities under them. Each of those indicators collects one target
for the plan. It does not collect a reported total or a sex or age split.
``plugins.dref_monitoring.scripts.report_questions`` is where the other
questions are worded.
"""

from __future__ import annotations

import re

from app.extensions import db
from app.models.enums import FormTemplateVersionStatusValue, QuestionType
from app.models.form_items import FormItem
from app.models.forms import FormSection, FormTemplate, FormTemplateVersion
from app.models.indicator_bank import IndicatorBank, Sector
from plugins.dref_monitoring.constants import FIELD_TYPE, SECTORS, TEMPLATE_NAME
from plugins.dref_monitoring.models import DrefIndicator, DrefOperation
from plugins.dref_monitoring.scripts import report_questions

_QUESTION_TYPES = {member.value for member in QuestionType}
_LEVELS = ("primary", "secondary", "tertiary")
_REPORT_KEY = "__report__"
_OPERATION_KEY = "__operation__"
_OTHER_KEY = "__other__"
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_MIN_CONTAINED_FOLD = 6


def ensure_operation_template(operation: DrefOperation) -> FormTemplate:
    """Update the published DREF operational monitoring template. Safe to call again."""
    version = (
        FormTemplateVersion.query.filter(FormTemplateVersion.name == TEMPLATE_NAME)
        .order_by(FormTemplateVersion.id.asc())
        .first()
    )
    description = (
        "Routine DREF monitoring. One section per sector, with every emergency "
        "indicator from the indicator bank. An assignment shows the indicators on that "
        "operation's monitoring plan. Other fields are questions."
    )
    if version is None:
        template = FormTemplate()
        db.session.add(template)
        db.session.flush()
        version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status=FormTemplateVersionStatusValue.published,
            name=TEMPLATE_NAME,
            description=description,
        )
        db.session.add(version)
        db.session.flush()
        template.published_version_id = version.id
    else:
        template = version.template
        if template is None:
            raise RuntimeError(f"Form template version {version.id} has no template.")
        status = getattr(version.status, "value", version.status)
        if status != FormTemplateVersionStatusValue.published.value:
            version.status = FormTemplateVersionStatusValue.published
        if template.published_version_id != version.id:
            template.published_version_id = version.id
        version.description = description

    sections = _section_plan(operation)
    _sync_sections(template, version, sections)
    _retire_legacy_plugin_field(version)
    db.session.flush()
    return template


def _retire_legacy_plugin_field(version: FormTemplateVersion) -> None:
    """Archive the original single plugin item once the sector sections exist."""
    plugin_type = f"plugin_{FIELD_TYPE}"
    items = FormItem.query.filter_by(version_id=version.id, item_type=plugin_type, archived=False).all()
    section_ids = {item.section_id for item in items}
    for item in items:
        item.archived = True
    for section_id in section_ids:
        section = db.session.get(FormSection, section_id)
        if section is None:
            continue
        cfg = section.config if isinstance(section.config, dict) else {}
        if cfg.get("dref_managed"):
            continue
        still_active = FormItem.query.filter_by(section_id=section.id, archived=False).count()
        if still_active == 0:
            section.archived = True


def _section_plan(operation: DrefOperation) -> list[dict]:
    """Every sector, every emergency indicator, then the report questions.

    A temporary adapter match that points at a bank row which is not marked
    emergency is included too, so the assignment can show it. The shared template
    keeps the full list. ``limit_entry_fields`` drops the indicators that are not
    on that operation's plan before the assignment page is rendered.

    ``operation`` is unused. The template is shared; each assignment filters it.
    """
    del operation
    by_fold, by_go_key = _sector_index()
    emergency = (
        IndicatorBank.query.filter(
            IndicatorBank.archived.is_(False),
            IndicatorBank.emergency.is_(True),
        )
        .order_by(IndicatorBank.id.asc())
        .all()
    )
    have = {row.id for row in emergency}
    extra_ids = [
        row[0]
        for row in db.session.query(DrefIndicator.indicator_bank_id)
        .filter(DrefIndicator.bank_adapted.is_(True), DrefIndicator.indicator_bank_id.isnot(None))
        .distinct()
        .all()
        if row[0] not in have
    ]
    if extra_ids:
        emergency = list(emergency) + (
            IndicatorBank.query.filter(
                IndicatorBank.id.in_(extra_ids),
                IndicatorBank.archived.is_(False),
            )
            .order_by(IndicatorBank.id.asc())
            .all()
        )
    selected = list(SECTORS)
    sector_id_by_key: dict[str, int] = {}
    for key, label in selected:
        sector = _resolve_bank_sector(key, label, by_fold, by_go_key)
        if sector is not None:
            sector_id_by_key[key] = int(sector.id)
    buckets = _assign_indicators(emergency, sector_id_by_key, [key for key, _label in selected])
    placed = {indicator.id for rows in buckets.values() for indicator in rows}
    other = [indicator for indicator in emergency if indicator.id not in placed]
    other.sort(key=lambda row: (row.name or "").casefold())
    built = []
    for index, (key, label) in enumerate(selected, start=1):
        built.append(
            {
                "key": key,
                "name": label[:100],
                "order": index,
                "indicators": buckets.get(key, []),
                "sector_questions": True,
                "report_questions": False,
            }
        )
    if other:
        built.append(
            {
                "key": _OTHER_KEY,
                "name": "Other emergency indicators",
                "order": len(built) + 1,
                "indicators": other,
                "sector_questions": False,
                "report_questions": False,
            }
        )
    built.append(
        {
            "key": _REPORT_KEY,
            "name": "Notes",
            "name_translations": {
                "fr": "Notes",
                "es": "Notas",
                "ar": "ملاحظات",
            },
            # One field. The section heading would repeat the question label.
            "hide_header": True,
            "order": len(built) + 1,
            "indicators": [],
            "sector_questions": False,
            "report_questions": True,
        }
    )
    return built


def _entry_render(section_key: str) -> str:
    """How the assignment form should draw this section. The plugin owns that styling."""
    if section_key == _REPORT_KEY:
        return "dref-report"
    return "dref-sector"


def _section_config(section_key: str, *, hide_header: bool = False) -> dict:
    config = {
        "dref_managed": True,
        "dref_sector_key": section_key,
        # Core draws one target field, and stamps this key on the section for the sector script.
        "indicator_entry": "target",
        "entry_key": section_key,
        "entry_render": _entry_render(section_key),
    }
    if hide_header:
        config["hide_section_header"] = True
    return config


def _sync_sections(template: FormTemplate, version: FormTemplateVersion, planned: list[dict]) -> None:
    existing = FormSection.query.filter_by(version_id=version.id).all()
    by_key: dict[str, FormSection] = {}
    for section in existing:
        cfg = section.config if isinstance(section.config, dict) else {}
        key = cfg.get("dref_sector_key")
        if cfg.get("dref_managed") and key and key not in by_key:
            by_key[str(key)] = section

    wanted = set()
    for spec in planned:
        key = spec["key"]
        wanted.add(key)
        section = by_key.get(key)
        if section is None:
            section = FormSection(
                template_id=template.id,
                version_id=version.id,
                name=spec["name"],
                name_translations=_titled_translations(None, spec["name"], spec.get("name_translations")),
                order=float(spec["order"]),
                section_type="standard",
                config=_section_config(key, hide_header=bool(spec.get("hide_header"))),
            )
            db.session.add(section)
            db.session.flush()
            by_key[key] = section
        else:
            section.name = spec["name"]
            section.name_translations = _titled_translations(section.name_translations, spec["name"], spec.get("name_translations"))
            section.order = float(spec["order"])
            section.archived = False
            cfg = dict(section.config or {})
            fresh = _section_config(key, hide_header=bool(spec.get("hide_header")))
            if not spec.get("hide_header"):
                cfg.pop("hide_section_header", None)
            cfg.update(fresh)
            section.config = cfg
        _sync_items(template, version, section, spec)

    for key, section in by_key.items():
        if key not in wanted:
            section.archived = True
            _archive_managed_items(section)


def _sync_items(template: FormTemplate, version: FormTemplateVersion, section: FormSection, spec: dict) -> None:
    existing = FormItem.query.filter_by(section_id=section.id).all()
    indicators_by_id: dict[int, FormItem] = {}
    questions_by_key: dict[str, FormItem] = {}
    for item in existing:
        cfg = item.config if isinstance(item.config, dict) else {}
        if not cfg.get("dref_managed"):
            continue
        if item.item_type == "indicator" and item.indicator_bank_id:
            indicators_by_id[int(item.indicator_bank_id)] = item
        elif item.item_type == "question" and cfg.get("dref_question_key"):
            questions_by_key[str(cfg["dref_question_key"])] = item

    placements = _placements(spec)
    wanted_indicators: set[int] = set()
    wanted_questions: set[str] = set()
    seen_questions: set[str] = set()
    for kind, payload, order in placements:
        if kind == "indicator":
            bank_id = int(payload.id)
            wanted_indicators.add(bank_id)
            _upsert_indicator(
                template,
                version,
                section,
                indicators_by_id.get(bank_id),
                payload,
                order,
            )
            continue
        key = str(payload.get("key") or "").strip()[:80]
        label = str(payload.get("label") or "").strip()
        if not key or not label or key in seen_questions:
            continue
        seen_questions.add(key)
        wanted_questions.add(key)
        _upsert_question(
            template,
            version,
            section,
            questions_by_key.get(key),
            payload,
            key,
            order,
        )

    for bank_id, item in indicators_by_id.items():
        if bank_id not in wanted_indicators:
            item.archived = True
    for key, item in questions_by_key.items():
        if key not in wanted_questions:
            item.archived = True


def _placements(spec: dict) -> list[tuple]:
    """Budget and people targeted, then each indicator on its own, then the note."""
    placed = []
    cursor = 0
    if "sector_key" in spec:
        question_sector = spec.get("sector_key")
    else:
        question_sector = None if spec["key"] in {_REPORT_KEY, _OPERATION_KEY} else spec["key"]
    if spec.get("sector_questions"):
        for question in _customized(list(report_questions.SECTOR_HEADER_QUESTIONS), sector_key=question_sector, indicator=None):
            cursor += 1
            placed.append(("question", question, float(cursor)))
    for indicator in spec["indicators"]:
        cursor += 1
        placed.append(("indicator", indicator, float(cursor)))
    extra = []
    if spec.get("report_questions"):
        extra.extend(_customized(list(report_questions.REPORT_QUESTIONS), sector_key=None, indicator=None))
    for question in extra:
        cursor += 1
        placed.append(("question", question, float(cursor)))
    return placed


def _customized(raw: list[dict], *, sector_key, indicator) -> list[dict]:
    incoming = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        options = item.get("options")
        if isinstance(options, (list, tuple)):
            item["options"] = [str(option) for option in options]
        incoming.append(item)
    result = report_questions.customize_questions(incoming, sector_key=sector_key, indicator=indicator)
    if result is None:
        return []
    if not isinstance(result, list):
        raise TypeError("customize_questions must return a list of question dicts.")
    return [row for row in result if isinstance(row, dict)]


def _upsert_indicator(template, version, section, item, indicator: IndicatorBank, order: float) -> None:
    # A single target. The back office total and sex/age split is not collected here.
    managed = _managed_config(allowed_disaggregation_options=["total"], indicator_entry="target")
    if item is None:
        item = FormItem(
            section_id=section.id,
            version_id=version.id,
            template_id=template.id,
            item_type="indicator",
            label=indicator.name,
            order=order,
            config=managed,
        )
        db.session.add(item)
    item.item_type = "indicator"
    item.label = indicator.name
    item.order = order
    item.archived = False
    item.type = indicator.type
    item.unit = indicator.unit or ""
    item.indicator_bank_id = indicator.id
    item.indicator_type_id = indicator.indicator_type_id
    item.indicator_unit_id = indicator.indicator_unit_id
    cfg = dict(item.config or {})
    cfg.update(managed)
    item.config = cfg


def _upsert_question(template, version, section, item, spec: dict, key: str, order: float) -> None:
    qtype = str(spec.get("type") or "textarea").strip().lower()
    if qtype not in _QUESTION_TYPES:
        qtype = "textarea"
    label = str(spec.get("label") or "").strip()
    definition = str(spec.get("description") or spec.get("definition") or "").strip() or None
    options = spec.get("options") if qtype in {"single_choice", "multiple_choice"} else None
    if isinstance(options, (list, tuple)):
        options = [str(option) for option in options if str(option).strip()] or None
    else:
        options = None
    width = spec.get("width") or 12
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = 12
    width = min(12, max(1, width))
    config = _managed_config(dref_question_key=key)
    config["layout_column_width"] = width
    if item is None:
        item = FormItem(
            section_id=section.id,
            version_id=version.id,
            template_id=template.id,
            item_type="question",
            label=label,
            label_translations=_titled_translations(None, label, spec.get("label_translations")),
            type=qtype,
            order=order,
            definition=definition,
            options_json=options,
            config=config,
        )
        db.session.add(item)
        return
    item.item_type = "question"
    item.label = label
    item.label_translations = _titled_translations(item.label_translations, label, spec.get("label_translations"))
    item.type = qtype
    item.order = order
    item.archived = False
    item.definition = definition
    item.options_json = options
    cfg = dict(item.config or {})
    cfg.update(config)
    item.config = cfg


def _titled_translations(existing, title: str, extra) -> dict:
    """Keep the English title on the generator. Other languages in ``extra`` are written with it."""
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged["en"] = title
    if isinstance(extra, dict):
        for key, value in extra.items():
            code = str(key or "").strip().lower()
            text = str(value or "").strip()
            if code and code != "en" and text:
                merged[code] = text
    return merged


def _managed_config(**extra) -> dict:
    config = {
        "is_required": False,
        "layout_column_width": 12,
        "layout_break_after": False,
        "allowed_disaggregation_options": ["total"],
        "age_groups_config": None,
        "allow_data_not_available": False,
        "allow_not_applicable": False,
        "allow_disability_questions": False,
        "indirect_reach": False,
        "exclude_from_completion_rate": False,
        "privacy": "ifrc_network",
        "dref_managed": True,
    }
    config.update(extra)
    return config


def _archive_managed_items(section: FormSection) -> None:
    for item in FormItem.query.filter_by(section_id=section.id).all():
        cfg = item.config if isinstance(item.config, dict) else {}
        if cfg.get("dref_managed"):
            item.archived = True


def _assign_indicators(indicators, sector_id_by_key: dict[str, int], key_order: list[str]) -> dict[str, list]:
    """Each indicator is placed once, on the first selected sector among primary, secondary, tertiary."""
    key_by_id = {sector_id: key for key, sector_id in sector_id_by_key.items()}
    buckets = {key: [] for key in key_order}
    for indicator in indicators:
        raw = indicator.sector if isinstance(indicator.sector, dict) else {}
        for level in _LEVELS:
            sector_id = _as_int(raw.get(level))
            key = key_by_id.get(sector_id) if sector_id is not None else None
            if key is not None:
                buckets[key].append(indicator)
                break
    for key in buckets:
        buckets[key].sort(key=lambda row: (row.name or "").casefold())
    return buckets


def _sector_index():
    by_fold: dict[str, Sector] = {}
    for sector in Sector.query.order_by(Sector.id.asc()).all():
        _index_folded_name(by_fold, sector.name, sector)
        translations = sector.name_translations if isinstance(sector.name_translations, dict) else {}
        for value in translations.values():
            if isinstance(value, str):
                _index_folded_name(by_fold, value, sector)
    by_go_key: dict[str, Sector] = {}
    aliases = getattr(report_questions, "SECTOR_NAME_TO_KEY", None) or {}
    for name, go_key in aliases.items():
        sector = by_fold.get(_fold(str(name)))
        if sector is not None and go_key:
            by_go_key[str(go_key)] = sector
    return by_fold, by_go_key


def _resolve_bank_sector(key: str, label: str, by_fold: dict, by_go_key: dict):
    """Map a GO sector onto an indicator-bank sector.

    Prefer an explicit ``SECTOR_NAME_TO_KEY`` alias, then an exact folded name,
    then a unique containment match so "Shelter" still pairs with "Shelter and
    basic household items" and "Livelihoods" with "Food security and livelihoods".
    """
    sector = by_go_key.get(key)
    if sector is not None:
        return sector
    folded = _fold(label)
    sector = by_fold.get(folded)
    if sector is not None:
        return sector
    return _unique_contained_sector(folded, by_fold)


def _unique_contained_sector(folded_label: str, by_fold: dict):
    if not folded_label or len(folded_label) < _MIN_CONTAINED_FOLD:
        return None
    hits = []
    seen_ids = set()
    for bank_fold, sector in by_fold.items():
        if not bank_fold or sector is None:
            continue
        shorter, longer = (bank_fold, folded_label) if len(bank_fold) <= len(folded_label) else (folded_label, bank_fold)
        if len(shorter) < _MIN_CONTAINED_FOLD or shorter not in longer:
            continue
        sector_id = getattr(sector, "id", None)
        if sector_id in seen_ids:
            continue
        seen_ids.add(sector_id)
        hits.append(sector)
    if len(hits) == 1:
        return hits[0]
    return None


def _index_folded_name(by_fold: dict, name: str, sector: Sector) -> None:
    folded = _fold(name)
    if folded:
        by_fold.setdefault(folded, sector)


def _fold(value) -> str:
    text = _PARENTHETICAL.sub("", str(value or ""))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _as_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
