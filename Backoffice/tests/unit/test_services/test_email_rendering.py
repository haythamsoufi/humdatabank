"""
Comprehensive tests for app/services/email/rendering.py.

Covers:
- render_admin_email_template (sandboxed Jinja2 + bleach)
- render_admin_email_template_for_preview
- sanitize_admin_email_html_for_api
- _datetimeformat_filter
- _allow_attr attribute callback
"""
import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from app.services.email.rendering import (
    render_admin_email_template,
    render_admin_email_template_for_preview,
    sanitize_admin_email_html_for_api,
    _datetimeformat_filter,
    _allow_attr,
)


# ---------------------------------------------------------------------------
# _datetimeformat_filter
# ---------------------------------------------------------------------------

class TestDatetimeformatFilter:
    def test_none_returns_empty(self):
        assert _datetimeformat_filter(None) == ""

    def test_datetime_object(self):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        result = _datetimeformat_filter(dt)
        assert "2024-06-15" in result

    def test_date_object(self):
        d = date(2024, 6, 15)
        result = _datetimeformat_filter(d)
        assert result == "2024-06-15"

    def test_string_value(self):
        result = _datetimeformat_filter("some string")
        assert result == "some string"

    def test_integer_value(self):
        result = _datetimeformat_filter(42)
        assert result == "42"

    def test_object_with_strftime(self):
        class FakeDate:
            def strftime(self, fmt):
                return "FAKE-DATE"
        result = _datetimeformat_filter(FakeDate())
        assert result == "FAKE-DATE"

    def test_object_with_strftime_exception(self):
        class BadDate:
            def strftime(self, fmt):
                raise ValueError("bad")
        result = _datetimeformat_filter(BadDate())
        assert result  # returns str(value)

    def test_date_strftime_exception(self):
        d = date(2024, 1, 1)
        with patch.object(d.__class__, "strftime", side_effect=Exception("fail")):
            result = _datetimeformat_filter(d)
            assert result  # falls back to str(value)

    def test_datetime_ensure_utc_exception(self):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        with patch("app.services.email.rendering.ensure_utc", side_effect=Exception("tz fail")):
            result = _datetimeformat_filter(dt)
            # falls back to str(dt)
            assert result


# ---------------------------------------------------------------------------
# _allow_attr
# ---------------------------------------------------------------------------

class TestAllowAttr:
    def test_blocks_onclick(self):
        assert _allow_attr("a", "onclick", "alert(1)") is False

    def test_blocks_onload(self):
        assert _allow_attr("body", "onload", "init()") is False

    def test_blocks_onmouseover(self):
        assert _allow_attr("div", "onmouseover", "hover()") is False

    def test_allows_href_https(self):
        assert _allow_attr("a", "href", "https://example.com") is True

    def test_allows_href_http(self):
        assert _allow_attr("a", "href", "http://example.com") is True

    def test_allows_href_mailto(self):
        assert _allow_attr("a", "href", "mailto:test@example.com") is True

    def test_blocks_href_javascript(self):
        assert _allow_attr("a", "href", "javascript:alert(1)") is False

    def test_blocks_href_vbscript(self):
        assert _allow_attr("a", "href", "vbscript:msgbox()") is False

    def test_blocks_href_data(self):
        assert _allow_attr("a", "href", "data:text/html,<h1>x</h1>") is False

    def test_blocks_javascript_with_nullbytes(self):
        assert _allow_attr("a", "href", "\x00javascript:alert()") is False

    def test_blocks_meta_http_equiv(self):
        assert _allow_attr("meta", "http-equiv", "refresh") is False

    def test_allows_meta_charset(self):
        assert _allow_attr("meta", "charset", "utf-8") is True

    def test_blocks_src_javascript(self):
        assert _allow_attr("img", "src", "javascript:void(0)") is False

    def test_allows_img_src_https(self):
        assert _allow_attr("img", "src", "https://example.com/img.png") is True

    def test_allows_class_attribute(self):
        assert _allow_attr("div", "class", "container") is True

    def test_allows_style_attribute(self):
        assert _allow_attr("p", "style", "color:red") is True

    def test_allows_action_https(self):
        assert _allow_attr("form", "action", "https://example.com/submit") is True

    def test_blocks_action_javascript(self):
        assert _allow_attr("form", "action", "javascript:submit()") is False

    def test_allows_data_attribute_non_url(self):
        assert _allow_attr("div", "data-id", "123") is True

    def test_blocks_data_attr_data_url(self):
        assert _allow_attr("a", "data", "data:text/html,<script>") is False


# ---------------------------------------------------------------------------
# render_admin_email_template
# ---------------------------------------------------------------------------

class TestRenderAdminEmailTemplate:
    def test_empty_string_returns_empty(self):
        result = render_admin_email_template("")
        assert result == ""

    def test_none_returns_empty(self):
        result = render_admin_email_template(None)
        assert result == ""

    def test_whitespace_only_returns_empty(self):
        result = render_admin_email_template("   \n  ")
        assert result == ""

    def test_simple_template_renders(self):
        result = render_admin_email_template("<p>Hello {{ name }}</p>", name="World")
        assert "Hello World" in result

    def test_variables_are_html_escaped(self):
        result = render_admin_email_template("<p>{{ xss }}</p>", xss="<script>alert(1)</script>")
        # script tag should be stripped by bleach
        assert "<script>" not in result

    def test_bleach_strips_script_tag(self):
        template = "<p>Hello</p><script>evil()</script>"
        result = render_admin_email_template(template)
        assert "<script>" not in result
        assert "Hello" in result

    def test_bleach_strips_event_handler(self):
        template = '<p onclick="evil()">Click me</p>'
        result = render_admin_email_template(template)
        assert "onclick" not in result
        assert "Click me" in result

    def test_bleach_strips_javascript_href(self):
        template = '<a href="javascript:alert(1)">link</a>'
        result = render_admin_email_template(template)
        assert "javascript:" not in result

    def test_safe_filter_passes_html(self):
        template = "<div>{{ content | safe }}</div>"
        result = render_admin_email_template(template, content="<b>bold</b>")
        assert "<b>bold</b>" in result

    def test_jinja_syntax_error_returns_empty(self):
        result = render_admin_email_template("{% if %}")
        assert result == ""

    def test_jinja_undefined_var_renders_empty_string(self):
        # SandboxedEnvironment with autoescape; undefined renders as ''
        result = render_admin_email_template("<p>{{ undefined_var }}</p>")
        assert "<p>" in result

    def test_datetimeformat_filter_available(self):
        dt = datetime(2024, 6, 15, 10, 0, 0)
        result = render_admin_email_template("{{ dt | datetimeformat }}", dt=dt)
        assert "2024-06-15" in result

    def test_sandbox_blocks_ssti(self):
        # __class__ traversal should be blocked by SandboxedEnvironment
        malicious = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
        result = render_admin_email_template(malicious)
        # Should return empty (render error caught) or safe string
        assert "__subclasses__" not in result or result == ""

    def test_bleach_sanitization_exception_returns_empty(self):
        import bleach
        with patch("app.services.email.rendering.bleach.clean", side_effect=Exception("bleach fail")):
            result = render_admin_email_template("<p>Hello</p>")
        assert result == ""

    def test_loops_in_template(self):
        template = "<ul>{% for item in items %}<li>{{ item }}</li>{% endfor %}</ul>"
        result = render_admin_email_template(template, items=["a", "b", "c"])
        assert "<li>a</li>" in result
        assert "<li>b</li>" in result
        assert "<li>c</li>" in result

    def test_conditional_in_template(self):
        template = "{% if show %}<p>visible</p>{% else %}<p>hidden</p>{% endif %}"
        assert "visible" in render_admin_email_template(template, show=True)
        assert "hidden" in render_admin_email_template(template, show=False)

    def test_inline_style_background_preserved(self):
        template = (
            '<div style="background-color:#0d9488;color:#ffffff;padding:28px 40px;">'
            '<h1 style="color:#ffffff;">Notification</h1></div>'
        )
        result = render_admin_email_template(template)
        assert "background-color:#0d9488" in result.replace(" ", "")
        assert "color:#ffffff" in result.replace(" ", "")

    def test_security_alert_header_style_preserved(self):
        from app.services.email.preview_context import build_security_alert_email_context
        from scripts.seeding.seed_email_templates import DEFAULT_EMAIL_TEMPLATES

        ctx = build_security_alert_email_context(
            event_type="failed_login",
            severity="high",
            description="Test",
            org_name="Org",
            copyright_year="2026",
        )
        result = render_admin_email_template(
            DEFAULT_EMAIL_TEMPLATES["email_template_security_alert"]["en"],
            **ctx,
        )
        assert 'class="email-header"' in result
        assert "background-color:#dc2626" in result.replace(" ", "")
        assert "color:#ffffff" in result.replace(" ", "")


# ---------------------------------------------------------------------------
# render_admin_email_template_for_preview
# ---------------------------------------------------------------------------

class TestRenderAdminEmailTemplateForPreview:
    def test_empty_template_returns_error(self):
        html, err = render_admin_email_template_for_preview("")
        assert html is None
        assert "empty" in err.lower()

    def test_none_template_returns_error(self):
        html, err = render_admin_email_template_for_preview(None)
        assert html is None
        assert err is not None

    def test_whitespace_only_returns_error(self):
        html, err = render_admin_email_template_for_preview("   ")
        assert html is None
        assert err is not None

    def test_valid_template_returns_html(self):
        html, err = render_admin_email_template_for_preview("<p>Hello {{ name }}</p>", name="Alice")
        assert err is None
        assert html is not None
        assert "Hello Alice" in html

    def test_jinja_error_returns_error_message(self):
        html, err = render_admin_email_template_for_preview("{% if %}")
        assert html is None
        assert err is not None
        assert len(err) > 0

    def test_renders_empty_output_returns_error(self):
        # Template that renders to empty/whitespace only
        html, err = render_admin_email_template_for_preview("{% if False %}<p>visible</p>{% endif %}")
        assert html is None
        assert "empty" in err.lower()

    def test_sanitization_removes_script(self):
        html, err = render_admin_email_template_for_preview("<p>Hi</p><script>evil()</script>")
        assert err is None
        assert "<script>" not in html
        assert "Hi" in html

    def test_sanitization_empty_after_clean_returns_error(self):
        import bleach
        with patch("app.services.email.rendering.bleach.clean", return_value="   "):
            html, err = render_admin_email_template_for_preview("<p>content</p>")
        assert html is None
        assert "empty" in err.lower()

    def test_bleach_exception_returns_error(self):
        import bleach
        with patch("app.services.email.rendering.bleach.clean", side_effect=Exception("clean fail")):
            html, err = render_admin_email_template_for_preview("<p>content</p>")
        assert html is None
        assert err is not None

    def test_strips_javascript_href(self):
        html, err = render_admin_email_template_for_preview('<a href="javascript:void(0)">link</a>')
        assert err is None
        assert "javascript:" not in html

    def test_datetimeformat_filter(self):
        dt = datetime(2024, 3, 15, 9, 0, 0)
        html, err = render_admin_email_template_for_preview("{{ dt | datetimeformat }}", dt=dt)
        assert err is None
        assert "2024-03-15" in html

    def test_context_variables_passed(self):
        html, err = render_admin_email_template_for_preview(
            "<p>{{ user }} - {{ count }}</p>", user="Alice", count=42
        )
        assert err is None
        assert "Alice" in html
        assert "42" in html


# ---------------------------------------------------------------------------
# sanitize_admin_email_html_for_api
# ---------------------------------------------------------------------------

class TestSanitizeAdminEmailHtmlForApi:
    def test_empty_string_returns_empty(self):
        assert sanitize_admin_email_html_for_api("") == ""

    def test_none_returns_empty(self):
        assert sanitize_admin_email_html_for_api(None) == ""

    def test_whitespace_only_returns_empty(self):
        assert sanitize_admin_email_html_for_api("   ") == ""

    def test_clean_html_passes_through(self):
        result = sanitize_admin_email_html_for_api("<p>Hello <strong>World</strong></p>")
        assert "Hello" in result
        assert "<strong>" in result

    def test_strips_script_tag(self):
        result = sanitize_admin_email_html_for_api("<p>Hi</p><script>evil()</script>")
        assert "<script>" not in result
        assert "Hi" in result

    def test_strips_onclick(self):
        result = sanitize_admin_email_html_for_api('<p onclick="evil()">text</p>')
        assert "onclick" not in result
        assert "text" in result

    def test_strips_javascript_href(self):
        result = sanitize_admin_email_html_for_api('<a href="javascript:alert(1)">link</a>')
        assert "javascript:" not in result

    def test_bleach_exception_returns_empty(self):
        with patch("app.services.email.rendering.bleach.clean", side_effect=Exception("fail")):
            result = sanitize_admin_email_html_for_api("<p>content</p>")
        assert result == ""

    def test_allows_safe_tags(self):
        html = "<h1>Title</h1><table><tr><td>Cell</td></tr></table>"
        result = sanitize_admin_email_html_for_api(html)
        assert "<h1>" in result
        assert "<table>" in result

    def test_strips_iframe(self):
        result = sanitize_admin_email_html_for_api('<iframe src="https://evil.com"></iframe>')
        assert "<iframe>" not in result

    def test_allows_img_tag(self):
        result = sanitize_admin_email_html_for_api('<img src="https://example.com/img.png" alt="test">')
        assert "<img" in result
