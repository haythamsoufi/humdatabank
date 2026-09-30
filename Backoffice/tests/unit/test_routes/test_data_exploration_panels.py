import pytest
from flask import Flask
from jinja2 import DictLoader
from markupsafe import Markup

from app.routes.admin.data_exploration import _render_panel_template


@pytest.fixture()
def panel_app():
    app = Flask(__name__)
    app.jinja_loader = DictLoader(
        {
            "panel.html": "<div>{{ value }}</div>",
            "panel.txt": "{{ value }}",
        }
    )
    return app


def test_panel_output_is_markup_and_variables_are_autoescaped(panel_app):
    with panel_app.test_request_context():
        out = _render_panel_template("panel.html", {"value": "<script>alert(1)</script>"})
    assert isinstance(out, Markup)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert out.startswith("<div>")


@pytest.mark.parametrize(
    "name",
    ["panel.txt", "../panel.html", "a/../../b.html", "/etc/panel.html", "\\panel.html", "", None, "panel.js"],
)
def test_invalid_panel_template_names_are_rejected(panel_app, name):
    with panel_app.test_request_context():
        with pytest.raises(ValueError):
            _render_panel_template(name, {})
