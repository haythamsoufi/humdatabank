"""Sidebar labels must go through gettext so catalogs can localise them."""

from pathlib import Path

import polib

_BACKOFFICE = Path(__file__).resolve().parents[2]
_SIDEBAR = _BACKOFFICE / "app" / "templates" / "components" / "_sidebar_nav_categories.html"
_CATALOG_LANGS = ("ar", "es", "fr", "hi", "ru", "zh")
_REQUIRED_MSGIDS = ("AI System", "AI Dashboard")


def test_sidebar_ai_labels_use_gettext():
    source = _SIDEBAR.read_text(encoding="utf-8")
    assert "{{ _('AI System') }}" in source
    assert "{{ _('AI Dashboard') }}" in source
    assert "{{ _('AI Dashboard')|forceescape }}" in source


def test_sidebar_ai_labels_have_catalog_translations():
    for lang in _CATALOG_LANGS:
        po_path = _BACKOFFICE / "translations" / lang / "LC_MESSAGES" / "messages.po"
        catalog = polib.pofile(str(po_path))
        by_msgid = {entry.msgid: entry for entry in catalog}
        for msgid in _REQUIRED_MSGIDS:
            entry = by_msgid.get(msgid)
            assert entry is not None, f"{lang}: missing {msgid!r}"
            assert entry.msgstr.strip(), f"{lang}: empty translation for {msgid!r}"
            assert entry.msgstr != msgid, f"{lang}: {msgid!r} is still English"
