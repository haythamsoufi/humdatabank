"""
Comprehensive tests for app/plugins/template_utils.py
Targets 100% code coverage.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from flask import Flask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(tmp_path: Path = None) -> Flask:
    app = Flask(__name__, instance_path=str(tmp_path or Path("/tmp")))
    app.config["TESTING"] = True
    if tmp_path:
        app.root_path = str(tmp_path / "app")
        (tmp_path / "app").mkdir(exist_ok=True)
    return app


# ---------------------------------------------------------------------------
# render_plugin_template
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderPluginTemplate:
    def test_renders_template_successfully(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.render_template", return_value="<rendered/>") as rt:
                from app.plugins.template_utils import render_plugin_template
                result = render_plugin_template("my_plugin", "field.html", key="val")
        rt.assert_called_once_with("plugins/my_plugin/field.html", key="val")
        assert result == "<rendered/>"

    def test_re_raises_exception_from_render_template(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.render_template", side_effect=Exception("tmpl error")):
                with patch("app.plugins.template_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    from app.plugins.template_utils import render_plugin_template
                    with pytest.raises(Exception) as exc_info:
                        render_plugin_template("my_plugin", "field.html")
        assert "tmpl error" in str(exc_info.value)

    def test_logs_error_on_exception(self, tmp_path):
        app = _make_app(tmp_path)
        mock_logger = MagicMock()
        with app.app_context():
            with patch("app.plugins.template_utils.render_template", side_effect=ValueError("bad")):
                with patch("app.plugins.template_utils.current_app") as mca:
                    mca.logger = mock_logger
                    from app.plugins.template_utils import render_plugin_template
                    with pytest.raises(ValueError):
                        render_plugin_template("my_plugin", "bad.html")
        mock_logger.error.assert_called_once()

    def test_constructs_correct_template_path(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.render_template", return_value="ok") as rt:
                from app.plugins.template_utils import render_plugin_template
                render_plugin_template("interactive_map", "entry_form.html", foo="bar")
        rt.assert_called_with("plugins/interactive_map/entry_form.html", foo="bar")


# ---------------------------------------------------------------------------
# get_plugin_template_path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPluginTemplatePath:
    def test_returns_correct_path(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                from app.plugins.template_utils import get_plugin_template_path
                result = get_plugin_template_path("my_plugin", "field.html")
        expected = tmp_path / "plugins" / "my_plugin" / "templates" / "field.html"
        assert result == expected

    def test_path_components_are_correct(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                from app.plugins.template_utils import get_plugin_template_path
                result = get_plugin_template_path("awesome_plugin", "settings.html")
        assert "awesome_plugin" in str(result)
        assert "templates" in str(result)
        assert result.name == "settings.html"


# ---------------------------------------------------------------------------
# plugin_template_exists
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginTemplateExists:
    def test_returns_true_when_template_exists(self, tmp_path):
        # Create the actual template file
        plugin_templates = tmp_path / "plugins" / "my_plugin" / "templates"
        plugin_templates.mkdir(parents=True)
        (plugin_templates / "field.html").write_text("<div/>")

        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                mca.logger = MagicMock()
                from app.plugins.template_utils import plugin_template_exists
                result = plugin_template_exists("my_plugin", "field.html")
        assert result is True

    def test_returns_false_when_template_missing(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                mca.logger = MagicMock()
                from app.plugins.template_utils import plugin_template_exists
                result = plugin_template_exists("nonexistent_plugin", "missing.html")
        assert result is False

    def test_returns_false_on_exception(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.get_plugin_template_path", side_effect=Exception("err")):
                with patch("app.plugins.template_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    from app.plugins.template_utils import plugin_template_exists
                    result = plugin_template_exists("any", "any.html")
        assert result is False

    def test_logs_debug_on_exception(self, tmp_path):
        mock_logger = MagicMock()
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.get_plugin_template_path", side_effect=OSError("perm")):
                with patch("app.plugins.template_utils.current_app") as mca:
                    mca.logger = mock_logger
                    from app.plugins.template_utils import plugin_template_exists
                    plugin_template_exists("any", "any.html")
        mock_logger.debug.assert_called_once()


# ---------------------------------------------------------------------------
# list_plugin_templates
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestListPluginTemplates:
    def test_returns_html_files_only(self, tmp_path):
        plugin_templates = tmp_path / "plugins" / "my_plugin" / "templates"
        plugin_templates.mkdir(parents=True)
        (plugin_templates / "field.html").write_text("<div/>")
        (plugin_templates / "settings.html").write_text("<div/>")
        (plugin_templates / "ignore.txt").write_text("not html")

        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                mca.logger = MagicMock()
                from app.plugins.template_utils import list_plugin_templates
                result = list_plugin_templates("my_plugin")

        assert "field.html" in result
        assert "settings.html" in result
        assert "ignore.txt" not in result

    def test_returns_empty_list_when_dir_missing(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                mca.logger = MagicMock()
                from app.plugins.template_utils import list_plugin_templates
                result = list_plugin_templates("nonexistent_plugin")
        assert result == []

    def test_returns_empty_list_on_exception(self, tmp_path):
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                mca.logger = MagicMock()
                with patch("pathlib.Path.iterdir", side_effect=OSError("perm")):
                    # Force the dir to appear to exist
                    with patch("pathlib.Path.exists", return_value=True):
                        from app.plugins.template_utils import list_plugin_templates
                        result = list_plugin_templates("my_plugin")
        assert result == []

    def test_logs_error_on_exception(self, tmp_path):
        mock_logger = MagicMock()
        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                mca.logger = mock_logger
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.iterdir", side_effect=PermissionError("denied")):
                        from app.plugins.template_utils import list_plugin_templates
                        list_plugin_templates("my_plugin")
        mock_logger.error.assert_called_once()

    def test_skips_subdirectories(self, tmp_path):
        plugin_templates = tmp_path / "plugins" / "my_plugin" / "templates"
        plugin_templates.mkdir(parents=True)
        (plugin_templates / "real.html").write_text("<div/>")
        subdir = plugin_templates / "subdir"
        subdir.mkdir()
        (subdir / "nested.html").write_text("<div/>")  # Should not be listed

        app = _make_app(tmp_path)
        with app.app_context():
            with patch("app.plugins.template_utils.current_app") as mca:
                mca.root_path = str(tmp_path / "app")
                mca.logger = MagicMock()
                from app.plugins.template_utils import list_plugin_templates
                result = list_plugin_templates("my_plugin")

        assert "real.html" in result
        assert "nested.html" not in result
        assert "subdir" not in result
