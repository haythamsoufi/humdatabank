"""Unit tests for the inline-JS / CSP diff guard (no database)."""

from __future__ import annotations

from scripts.ci.check_no_inline_js_in_diff import scan_diff, should_scan_file


def test_skips_jsdom_test_fixtures():
    assert should_scan_file("Backoffice/tests/js/forms/form-optimization.test.js") is False
    assert should_scan_file("Backoffice/tests/unit/test_foo.py") is False


def test_still_scans_production_js_and_templates():
    assert should_scan_file("Backoffice/app/static/js/forms/modules/form-optimization.js") is True
    assert should_scan_file("Backoffice/app/templates/forms/entry.html") is True


def test_scan_diff_ignores_test_file_innerhtml():
    diff = """\
diff --git a/Backoffice/tests/js/forms/form-optimization.test.js b/Backoffice/tests/js/forms/form-optimization.test.js
+++ b/Backoffice/tests/js/forms/form-optimization.test.js
@@ -0,0 +1 @@
+    document.body.innerHTML = `
"""
    assert scan_diff(diff) == []


def test_scan_diff_ignores_sqlalchemy_ondelete():
    diff = """\
diff --git a/Backoffice/app/models/assignments.py b/Backoffice/app/models/assignments.py
+++ b/Backoffice/app/models/assignments.py
@@ -0,0 +1 @@
+    status_changed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
"""
    assert scan_diff(diff) == []


def test_scan_diff_still_flags_html_event_handler():
    diff = """\
diff --git a/Backoffice/app/templates/admin/foo.html b/Backoffice/app/templates/admin/foo.html
+++ b/Backoffice/app/templates/admin/foo.html
@@ -0,0 +1 @@
+    <button onclick="doThing()">Go</button>
"""
    findings = scan_diff(diff)
    assert findings
    assert any("onclick" in item for item in findings)


def test_scan_diff_flags_production_innerhtml():
    diff = """\
diff --git a/Backoffice/app/static/js/forms/foo.js b/Backoffice/app/static/js/forms/foo.js
+++ b/Backoffice/app/static/js/forms/foo.js
@@ -0,0 +1 @@
+    el.innerHTML = userInput;
"""
    findings = scan_diff(diff)
    assert len(findings) == 1
    assert "innerHTML assignment" in findings[0]
    assert "foo.js" in findings[0]
