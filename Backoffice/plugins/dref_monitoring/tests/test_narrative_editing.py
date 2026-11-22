"""Editing the chapters of a draft: saving, going back to the model's text, rewriting one chapter with the model,
and reading an edited Word export back."""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document

from app.extensions import db
from app.models import AIJob
from plugins.dref_monitoring.access import Actor
from plugins.dref_monitoring.models import DrefDraft, DrefOperation
from plugins.dref_monitoring.services import draft_job
from plugins.dref_monitoring.services import narrative_format as fmt
from plugins.dref_monitoring.services.docx_export import GENERATED_TEXT_STYLE, render_docx
from plugins.dref_monitoring.services.docx_import import DocxImportError, analyze_docx, expected_reference
from plugins.dref_monitoring.services.draft_job import queue_draft_job, status_payload
from plugins.dref_monitoring.services.drafts import (
    TOO_LONG,
    chapters_of,
    generate_draft,
    narrative_fields,
    regenerate_section,
    reset_section,
    save_chapters,
)
from plugins.dref_monitoring.services.sources import narrative_sources, sources_state
from plugins.dref_monitoring.services.go_sync import apply_rows
from plugins.dref_monitoring.services.llm import live_view, partial_chapters
from plugins.dref_monitoring.services.report_document import build_report
from plugins.dref_monitoring.tests.test_report_export import _source
from tests.factories import create_test_country

# ---- no database -----------------------------------------------------------------------------


@pytest.mark.unit
def test_a_chapter_keeps_its_formatting_and_the_figures_text_is_marked_generated():
    html = "<p>Rain <strong>flooded</strong> the town.</p><ul><li>Roads cut</li><li>Bridges down</li></ul>"
    blocks = build_report(_source(narratives={"what_happened": html}))
    event = next(block for block in blocks if block.text == "What happened, where and when?")
    chapter = blocks[blocks.index(event) + 1]
    assert chapter.key == "what_happened" and chapter.generated is False
    assert chapter.html == html
    assert [node.type for node in chapter.nodes] == ["p", "ul"]
    date = blocks[blocks.index(next(b for b in blocks if b.text == "Date of event")) + 1]
    assert date.generated is True and date.key == "date-of-event"


@pytest.mark.unit
def test_a_figure_section_can_be_rewritten_and_stays_out_of_the_chapter_above_it():
    blocks = build_report(_source())
    progress = next(block for block in blocks if block.key == "progress-1")
    assert progress.figure and progress.generated
    assert "Clinic support is ongoing (40% complete)." in progress.text
    edited = build_report(_source(block_edits={"progress-1": "<p>The clinic stayed open.</p><script>alert(1)</script>"}))
    progress = next(block for block in edited if block.key == "progress-1")
    assert progress.text == "The clinic stayed open."
    assert progress.generated is True
    document = Document(BytesIO(_docx(edited)))
    paragraph = document.paragraphs[_paragraph_after(document, "Progress towards outcome") + 1]
    assert paragraph.style.name == GENERATED_TEXT_STYLE
    assert paragraph.text == "The clinic stayed open."


@pytest.mark.unit
def test_every_chapter_of_the_report_type_has_a_place_to_write():
    blocks = build_report(_source())
    keys = [block.key for block in blocks if block.key]
    assert "summary_of_changes" in keys and "challenges" not in keys
    final = [block.key for block in build_report(_source(kind="final_report")) if block.key]
    assert "challenges" in final and "summary_of_changes" not in final


def _docx(blocks, **kwargs):
    return render_docx(blocks, "MDRZZ001", reference=expected_reference(3, 5), **kwargs)


def _paragraph_after(document, heading):
    paragraphs = document.paragraphs
    for index, paragraph in enumerate(paragraphs):
        if paragraph.text.strip() == heading and paragraph.style.name.startswith("Heading"):
            return index
    raise AssertionError(f"No heading {heading}")


def _draft(**overrides):
    values = {
        "id": 5,
        "report_kind": "operational_update",
        "language": "en",
        "edited_body": None,
        "body": "",
        "ai_used": False,
        "sections": {"narrative_mode": "manual"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.unit
def test_the_word_file_keeps_links_colour_highlight_and_strike():
    html = (
        '<p>See <a href="https://example.org/report" target="_blank" rel="noopener noreferrer">the update</a> '
        'and <span style="color:#e03e2d;background-color:#ffff00"><s>this</s></span>.</p>'
    )
    document = Document(BytesIO(_docx(build_report(_source(narratives={"what_happened": html})))))
    start = _paragraph_after(document, "What happened, where and when?")
    paragraph = document.paragraphs[start + 1]
    assert paragraph._p.xpath(".//w:hyperlink")
    assert paragraph._p.xpath('.//w:color[@w:val="E03E2D"]')
    assert paragraph._p.xpath('.//w:shd[@w:fill="FFFF00"]')
    assert paragraph._p.xpath(".//w:strike")
    result = analyze_docx(
        _docx(build_report(_source(narratives={"what_happened": html}))),
        _draft(edited_body=json.dumps({"what_happened": html})),
        SimpleNamespace(id=3),
    )
    row = next(item for item in result["chapters"] if item["key"] == "what_happened")
    assert row["status"] == "unchanged"


@pytest.mark.unit
def test_the_word_file_carries_formatting_lists_and_a_reference():
    html = "<p>Rain <strong>flooded</strong> the town.</p><ol><li>Roads cut</li><li>Bridges down</li></ol>"
    document = Document(BytesIO(_docx(build_report(_source(narratives={"what_happened": html})))))
    assert document.core_properties.identifier == expected_reference(3, 5)
    start = _paragraph_after(document, "What happened, where and when?")
    first, second, third = document.paragraphs[start + 1 : start + 4]
    assert first.text == "Rain flooded the town."
    assert [run.text for run in first.runs if run.bold] == ["flooded"]
    assert second.style.name == "List Number" and third.style.name == "List Number"
    generated = document.paragraphs[_paragraph_after(document, "Date of event") + 1]
    assert generated.style.name == GENERATED_TEXT_STYLE


@pytest.mark.unit
def test_an_edited_word_file_gives_back_only_what_a_person_wrote():
    raw = _docx(build_report(_source(narratives={"what_happened": "<p>The river rose.</p>"})))
    document = Document(BytesIO(raw))
    # An edit in an existing chapter, a bullet list in an empty one, and text under a heading that is not a chapter.
    first = document.paragraphs[_paragraph_after(document, "What happened, where and when?") + 1]
    first.runs[0].text = "The river rose and stayed high."
    needs = document.paragraphs[_paragraph_after(document, "Needs (gaps) identified") + 1]
    needs.style = document.styles["List Bullet"]
    needs.add_run("Clean water")
    second = document.add_paragraph("Shelter kits", style="List Bullet")
    needs._p.addnext(second._p)
    contact = document.paragraphs[_paragraph_after(document, "Contact information") + 1]
    contact.add_run("Call Sam")
    out = BytesIO()
    document.save(out)

    result = analyze_docx(out.getvalue(), _draft(edited_body=json.dumps({"what_happened": "<p>The river rose.</p>"})), SimpleNamespace(id=3))
    rows = {row["key"]: row for row in result["chapters"]}
    assert rows["what_happened"]["status"] == "changed"
    assert rows["what_happened"]["html"] == "<p>The river rose and stayed high.</p>"
    assert rows["needs"]["status"] == "added"
    assert rows["needs"]["html"] == "<ul><li>Clean water</li><li>Shelter kits</li></ul>"
    assert rows["overall_objective"]["status"] == "unchanged"
    assert result["ignored"] == [{"heading": "Contact information", "paragraphs": 1}]
    assert result["warnings"] == []


@pytest.mark.unit
def test_an_untouched_export_changes_nothing():
    raw = _docx(build_report(_source(narratives={"needs": "<p>Water is short.</p>"})))
    result = analyze_docx(raw, _draft(edited_body=json.dumps({"needs": "<p>Water is short.</p>"})), SimpleNamespace(id=3))
    assert all(row["status"] in ("unchanged", "missing") for row in result["chapters"])


@pytest.mark.unit
def test_a_file_from_another_report_is_flagged_and_a_bad_file_is_refused():
    raw = render_docx(build_report(_source()), "MDRZZ001", reference=expected_reference(9, 99))
    result = analyze_docx(raw, _draft(), SimpleNamespace(id=3))
    assert "This file was exported from a different report." in result["warnings"]
    with pytest.raises(DocxImportError):
        analyze_docx(b"not a zip", _draft(), SimpleNamespace(id=3))
    empty = BytesIO()
    document = Document()
    document.add_paragraph("Nothing to see")
    document.save(empty)
    with pytest.raises(DocxImportError):
        analyze_docx(empty.getvalue(), _draft(), SimpleNamespace(id=3))


@pytest.mark.unit
def test_a_french_export_maps_back_by_heading():
    raw = _docx(build_report({**_source(narratives={"needs": "<p>Eau</p>"}), "language": "fr"}), language="fr")
    document = Document(BytesIO(raw))
    index = next(
        i for i, p in enumerate(document.paragraphs) if p.style.name.startswith("Heading") and p.text.startswith("Besoins")
    )
    document.paragraphs[index + 1].runs[0].text = "Eau potable"
    out = BytesIO()
    document.save(out)
    result = analyze_docx(out.getvalue(), _draft(edited_body=json.dumps({"needs": "<p>Eau</p>"}), language="fr"), SimpleNamespace(id=3))
    needs = next(row for row in result["chapters"] if row["key"] == "needs")
    assert needs["html"] == "<p>Eau potable</p>"


@pytest.mark.unit
def test_the_live_view_reads_a_chapter_that_is_still_being_written():
    keys = ("what_happened", "needs")
    text = '{"what_happened": "Rain flooded the town.", "needs": "Water and sh'
    found = partial_chapters(text, keys)
    assert found["what_happened"] == ("Rain flooded the town.", True)
    assert found["needs"] == ("Water and sh", False)
    live = live_view(text, keys)
    assert live == {"done": ["what_happened"], "writing": "needs", "text": "Water and sh"}


# ---- database --------------------------------------------------------------------------------


def _row():
    return {
        "id": "Dref-narr-1",
        "appeal_code": "MDRNAR01",
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
        "end_date_of_operation": "2026-06-30",
        "operation_timeframe": 6,
        "operation_status": "active",
        "is_latest_stage": True,
        "sector_health": True,
        "sector_health_budget": 8000,
        "sector_health_people_targeted": 80,
        "date_of_approval": "2026-01-05",
    }


@pytest.fixture
def operation(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    apply_rows([_row()])
    return DrefOperation.query.filter_by(appeal_code="MDRNAR01").one()


def _manager(user_id):
    return Actor(user_id, True, frozenset(), frozenset(), {})


def _ai_draft(operation, user_id, chapters=None):
    chapters = chapters or {"what_happened": "Rain flooded the town.", "needs": "Water is short."}
    result = generate_draft(
        operation,
        "operational_update",
        _manager(user_id),
        complete=lambda payload, kind, **kw: json.dumps(chapters),
        model_name="test-model",
        narrative="ai",
    )
    return db.session.get(DrefDraft, result["draft_id"])


@pytest.mark.db
def test_saving_chapters_stores_clean_html_and_says_why_one_failed(operation, system_manager_user):
    draft = _ai_draft(operation, system_manager_user.id)
    error, saved, failed = save_chapters(
        draft,
        operation,
        {
            "needs": "<p>Water <b>is</b> short<script>alert(1)</script></p>",
            "who_targeted": "x" * 7000,
            "not_a_chapter": "hello",
        },
        _manager(system_manager_user.id),
    )
    assert error is None
    assert saved == {"needs": "<p>Water <strong>is</strong> short</p>"}
    again, saved_figure, failed_figure = save_chapters(
        draft, operation, {"progress-1": "<p>The clinic stayed open.</p>"}, _manager(system_manager_user.id)
    )
    assert again is None and not failed_figure
    assert saved_figure == {"progress-1": "<p>The clinic stayed open.</p>"}
    assert draft.sections["block_edits"]["progress-1"] == "<p>The clinic stayed open.</p>"
    assert "Water" in chapters_of(draft)["needs"]
    assert failed["who_targeted"] == TOO_LONG and failed["not_a_chapter"] == "Unknown chapter."
    db.session.refresh(draft)
    stored = chapters_of(draft)
    assert stored["needs"] == "<p>Water <strong>is</strong> short</p>"
    assert fmt.to_plain(stored["what_happened"]) == "Rain flooded the town."
    assert draft.body and "Water is short." in draft.body  # what the model wrote stays


@pytest.mark.db
def test_a_chapter_goes_back_to_what_the_model_wrote(operation, system_manager_user):
    draft = _ai_draft(operation, system_manager_user.id)
    actor = _manager(system_manager_user.id)
    save_chapters(draft, operation, {"needs": "<p>My own words.</p>"}, actor)
    rows = {row["key"]: row for row in narrative_fields(draft)}
    assert rows["needs"]["edited"] is True and rows["what_happened"]["edited"] is False
    error, html = reset_section(draft, operation, "needs", actor)
    assert error is None and fmt.to_plain(html) == "Water is short."
    assert reset_section(draft, operation, "overall_objective", actor)[0] == "The model did not write this chapter."
    assert reset_section(draft, operation, "nope", actor)[0] == "Unknown chapter."


@pytest.mark.db
def test_a_figures_only_or_validated_draft_cannot_be_edited(operation, system_manager_user):
    actor = _manager(system_manager_user.id)
    figures = db.session.get(
        DrefDraft, generate_draft(operation, "operational_update", actor, narrative="none")["draft_id"]
    )
    assert save_chapters(figures, operation, {"needs": "x"}, actor)[0] == "This report is figures only and has no narrative to edit."
    draft = _ai_draft(operation, system_manager_user.id)
    draft.status = "validated"
    db.session.commit()
    assert save_chapters(draft, operation, {"needs": "x"}, actor)[0] == "This draft is already validated."


@pytest.mark.db
def test_a_draft_keeps_the_sources_the_model_named_and_a_rewrite_can_replace_one_chapter(
    operation, system_manager_user
):
    actor = _manager(system_manager_user.id)

    def complete(payload, kind, **kwargs):
        assert any(item["id"] == "operation" for item in payload["source_catalog"])
        assert all("url" not in item for item in payload["source_catalog"])
        return json.dumps(
            {
                "what_happened": "Rain flooded the town.",
                "needs": "Water is short.",
                "sources": [
                    {
                        "id": "operation",
                        "chapter": "what_happened",
                        "used_for": "The flood is recorded in the monitoring figures.",
                    },
                    {"id": "not-a-source", "chapter": "needs", "used_for": "Invented."},
                ],
            }
        )

    result = generate_draft(
        operation,
        "operational_update",
        actor,
        complete=complete,
        model_name="test-model",
        narrative="ai",
    )
    draft = db.session.get(DrefDraft, result["draft_id"])
    rows = narrative_sources(draft)
    assert sources_state(draft) == "listed"
    assert [(row["chapter"], row["id"]) for row in rows] == [("what_happened", "operation")]
    assert rows[0]["url"] == f"/dref-monitoring/operations/{operation.id}"
    assert "javascript" not in rows[0]["url"]

    def rewrite(payload, kind, key, progress=None):
        return json.dumps(
            {
                key: "Safe water is the first need.",
                "sources": [
                    {"id": "operation", "chapter": key, "used_for": "People still need water.", "url": "https://evil.example"}
                ],
            }
        )

    rewritten = regenerate_section(draft, operation, actor, "needs", complete_section=rewrite)
    assert rewritten["ok"] is True
    assert rewritten["sources"][0]["id"] == "operation"
    assert rewritten["sources"][0]["url"] == f"/dref-monitoring/operations/{operation.id}"
    assert "evil.example" not in rewritten["sources"][0]["url"]
    db.session.refresh(draft)
    assert narrative_sources(draft) == rows

    error, saved, failed = save_chapters(
        draft,
        operation,
        {"needs": rewritten["html"]},
        actor,
        sources={"needs": rewritten["sources"]},
    )
    assert error is None and not failed and "needs" in saved
    assert [(row["chapter"], row["used_for"]) for row in narrative_sources(draft)] == [
        ("what_happened", "The flood is recorded in the monitoring figures."),
        ("needs", "People still need water."),
    ]
    error, html = reset_section(draft, operation, "needs", actor)
    assert error is None and "Safe water" not in fmt.to_plain(html)
    assert [row["chapter"] for row in narrative_sources(draft)] == ["what_happened"]


@pytest.mark.db
def test_rewriting_one_chapter_returns_text_and_stores_nothing(operation, system_manager_user):
    draft = _ai_draft(operation, system_manager_user.id)
    actor = _manager(system_manager_user.id)
    seen = {}

    def complete_section(payload, kind, key, progress=None):
        seen.update(payload["rewrite"], key=key)
        return json.dumps({key: "- Clean water\n- Shelter kits"})

    result = regenerate_section(
        draft,
        operation,
        actor,
        "needs",
        complete_section=complete_section,
        instruction="Use bullets",
        current="<p>My draft</p>",
    )
    assert result["ok"] is True
    assert result["html"] == "<ul><li>Clean water</li><li>Shelter kits</li></ul>"
    assert seen["current_text"] == "My draft" and seen["instruction"] == "Use bullets" and seen["key"] == "needs"
    assert "what_happened" in seen["other_chapters"] and "needs" not in seen["other_chapters"]
    db.session.refresh(draft)
    assert fmt.to_plain(chapters_of(draft)["needs"]) == "Water is short."
    empty = regenerate_section(draft, operation, actor, "needs", complete_section=lambda *a, **k: "{}")
    assert empty == {
        "ok": False,
        "error": "Nothing in the sources for this operation covers this chapter, so it stays empty.",
    }
    broken = regenerate_section(draft, operation, actor, "needs", complete_section=lambda *a, **k: "not json")
    assert broken == {"ok": False, "error": "The model did not return text for this chapter."}
    assert regenerate_section(draft, operation, actor, "needs", complete_section=None)["error"] == "AI drafting is not enabled."


def _run_job(app, job_id):
    job = db.session.get(AIJob, job_id)
    draft_job._process_item(app, job_id=job_id, item_id=job.items[0].id)
    db.session.expire_all()
    return db.session.get(AIJob, job_id)


@pytest.mark.db
def test_a_chapter_rewrite_runs_as_a_job_and_hands_the_text_back(app, operation, system_manager_user, monkeypatch):
    draft = _ai_draft(operation, system_manager_user.id)
    monkeypatch.setattr("app.services.ai.ai_job_runner.start_ai_job_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr("plugins.dref_monitoring.config_store.ai_enabled", lambda: True)
    monkeypatch.setattr("plugins.dref_monitoring.services.context.load_context", lambda *a, **k: {})
    monkeypatch.setattr(
        "plugins.dref_monitoring.services.llm.complete_section_with_engine",
        lambda payload, kind, key, progress=None: json.dumps({key: "Safe water is the first need."}),
    )
    params = {
        "action": "section",
        "operation_id": operation.id,
        "kind": "operational_update",
        "draft_id": draft.id,
        "section": "needs",
        "current": "<p>Water is short.</p>",
    }
    job_id, created = queue_draft_job(system_manager_user.id, params, app)
    again, created_again = queue_draft_job(system_manager_user.id, params, app)
    other, created_other = queue_draft_job(system_manager_user.id, {**params, "section": "who_targeted"}, app)
    assert created and not created_again and again == job_id and created_other and other != job_id
    payload = status_payload(_run_job(app, job_id))
    assert payload["status"] == "completed"
    assert payload["section"] == "needs" and payload["kind"] == "operational_update"
    assert payload["summary"]["section"] == "needs"
    assert payload["summary"]["html"] == "<p>Safe water is the first need.</p>"
    db.session.refresh(draft)
    assert fmt.to_plain(chapters_of(draft)["needs"]) == "Water is short."


@pytest.fixture
def plugin_on(app):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    yield
    app.plugin_manager.active_plugins = previous


@pytest.mark.db
def test_the_page_saves_resets_and_queues_a_rewrite(app, operation, system_manager_user, logged_in_sm_client, plugin_on, monkeypatch):
    draft = _ai_draft(operation, system_manager_user.id)
    base = f"/dref-monitoring/operations/{operation.id}/drafts/{draft.id}"
    page = logged_in_sm_client.get(base)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'id="dref-narrative-config"' in html and 'data-chapter="needs"' in html
    assert "Water is short." in html

    saved = logged_in_sm_client.post(f"{base}/chapters", json={"sections": {"needs": "<p>Edited <em>needs</em></p>"}})
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["ok"] is True and body["saved"]["needs"]["html"] == "<p>Edited <em>needs</em></p>"
    assert body["saved"]["needs"]["words"] == 2

    rejected = logged_in_sm_client.post(f"{base}/chapters", json={"sections": {"needs": "x" * 7000}})
    assert rejected.status_code == 400 and rejected.get_json()["failed"]["needs"] == TOO_LONG
    assert logged_in_sm_client.post(f"{base}/chapters", json={}).status_code == 400

    reset = logged_in_sm_client.post(f"{base}/chapters/needs/reset")
    assert reset.status_code == 200 and reset.get_json()["words"] == 3
    assert logged_in_sm_client.post(f"{base}/chapters/nope/reset").status_code == 400

    monkeypatch.setattr("app.services.ai.ai_job_runner.start_ai_job_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr("plugins.dref_monitoring.routes.ai_enabled", lambda: True)
    queued = logged_in_sm_client.post(f"{base}/chapters/needs/generate", json={"instruction": "shorter", "current": "<p>x</p>"})
    assert queued.status_code == 202
    assert queued.get_json()["section"] == "needs" and queued.get_json()["created"] is True
    assert logged_in_sm_client.post(f"{base}/chapters/nope/generate", json={}).status_code == 404


@pytest.mark.db
def test_the_page_round_trips_a_word_export(app, operation, system_manager_user, logged_in_sm_client, plugin_on):
    draft = _ai_draft(operation, system_manager_user.id)
    base = f"/dref-monitoring/operations/{operation.id}/drafts/{draft.id}"
    exported = logged_in_sm_client.get(f"{base}/export.docx")
    assert exported.status_code == 200
    document = Document(BytesIO(exported.data))
    assert document.core_properties.identifier == expected_reference(operation.id, draft.id)
    heading = _paragraph_after(document, "What happened, where and when?")
    document.paragraphs[heading + 1].runs[0].text = "Rain flooded the whole district."
    out = BytesIO()
    document.save(out)
    out.seek(0)

    response = logged_in_sm_client.post(
        f"{base}/import.docx", data={"document": (out, "report.docx")}, content_type="multipart/form-data"
    )
    assert response.status_code == 200
    rows = {row["key"]: row for row in response.get_json()["chapters"]}
    assert rows["what_happened"]["status"] == "changed"
    assert rows["what_happened"]["html"] == "<p>Rain flooded the whole district.</p>"
    assert rows["needs"]["status"] == "unchanged"
    db.session.refresh(draft)
    assert fmt.to_plain(chapters_of(draft)["what_happened"]) == "Rain flooded the town."  # analysing saves nothing

    bad = logged_in_sm_client.post(
        f"{base}/import.docx", data={"document": (BytesIO(b"nope"), "report.docx")}, content_type="multipart/form-data"
    )
    assert bad.status_code == 400 and bad.get_json()["error"] == "This is not a Word (.docx) file."
    wrong = logged_in_sm_client.post(
        f"{base}/import.docx", data={"document": (BytesIO(b"nope"), "report.txt")}, content_type="multipart/form-data"
    )
    assert wrong.status_code == 400
