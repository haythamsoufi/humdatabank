"""
Comprehensive tests for app/plugins/jinja_plugin_loader.py
Targets 100% code coverage of PluginTemplateLoader.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from jinja2 import TemplateNotFound, Environment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loader(tmp_path, plugin_id="my_plugin", content="Hello {{ name }}"):
    """Build a PluginTemplateLoader with a real template file on disk."""
    from app.plugins.jinja_plugin_loader import PluginTemplateLoader

    templates_dir = tmp_path / plugin_id / "templates"
    templates_dir.mkdir(parents=True)
    template_file = templates_dir / "field.html"
    template_file.write_text(content, encoding="utf-8")

    def get_template_dir(pid):
        if pid == plugin_id:
            return templates_dir
        return None

    loader = PluginTemplateLoader(get_template_dir)
    return loader, templates_dir, template_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginTemplateLoaderGetSource:
    def test_returns_source_for_valid_template(self, tmp_path):
        """get_source returns (source, filename, uptodate) for a valid template."""
        loader, templates_dir, tf = _loader(tmp_path)
        env = MagicMock()

        source, filename, uptodate = loader.get_source(env, "plugins/my_plugin/field.html")

        assert source == "Hello {{ name }}"
        assert filename == str(tf.resolve())
        assert callable(uptodate)

    def test_raises_for_non_plugin_prefix(self, tmp_path):
        """Templates not starting with 'plugins/' raise TemplateNotFound."""
        loader, _, _ = _loader(tmp_path)
        env = MagicMock()
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "base/field.html")

    def test_raises_for_too_short_path(self, tmp_path):
        """'plugins/only_plugin_id' (no rel part) raises TemplateNotFound."""
        loader, _, _ = _loader(tmp_path)
        env = MagicMock()
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "plugins/my_plugin")

    def test_raises_when_plugin_id_empty(self, tmp_path):
        """'plugins//field.html' (empty plugin_id) raises TemplateNotFound."""
        loader, _, _ = _loader(tmp_path)
        env = MagicMock()
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "plugins//field.html")

    def test_raises_when_rel_empty(self, tmp_path):
        """'plugins/my_plugin/' (empty rel) raises TemplateNotFound."""
        loader, _, _ = _loader(tmp_path)
        env = MagicMock()
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "plugins/my_plugin/")

    def test_raises_when_get_template_dir_returns_none(self, tmp_path):
        """When get_template_dir returns None, TemplateNotFound is raised."""
        from app.plugins.jinja_plugin_loader import PluginTemplateLoader
        loader = PluginTemplateLoader(lambda pid: None)
        env = MagicMock()
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "plugins/unknown_plugin/field.html")

    def test_raises_when_file_not_found(self, tmp_path):
        """Missing template file raises TemplateNotFound."""
        loader, templates_dir, _ = _loader(tmp_path)
        env = MagicMock()
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "plugins/my_plugin/nonexistent.html")

    def test_raises_for_directory_traversal(self, tmp_path):
        """Path traversal attempts raise TemplateNotFound."""
        loader, templates_dir, _ = _loader(tmp_path)
        env = MagicMock()
        # Attempt to escape via ../
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "plugins/my_plugin/../../etc/passwd")

    def test_raises_when_path_resolves_to_directory(self, tmp_path):
        """If the resolved path is a directory (not a file), raise TemplateNotFound."""
        from app.plugins.jinja_plugin_loader import PluginTemplateLoader

        subdir = tmp_path / "my_plugin" / "templates" / "subdir"
        subdir.mkdir(parents=True)

        loader = PluginTemplateLoader(lambda pid: tmp_path / "my_plugin" / "templates")
        env = MagicMock()
        with pytest.raises(TemplateNotFound):
            loader.get_source(env, "plugins/my_plugin/subdir")


@pytest.mark.unit
class TestPluginTemplateLoaderUptodate:
    def test_uptodate_returns_true_when_file_unchanged(self, tmp_path):
        loader, _, tf = _loader(tmp_path)
        env = MagicMock()
        _, _, uptodate = loader.get_source(env, "plugins/my_plugin/field.html")
        assert uptodate() is True

    def test_uptodate_returns_false_when_file_modified(self, tmp_path):
        loader, _, tf = _loader(tmp_path)
        env = MagicMock()
        _, _, uptodate = loader.get_source(env, "plugins/my_plugin/field.html")

        import time
        time.sleep(0.01)
        tf.write_text("modified content", encoding="utf-8")
        # Touch modifies mtime
        tf.touch()
        assert uptodate() is False

    def test_uptodate_returns_false_when_file_deleted(self, tmp_path):
        loader, _, tf = _loader(tmp_path)
        env = MagicMock()
        _, _, uptodate = loader.get_source(env, "plugins/my_plugin/field.html")

        tf.unlink()
        assert uptodate() is False

    def test_uptodate_handles_oserror(self, tmp_path):
        """If stat raises OSError, uptodate returns False."""
        loader, _, tf = _loader(tmp_path)
        env = MagicMock()
        _, _, uptodate = loader.get_source(env, "plugins/my_plugin/field.html")

        with patch.object(Path, "stat", side_effect=OSError("perm")):
            assert uptodate() is False


@pytest.mark.unit
class TestPluginTemplateLoaderIntegration:
    def test_loader_works_with_jinja2_environment(self, tmp_path):
        """End-to-end: loader integrates with a real Jinja2 Environment."""
        loader, _, _ = _loader(tmp_path, content="Value: {{ val }}")
        env = Environment(loader=loader)
        template = env.get_template("plugins/my_plugin/field.html")
        rendered = template.render(val="42")
        assert "42" in rendered

    def test_multiple_plugins_isolated(self, tmp_path):
        """Different plugins have isolated template namespaces."""
        from app.plugins.jinja_plugin_loader import PluginTemplateLoader

        dirs = {}
        for pid in ("plugin_a", "plugin_b"):
            d = tmp_path / pid / "templates"
            d.mkdir(parents=True)
            (d / "index.html").write_text(f"Plugin {pid}", encoding="utf-8")
            dirs[pid] = d

        loader = PluginTemplateLoader(lambda pid: dirs.get(pid))
        env = MagicMock()

        src_a, _, _ = loader.get_source(env, "plugins/plugin_a/index.html")
        src_b, _, _ = loader.get_source(env, "plugins/plugin_b/index.html")

        assert "plugin_a" in src_a
        assert "plugin_b" in src_b
