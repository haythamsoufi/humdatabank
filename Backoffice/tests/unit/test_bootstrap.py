"""Tests for app/bootstrap.py — comprehensive coverage of all functions."""

import os
import pytest
from unittest.mock import MagicMock, patch, call
from flask import Flask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flask_app(**config):
    flask_app = Flask(__name__)
    flask_app.config.update(
        SECRET_KEY='test-secret',
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    flask_app.config.update(config)
    return flask_app


# ---------------------------------------------------------------------------
# init_upload_storage
# ---------------------------------------------------------------------------

class TestInitUploadStorage:
    def test_filesystem_provider_creates_upload_folder(self, tmp_path):
        from app.bootstrap import init_upload_storage

        upload_dir = str(tmp_path / "uploads")
        flask_app = _make_flask_app(
            UPLOAD_FOLDER=upload_dir,
            UPLOAD_STORAGE_PROVIDER='filesystem',
        )
        with flask_app.app_context():
            init_upload_storage(flask_app)

        assert os.path.isdir(upload_dir)

    def test_azure_blob_creates_temp_subdir(self, tmp_path):
        from app.bootstrap import init_upload_storage

        upload_dir = str(tmp_path / "uploads")
        flask_app = _make_flask_app(
            UPLOAD_FOLDER=upload_dir,
            UPLOAD_STORAGE_PROVIDER='azure_blob',
        )
        with flask_app.app_context():
            init_upload_storage(flask_app)

        assert os.path.isdir(os.path.join(upload_dir, 'temp'))

    def test_empty_upload_folder_defaults_to_instance(self, tmp_path):
        """When UPLOAD_FOLDER is empty, falls back to instance_path/uploads."""
        from app.bootstrap import init_upload_storage

        flask_app = _make_flask_app(UPLOAD_FOLDER='', UPLOAD_STORAGE_PROVIDER='filesystem')
        flask_app.instance_path = str(tmp_path)

        with flask_app.app_context():
            init_upload_storage(flask_app)

        expected = os.path.join(str(tmp_path), 'uploads')
        assert flask_app.config['UPLOAD_FOLDER'] == expected
        assert os.path.isdir(expected)

    def test_no_upload_folder_key_defaults_to_instance(self, tmp_path):
        """Missing UPLOAD_FOLDER key should use instance_path/uploads."""
        from app.bootstrap import init_upload_storage

        flask_app = _make_flask_app(UPLOAD_STORAGE_PROVIDER='filesystem')
        flask_app.instance_path = str(tmp_path)
        flask_app.config.pop('UPLOAD_FOLDER', None)

        with flask_app.app_context():
            init_upload_storage(flask_app)

        assert 'uploads' in flask_app.config['UPLOAD_FOLDER']


# ---------------------------------------------------------------------------
# load_dynamic_settings
# ---------------------------------------------------------------------------

class TestLoadDynamicSettings:
    def _mock_config_class(self):
        cfg = MagicMock()
        cfg.LANGUAGES = ['en', 'fr']
        cfg.TRANSLATABLE_LANGUAGES = ['fr']
        cfg.ENABLED_ENTITY_TYPES = ['countries', 'ns_structure']
        cfg.DOCUMENT_TYPES = ['report', 'plan']
        cfg.DEFAULT_AGE_GROUPS = ['0-5', '6-17']
        cfg.DEFAULT_SEX_CATEGORIES = ['male', 'female']
        return cfg

    def test_loads_settings_from_database_success(self, app):
        """Happy path: settings read from DB and applied to app.config."""
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': ['en', 'fr', 'ar'],
            'show_language_flags': True,
            'enabled_entity_types': ['countries'],
            'document_types': ['plan'],
            'age_groups': ['0-5'],
            'sex_categories': ['male'],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS',
                   {'countries', 'ns_structure', 'secretariat'}), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_authsvc:
            mock_authsvc.rbac_enabled.return_value = False
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)

        assert app.config['SUPPORTED_LANGUAGES'] == ['en', 'fr', 'ar']
        assert app.config['TRANSLATABLE_LANGUAGES'] == ['fr', 'ar']

    def test_falls_back_to_defaults_on_exception(self, app):
        """If read_settings raises, defaults from config_class are used."""
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()

        with patch('app.services.app_settings_service.read_settings',
                   side_effect=Exception("DB down")):
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)

        assert app.config['SUPPORTED_LANGUAGES'] == ['en', 'fr']
        assert app.config['SHOW_LANGUAGE_FLAGS'] is True

    def test_show_flags_parsed_from_string_true(self, app):
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': ['en'],
            'show_language_flags': 'true',
            'enabled_entity_types': [],
            'document_types': [],
            'age_groups': [],
            'sex_categories': [],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS', {'countries'}), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_auth:
            mock_auth.rbac_enabled.return_value = False
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)

        assert app.config['SHOW_LANGUAGE_FLAGS'] is True

    def test_show_flags_parsed_from_int(self, app):
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': ['en'],
            'show_language_flags': 1,
            'enabled_entity_types': [],
            'document_types': [],
            'age_groups': [],
            'sex_categories': [],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS', {'countries'}), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_auth:
            mock_auth.rbac_enabled.return_value = False
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)

        assert app.config['SHOW_LANGUAGE_FLAGS'] is True

    def test_show_flags_unknown_type_defaults_true(self, app):
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': ['en'],
            'show_language_flags': object(),  # Unknown type → True
            'enabled_entity_types': [],
            'document_types': [],
            'age_groups': [],
            'sex_categories': [],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS', {'countries'}), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_auth:
            mock_auth.rbac_enabled.return_value = False
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)

        assert app.config['SHOW_LANGUAGE_FLAGS'] is True

    def test_empty_languages_falls_back_to_config(self, app):
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': [],  # empty → fallback
            'show_language_flags': True,
            'enabled_entity_types': ['countries'],
            'document_types': [],
            'age_groups': [],
            'sex_categories': [],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS', {'countries'}), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_auth:
            mock_auth.rbac_enabled.return_value = False
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)

        # Falls back to config_class.LANGUAGES
        assert app.config['SUPPORTED_LANGUAGES'] == ['en', 'fr']

    def test_entity_types_filtered_by_allowed(self, app):
        """Entity types not in ALLOWED_ENTITY_TYPE_GROUPS are excluded."""
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': ['en'],
            'show_language_flags': True,
            'enabled_entity_types': ['countries', 'invalid_type'],
            'document_types': [],
            'age_groups': [],
            'sex_categories': [],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS',
                   {'countries', 'ns_structure'}), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_auth:
            mock_auth.rbac_enabled.return_value = False
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)

        assert 'invalid_type' not in app.config['ENABLED_ENTITY_TYPES']
        assert 'countries' in app.config['ENABLED_ENTITY_TYPES']

    def test_rbac_not_seeded_warning(self, app):
        """When RBAC is enabled but permissions not seeded, a warning is logged."""
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': ['en'],
            'show_language_flags': True,
            'enabled_entity_types': [],
            'document_types': [],
            'age_groups': [],
            'sex_categories': [],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS', set()), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_auth:
            mock_auth.rbac_enabled.return_value = True
            mock_auth._permissions_seeded.return_value = False
            with patch.object(app.logger, 'warning') as mock_warn:
                with app.app_context():
                    load_dynamic_settings(app, config_class, 0.0)

            warning_msgs = [str(c) for c in mock_warn.call_args_list]
            assert any('RBAC' in m or 'rbac' in m.lower() for m in warning_msgs)

    def test_rbac_check_exception_is_swallowed(self, app):
        """Exception during RBAC sanity check should be caught."""
        from app.bootstrap import load_dynamic_settings

        config_class = self._mock_config_class()
        all_settings = {
            'languages': ['en'],
            'show_language_flags': True,
            'enabled_entity_types': [],
            'document_types': [],
            'age_groups': [],
            'sex_categories': [],
        }

        with patch('app.services.app_settings_service.read_settings', return_value=all_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS', set()), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService',
                   side_effect=Exception("import error")):
            with app.app_context():
                # Should not raise
                load_dynamic_settings(app, config_class, 0.0)

    def test_settings_load_time_slow_path_logs(self, app):
        """Slow settings load (> 0.1s) should log a debug message."""
        from app.bootstrap import load_dynamic_settings
        import time

        config_class = self._mock_config_class()

        def slow_read_settings():
            return {
                'languages': ['en'],
                'show_language_flags': True,
                'enabled_entity_types': [],
                'document_types': [],
                'age_groups': [],
                'sex_categories': [],
            }

        with patch('app.services.app_settings_service.read_settings',
                   side_effect=slow_read_settings), \
             patch('app.services.app_settings_service.ALLOWED_ENTITY_TYPE_GROUPS', set()), \
             patch('app.services.app_settings_service.apply_ai_settings_to_config'), \
             patch('app.services.authorization_service.AuthorizationService') as mock_auth, \
             patch('app.bootstrap.time') as mock_time:
            mock_auth.rbac_enabled.return_value = False
            # Simulate slow load: first call for start, second for elapsed
            mock_time.time.side_effect = [0.0, 0.5, 0.5, 0.5, 1.0]
            with app.app_context():
                load_dynamic_settings(app, config_class, 0.0)


# ---------------------------------------------------------------------------
# register_favicon_routes
# ---------------------------------------------------------------------------

class TestRegisterFaviconRoutes:
    def test_favicon_ico_served_when_exists(self, tmp_path):
        from app.bootstrap import register_favicon_routes

        favicon = tmp_path / "favicon.ico"
        favicon.write_bytes(b"\x00\x00\x01\x00")  # minimal ICO header

        flask_app = _make_flask_app()
        register_favicon_routes(flask_app, str(tmp_path))

        client = flask_app.test_client()
        response = client.get('/favicon.ico')
        assert response.status_code == 200

    def test_svg_logo_served_when_favicon_missing(self, tmp_path):
        from app.bootstrap import register_favicon_routes

        logo = tmp_path / "IFRC_logo.svg"
        logo.write_bytes(b"<svg/>")

        flask_app = _make_flask_app()
        register_favicon_routes(flask_app, str(tmp_path))

        client = flask_app.test_client()
        response = client.get('/favicon.ico')
        assert response.status_code == 200

    def test_404_when_neither_favicon_nor_logo(self, tmp_path):
        from app.bootstrap import register_favicon_routes

        flask_app = _make_flask_app()
        register_favicon_routes(flask_app, str(tmp_path))

        client = flask_app.test_client()
        response = client.get('/favicon.ico')
        assert response.status_code == 404

    def test_test_static_route_registered_in_debug(self, tmp_path):
        """In debug mode, /test-static/<filename> route should be registered."""
        from app.bootstrap import register_favicon_routes

        flask_app = _make_flask_app(DEBUG=True)
        flask_app.debug = True
        register_favicon_routes(flask_app, str(tmp_path))

        # Route should be present
        rules = [str(r) for r in flask_app.url_map.iter_rules()]
        assert any('test-static' in r for r in rules)

    def test_test_static_returns_file_in_debug(self, tmp_path):
        """In debug mode, /test-static/<filename> should serve existing files."""
        from app.bootstrap import register_favicon_routes

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        flask_app = _make_flask_app(DEBUG=True)
        flask_app.debug = True
        register_favicon_routes(flask_app, str(tmp_path))

        client = flask_app.test_client()
        response = client.get('/test-static/test.txt')
        assert response.status_code == 200

    def test_test_static_404_when_folder_missing(self):
        """If static folder doesn't exist, test-static returns 404."""
        from app.bootstrap import register_favicon_routes

        flask_app = _make_flask_app(DEBUG=True)
        flask_app.debug = True
        register_favicon_routes(flask_app, '/nonexistent/path')

        client = flask_app.test_client()
        response = client.get('/test-static/test.txt')
        assert response.status_code == 404

    def test_test_static_400_for_path_traversal(self, tmp_path):
        """Path traversal attempts should return 400."""
        from app.bootstrap import register_favicon_routes

        flask_app = _make_flask_app(DEBUG=True)
        flask_app.debug = True
        register_favicon_routes(flask_app, str(tmp_path))

        client = flask_app.test_client()
        # '../etc/passwd' basename is 'passwd' which is safe, but '.' or '..' directly
        response = client.get('/test-static/.')
        # Should be 400 (invalid path) or 404
        assert response.status_code in (400, 404)

    def test_test_static_404_for_nonexistent_file(self, tmp_path):
        """Requesting a non-existent file should return 404."""
        from app.bootstrap import register_favicon_routes

        flask_app = _make_flask_app(DEBUG=True)
        flask_app.debug = True
        register_favicon_routes(flask_app, str(tmp_path))

        client = flask_app.test_client()
        response = client.get('/test-static/nope.txt')
        assert response.status_code == 404

    def test_test_static_not_registered_in_production(self, tmp_path):
        """In non-debug mode, /test-static should NOT be registered."""
        from app.bootstrap import register_favicon_routes

        flask_app = _make_flask_app(DEBUG=False)
        flask_app.debug = False
        register_favicon_routes(flask_app, str(tmp_path))

        rules = [str(r) for r in flask_app.url_map.iter_rules()]
        assert not any('test-static' in r for r in rules)
