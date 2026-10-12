"""Real-browser check of editable variable matrix cells on the entry form.

Opt-in (needs Node, ``playwright-core`` and a Chrome/Chromium binary)::

    cd Backoffice && npm i --no-save playwright-core
    E2E_BROWSER=1 python -m pytest tests/e2e_browser -s

Optional env: ``CHROME_PATH`` (browser binary), ``E2E_PORT`` (default 5056).

It serves the app from the pytest process and drives the matrix with auto-loaded
rows whose editable variable column resolves from another assignment. Nothing is
saved, yet the page used to come back empty and fully green after a reload: leaving
the page stored an auto-fill draft, and restoring it persisted blank values for
cells that were disabled at the time. The script reloads the page repeatedly and
also covers overlapping, out-of-order resolves and failing endpoints.
"""
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from app.models import (
    AssignedForm, AssignmentEntityStatus, FormData, FormItem, FormSection, FormTemplateVersion,
)
from app.models.enums import EntityType
from tests.factories import create_test_country, create_test_template, create_test_user

SCRIPT = Path(__file__).with_name("entry_form_variable_matrix.mjs")
BACKOFFICE_DIR = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("E2E_PORT", "5056"))


def _chrome_path():
    explicit = os.environ.get("CHROME_PATH")
    if explicit:
        return explicit
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _playwright_available():
    if not shutil.which("node"):
        return False
    probe = subprocess.run(
        ["node", "-e", "require.resolve('playwright-core')"],
        cwd=BACKOFFICE_DIR, capture_output=True,
    )
    return probe.returncode == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("E2E_BROWSER") != "1", reason="set E2E_BROWSER=1 to run browser tests"),
]


def _build_assignment(db_session):
    user = create_test_user(db_session, role="system_manager")
    country = create_test_country(db_session)
    rows = [create_test_country(db_session) for _ in range(3)]

    source_template = create_test_template(db_session)
    source_version = db_session.get(FormTemplateVersion, source_template.published_version_id)
    source_section = FormSection(
        template_id=source_template.id, version_id=source_version.id, name="Source", order=1,
    )
    db_session.add(source_section)
    db_session.flush()
    source_item = FormItem(
        section_id=source_section.id, version_id=source_version.id, template_id=source_template.id,
        item_type='matrix', label='Source', order=1,
        config={'matrix_config': {'row_mode': 'list_library', 'columns': [{'name': 'Planned', 'type': 'number'}]}},
    )
    db_session.add(source_item)
    source_form = AssignedForm(template_id=source_template.id, period_name="2023")
    db_session.add(source_form)
    db_session.flush()
    source_aes = AssignmentEntityStatus(
        assigned_form_id=source_form.id, entity_type=EntityType.country.value,
        entity_id=country.id, status="in_progress",
    )
    db_session.add(source_aes)
    db_session.flush()
    disagg = {'_table': 'country'}
    for index, row in enumerate(rows):
        disagg[f"{row.id}_Planned"] = (index + 1) * 10
    db_session.add(FormData(
        assignment_entity_status_id=source_aes.id, form_item_id=source_item.id, disagg_data=disagg,
    ))

    template = create_test_template(db_session)
    version = db_session.get(FormTemplateVersion, template.published_version_id)
    version.variables = {
        'plan': {
            'source_template_id': source_template.id,
            'source_assignment_period': '2023',
            'source_form_item_id': source_item.id,
            'entity_scope': 'same',
            'matrix_column_name': 'Planned',
        },
    }
    section = FormSection(template_id=template.id, version_id=version.id, name="Section", order=1)
    db_session.add(section)
    db_session.flush()
    item = FormItem(
        section_id=section.id, version_id=version.id, template_id=template.id,
        item_type='matrix', label='Matrix', order=1,
        config={'matrix_config': {
            'row_mode': 'list_library',
            'auto_load_entities': True,
            'lookup_list_id': 'country',
            'columns': [
                {'name': 'Planned', 'type': 'number', 'is_variable': True, 'variable': 'plan',
                 'variable_readonly': False, 'variable_save_value': True},
                {'name': 'Actual', 'type': 'number'},
            ],
        }},
    )
    db_session.add(item)
    assigned_form = AssignedForm(template_id=template.id, period_name="2024")
    db_session.add(assigned_form)
    db_session.flush()
    aes = AssignmentEntityStatus(
        assigned_form_id=assigned_form.id, entity_type=EntityType.country.value,
        entity_id=country.id, status="in_progress",
    )
    db_session.add(aes)
    db_session.commit()
    return user, aes.id, item.id


def test_variable_matrix_never_loads_empty_or_green(app, client, db_session):
    chrome = _chrome_path()
    if not chrome:
        pytest.skip("no Chrome/Chromium binary found (set CHROME_PATH)")
    if not _playwright_available():
        pytest.skip("playwright-core is not installed (npm i --no-save playwright-core)")

    user, aes_id, item_id = _build_assignment(db_session)
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    cookie = client.get_cookie("session")

    server = make_server("127.0.0.1", PORT, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        proc = subprocess.run(
            ["node", str(SCRIPT), f"http://127.0.0.1:{PORT}", cookie.value, str(aes_id), str(item_id)],
            cwd=BACKOFFICE_DIR, capture_output=True, text=True, timeout=600,
            env={**os.environ, "CHROME_PATH": chrome},
        )
    finally:
        server.shutdown()

    print(proc.stdout)
    print(proc.stderr)
    assert proc.returncode == 0, proc.stdout + proc.stderr
