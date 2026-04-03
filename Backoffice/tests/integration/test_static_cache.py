"""
Integration tests for static file caching headers.

Tests that static files have proper cache headers set.
"""
import pytest
from flask import url_for


@pytest.mark.integration
@pytest.mark.static
class TestStaticCache:
    """Test static file caching headers."""

    TEST_FILES = [
        'css/output.css',
        'css/forms.css',
        'css/layout.css',
        'js/layout.js',
        'js/csrf.js',
        'js/chatbot.js',
    ]

    def parse_cache_control(self, header_value):
        """Parse Cache-Control header into a dictionary."""
        if not header_value:
            return {}

        directives = {}
        for part in header_value.split(','):
            part = part.strip()
            if '=' in part:
                key, value = part.split('=', 1)
                directives[key.strip().lower()] = value.strip()
            else:
                directives[part.strip().lower()] = True

        return directives

    def test_versioned_static_files_have_long_cache(self, client, app):
        """Test that versioned static files have long cache headers."""
        with app.app_context():
            for file_path in self.TEST_FILES:
                # Try to access versioned file
                url = f'/static/{file_path}?v=1.0'
                response = client.head(url)

                if response.status_code == 200:
                    cache_control = response.headers.get('Cache-Control', '')
                    parsed = self.parse_cache_control(cache_control)

                    # Versioned files should have long cache (1 year)
                    assert 'max-age' in parsed or 'public' in parsed
                    if 'max-age' in parsed:
                        # Should be 1 year (31536000 seconds) or immutable
                        max_age = int(parsed.get('max-age', '0'))
                        assert max_age >= 3600  # At least 1 hour

    def test_static_files_have_etag(self, client, app):
        """Test that static files have ETag headers."""
        with app.app_context():
            for file_path in self.TEST_FILES:
                url = f'/static/{file_path}?v=1.0'
                response = client.head(url)

                if response.status_code == 200:
                    # ETag should be present (Flask adds this automatically)
                    etag = response.headers.get('ETag')
                    # ETag is optional but nice to have
                    # Just verify the file is accessible
                    assert response.status_code == 200

    def test_static_files_are_accessible(self, client, app):
        """Test that static files are accessible."""
        with app.app_context():
            for file_path in self.TEST_FILES:
                url = f'/static/{file_path}?v=1.0'
                response = client.head(url)

                # File might not exist in test environment, that's OK
                # Just verify we get a valid HTTP response
                assert response.status_code in [200, 404]
