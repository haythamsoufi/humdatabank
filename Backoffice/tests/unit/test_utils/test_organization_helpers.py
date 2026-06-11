"""
Unit tests for app/utils/organization_helpers.py

Covers: get_org_name, get_org_short_name, get_org_domain,
        get_org_email_domain, is_org_email, get_org_logo_path,
        get_org_copyright_year, get_org_branding, get_branding_context
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestGetOrgName:
    def test_returns_service_value(self):
        from app.utils.organization_helpers import get_org_name
        with patch("app.utils.organization_helpers.get_organization_name", return_value="IFRC") as mock_fn:
            result = get_org_name()
            mock_fn.assert_called_once_with(default="Humanitarian Databank", locale=None)
            assert result == "IFRC"

    def test_custom_default_forwarded(self):
        from app.utils.organization_helpers import get_org_name
        with patch("app.utils.organization_helpers.get_organization_name", return_value="Custom") as mock_fn:
            get_org_name(default="My Default")
            mock_fn.assert_called_once_with(default="My Default", locale=None)

    def test_locale_forwarded(self):
        from app.utils.organization_helpers import get_org_name
        with patch("app.utils.organization_helpers.get_organization_name", return_value="Org FR") as mock_fn:
            get_org_name(locale="fr")
            mock_fn.assert_called_once_with(default="Humanitarian Databank", locale="fr")


@pytest.mark.unit
class TestGetOrgShortName:
    def test_returns_service_value(self):
        from app.utils.organization_helpers import get_org_short_name
        with patch("app.utils.organization_helpers.get_organization_short_name", return_value="HDB") as mock_fn:
            result = get_org_short_name()
            mock_fn.assert_called_once_with(default="Humanitarian Databank", locale=None)
            assert result == "HDB"

    def test_locale_forwarded(self):
        from app.utils.organization_helpers import get_org_short_name
        with patch("app.utils.organization_helpers.get_organization_short_name", return_value="HDB") as mock_fn:
            get_org_short_name(locale="ar")
            mock_fn.assert_called_once_with(default="Humanitarian Databank", locale="ar")


@pytest.mark.unit
class TestGetOrgDomain:
    def test_returns_service_value(self):
        from app.utils.organization_helpers import get_org_domain
        with patch("app.utils.organization_helpers.get_organization_domain", return_value="example.org") as mock_fn:
            result = get_org_domain()
            mock_fn.assert_called_once_with(default="humdatabank.org")
            assert result == "example.org"

    def test_custom_default_forwarded(self):
        from app.utils.organization_helpers import get_org_domain
        with patch("app.utils.organization_helpers.get_organization_domain", return_value="x.org") as mock_fn:
            get_org_domain(default="fallback.org")
            mock_fn.assert_called_once_with(default="fallback.org")


@pytest.mark.unit
class TestGetOrgEmailDomain:
    def test_returns_service_value(self):
        from app.utils.organization_helpers import get_org_email_domain
        with patch("app.utils.organization_helpers.get_organization_email_domain", return_value="mail.org") as mock_fn:
            result = get_org_email_domain()
            mock_fn.assert_called_once_with(default="humdatabank.org")
            assert result == "mail.org"


@pytest.mark.unit
class TestIsOrgEmail:
    def test_org_email_returns_true(self):
        from app.utils.organization_helpers import is_org_email
        with patch("app.utils.organization_helpers.is_organization_email", return_value=True) as mock_fn:
            result = is_org_email("user@example.org")
            mock_fn.assert_called_once_with("user@example.org")
            assert result is True

    def test_external_email_returns_false(self):
        from app.utils.organization_helpers import is_org_email
        with patch("app.utils.organization_helpers.is_organization_email", return_value=False):
            assert is_org_email("user@gmail.com") is False


@pytest.mark.unit
class TestGetOrgLogoPath:
    def test_returns_service_value(self):
        from app.utils.organization_helpers import get_org_logo_path
        with patch("app.utils.organization_helpers.get_organization_logo_path", return_value="logo.png") as mock_fn:
            result = get_org_logo_path()
            mock_fn.assert_called_once_with(default="logo.svg")
            assert result == "logo.png"

    def test_custom_default_forwarded(self):
        from app.utils.organization_helpers import get_org_logo_path
        with patch("app.utils.organization_helpers.get_organization_logo_path", return_value="x.svg") as mock_fn:
            get_org_logo_path(default="fallback.svg")
            mock_fn.assert_called_once_with(default="fallback.svg")


@pytest.mark.unit
class TestGetOrgCopyrightYear:
    def test_returns_service_value(self):
        from app.utils.organization_helpers import get_org_copyright_year
        with patch("app.utils.organization_helpers.get_organization_copyright_year", return_value="2024") as mock_fn:
            result = get_org_copyright_year()
            assert result == "2024"

    def test_default_none_forwarded(self):
        from app.utils.organization_helpers import get_org_copyright_year
        with patch("app.utils.organization_helpers.get_organization_copyright_year", return_value="") as mock_fn:
            get_org_copyright_year()
            mock_fn.assert_called_once_with(default=None)


@pytest.mark.unit
class TestGetOrgBranding:
    def test_delegates_to_service(self):
        from app.utils.organization_helpers import get_org_branding
        expected = {"organization_name": "HDB", "organization_domain": "hdb.org"}
        with patch("app.utils.organization_helpers.get_organization_branding", return_value=expected) as mock_fn:
            result = get_org_branding()
            mock_fn.assert_called_once()
            assert result == expected


@pytest.mark.unit
class TestGetBrandingContext:
    def _patch_all(self, branding, org_name="HDB Full", short_name="HDB", logo="logo.svg"):
        return (
            patch("app.utils.organization_helpers.get_organization_branding", return_value=branding),
            patch("app.utils.organization_helpers.get_org_name", return_value=org_name),
            patch("app.utils.organization_helpers.get_org_short_name", return_value=short_name),
            patch("app.utils.organization_helpers.get_organization_logo_path", return_value=logo),
        )

    def test_all_keys_present(self):
        from app.utils.organization_helpers import get_branding_context
        branding = {
            "organization_domain": "hdb.org",
            "organization_email_domain": "mail.hdb.org",
            "organization_copyright_year": "2024",
        }
        p1, p2, p3, p4 = self._patch_all(branding)
        with p1, p2, p3, p4:
            result = get_branding_context()
        assert result["org_name"] == "HDB Full"
        assert result["org_short_name"] == "HDB"
        assert result["org_domain"] == "hdb.org"
        assert result["org_email_domain"] == "mail.hdb.org"
        assert result["org_logo"] == "logo.svg"
        assert result["org_copyright_year"] == "2024"

    def test_email_domain_falls_back_to_domain(self):
        from app.utils.organization_helpers import get_branding_context
        branding = {
            "organization_domain": "hdb.org",
            # no organization_email_domain key
            "organization_copyright_year": "2024",
        }
        p1, p2, p3, p4 = self._patch_all(branding)
        with p1, p2, p3, p4:
            result = get_branding_context()
        assert result["org_email_domain"] == "hdb.org"

    def test_locale_forwarded_to_name_helpers(self):
        from app.utils.organization_helpers import get_branding_context
        branding = {"organization_domain": "x.org", "organization_copyright_year": ""}
        with patch("app.utils.organization_helpers.get_organization_branding", return_value=branding):
            with patch("app.utils.organization_helpers.get_org_name") as mock_name:
                mock_name.return_value = "Org"
                with patch("app.utils.organization_helpers.get_org_short_name") as mock_short:
                    mock_short.return_value = "O"
                    with patch("app.utils.organization_helpers.get_organization_logo_path", return_value="l.svg"):
                        get_branding_context(locale="fr")
                        mock_name.assert_called_once_with(locale="fr")
                        mock_short.assert_called_once_with(locale="fr")
