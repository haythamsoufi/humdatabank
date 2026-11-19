"""GO-shaped operational update and final report exports. No database."""

from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest

from plugins.dref_monitoring.services.docx_export import render_docx
from plugins.dref_monitoring.services.report_document import (
    FINANCE,
    INTERVENTION,
    build_report,
    export_narrative,
    running_header,
)

pytestmark = pytest.mark.unit


def _source(**overrides):
    base = {
        "kind": "operational_update",
        "appeal_code": "MDRZZ001",
        "disaster_name": "Zedland Flood",
        "country_name": "Zedland",
        "hazard": "Flood",
        "crisis_category": "Yellow",
        "appeal_type": "DREF",
        "pillar": "Response",
        "onset": "Sudden",
        "districts": "Capital",
        "date_of_disaster": date(2026, 1, 2),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 6, 30),
        "timeframe_months": 6,
        "reporting_start": date(2026, 1, 1),
        "reporting_end": date(2026, 1, 31),
        "total_approved": 10000,
        "people_affected": 5000,
        "people_targeted": 80,
        "funds_received": True,
        "expenditure": 2500,
        "narrative": "",
        "baselines": [
            {
                "stage": "Application",
                "total_approved": 8000,
                "end_date": date(2026, 4, 30),
                "people_targeted": 60,
                "sectors": [{"key": "health", "label": "Health", "budget_chf": "6000", "people_targeted": 60}],
            },
            {
                "stage": "Operational update",
                "total_approved": 10000,
                "end_date": date(2026, 6, 30),
                "people_targeted": 80,
                "sectors": [{"key": "health", "label": "Health", "budget_chf": "8000", "people_targeted": 80}],
            },
        ],
        "changes": [
            {
                "status": "approved",
                "field": "end_date",
                "target_type": "operation",
                "old_value": "2026-04-30",
                "new_value": "2026-06-30",
                "justification": "Rains continued.",
            }
        ],
        "sectors": [
            {
                "label": "Health",
                "budget_chf": 8000,
                "people_targeted": 80,
                "expenditure": 2500,
                "activities": [
                    {
                        "title": "Clinic support",
                        "status": "ongoing",
                        "percent": 40,
                        "households": 12,
                        "individuals": 40,
                        "expenditure": 2500,
                        "note": "Volunteers are visiting households.",
                        "women": 10,
                        "men": 8,
                        "girls": 12,
                        "boys": 10,
                        "indicators": [{"title": "People receiving first aid", "target": 100, "actual": 40, "unit": "people"}],
                    }
                ],
            }
        ],
        "risks": [
            {"title": "Access", "likelihood": "medium", "impact": "high", "mitigation": "Use local branches.", "status": "open"}
        ],
        "procurement": [{"item": "Mosquito nets", "milestone": "ordered"}],
        "delays": ["The supplier missed the first window."],
    }
    base.update(overrides)
    return base


def _headings(blocks, level):
    return [block.text for block in blocks if block.kind == "heading" and block.level == level]


def _text(blocks):
    parts = []
    for block in blocks:
        if block.text:
            parts.append(block.text)
        parts.extend(" ".join(row) for row in block.rows)
    return "\n".join(parts)


def test_template_prose_is_left_out_and_an_edit_is_kept():
    template = SimpleNamespace(edited_body=None, body="Operational update for MDRZZ001", ai_used=False)
    assert export_narrative(template) == ""
    edited = SimpleNamespace(edited_body="The river stayed high.", body="Operational update for MDRZZ001", ai_used=False)
    assert export_narrative(edited) == "The river stayed high."
    generated = SimpleNamespace(edited_body=None, body="The river stayed high.", ai_used=True)
    assert export_narrative(generated) == "The river stayed high."


def test_operational_update_follows_the_go_outline_and_does_not_invent_the_event():
    blocks = build_report(_source())
    headings = _headings(blocks, 1)
    assert headings[0] == "Description of the event"
    assert "Summary of changes" in headings
    assert INTERVENTION["operational_update"] in headings
    assert FINANCE["operational_update"] in headings
    assert "Implementation" not in headings
    assert "Financial report" not in headings
    event = next(block for block in blocks if block.kind == "heading" and block.text == "What happened, where and when?")
    following = blocks[blocks.index(event) + 1]
    assert following.kind == "paragraph"
    assert following.text == ""
    body = _text(blocks)
    assert "CHF 8,000" in body and "CHF 10,000" in body
    assert "Rains continued." in body
    assert "People receiving first aid" in body
    assert "40 people" in body
    assert "Clinic support is ongoing (40% complete)." in body
    assert "The supplier missed the first window." in body
    indicator = next(block for block in blocks if block.kind == "table" and block.headers[:1] == ("Title",))
    assert indicator.headers == ("Title", "Target", "Actual")
    assert indicator.rows[0][1] == "100 people"
    assert indicator.rows[0][2] == "40 people"


def test_final_report_uses_implementation_and_a_variance_line():
    blocks = build_report(_source(kind="final_report", narrative="Household visits continued through June."))
    headings = _headings(blocks, 1)
    assert "Summary of changes" not in headings
    assert "Planned intervention" not in headings
    assert "Budget overview" not in headings
    assert INTERVENTION["final_report"] in headings
    assert FINANCE["final_report"] in headings
    assert "Challenges" in _headings(blocks, 2)
    assert "Draft narrative" in headings
    body = _text(blocks)
    assert "Household visits continued through June." in body
    assert "CHF 7,500 under the approved allocation" in body
    assert "Who was targeted by this operation?" in _headings(blocks, 2)
    assert running_header(_source(kind="final_report")) == "MDRZZ001  ·  Final report"


def test_a_single_stage_does_not_invent_a_revision():
    blocks = build_report(_source(baselines=[{
        "stage": "Application",
        "total_approved": 10000,
        "end_date": date(2026, 6, 30),
        "people_targeted": 80,
        "sectors": [],
    }], changes=[]))
    body = _text(blocks)
    assert "No revision between stages is recorded." in body
    assert "changed from" not in body


def test_word_file_uses_heading_styles_and_an_outline_level():
    blocks = build_report(_source())
    payload = render_docx(blocks, running_header(_source()))
    archive = zipfile.ZipFile(BytesIO(payload))
    styles = archive.read("word/styles.xml").decode("utf-8")
    document = archive.read("word/document.xml").decode("utf-8")
    assert 'w:styleId="Heading1"' in styles
    assert 'w:styleId="Heading2"' in styles
    assert 'w:styleId="Heading3"' in styles
    assert 'w:styleId="Title"' in styles
    assert 'w:styleId="Note"' in styles
    assert "Montserrat" in styles
    assert "011E41" in styles
    assert "EF3340" in styles
    assert 'w:val="Heading1"' in document
    assert 'w:val="Heading2"' in document
    assert 'w:val="Title"' in document
    assert "MDRZZ001" in document
    assert "Planned intervention" in document
    assert "People receiving first aid" in document
    heading = styles.split('w:styleId="Heading1"', 1)[1].split("</w:style>", 1)[0]
    assert 'w:val="0"' in heading


def test_pdf_uses_the_same_outline_and_weasyprint_writes_a_file():
    from plugins.dref_monitoring.services.pdf_export import _html, render_pdf

    html = _html(build_report(_source()), running_header(_source()))
    assert "MDRZZ001" in html
    assert "Planned intervention" in html
    assert "People receiving first aid" in html
    assert '<h1 class="chapter">Description of the event</h1>' in html
    pytest.importorskip("weasyprint")
    payload = render_pdf(build_report(_source()), running_header(_source()))
    assert payload.startswith(b"%PDF")
    assert len(payload) > 5000
