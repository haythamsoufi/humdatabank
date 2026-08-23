"""Unit tests for organization translation lookup and missing-count helpers."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.unit]


class TestIsoLanguageCode:
    def test_locale_and_legacy_russian(self):
        from app.forms.organization.translation_helpers import iso_language_code

        assert iso_language_code("ru_RU") == "ru"
        assert iso_language_code("ru-RU") == "ru"
        assert iso_language_code("Russian") == "ru"
        assert iso_language_code("ru") == "ru"
        assert iso_language_code("") == ""
        assert iso_language_code(None) == ""


class TestLookupTranslation:
    def test_finds_iso_locale_and_legacy_keys(self):
        from app.forms.organization.translation_helpers import lookup_translation

        assert lookup_translation({"ru": "Красный"}, "ru") == "Красный"
        assert lookup_translation({"ru_RU": "Красный"}, "ru") == "Красный"
        assert lookup_translation({"russian": "Красный"}, "ru") == "Красный"
        assert lookup_translation({"fr": "Croix"}, "ru") == ""
        assert lookup_translation(None, "ru") == ""


class TestCountMissingNameTranslations:
    def test_counts_missing_russian_when_other_languages_present(self, app):
        from app.forms.organization.translation_helpers import count_missing_name_translations

        ns = SimpleNamespace(
            name="Foo NS",
            name_translations={"fr": "Société", "es": "Sociedad", "ar": "جمعية", "zh": "红会"},
        )
        with app.app_context():
            app.config["TRANSLATABLE_LANGUAGES"] = ["fr", "es", "ar", "ru", "zh"]
            result = count_missing_name_translations([ns])

        assert result["ru"] == 1
        assert result["fr"] == 0
        assert result["es"] == 0

    def test_locale_key_counts_as_present(self, app):
        from app.forms.organization.translation_helpers import count_missing_name_translations

        ns = SimpleNamespace(
            name="Foo NS",
            name_translations={"ru_RU": "Красный Крест"},
        )
        with app.app_context():
            app.config["TRANSLATABLE_LANGUAGES"] = ["ru"]
            result = count_missing_name_translations([ns])

        assert result["ru"] == 0


class TestApplyOrganizationEntityTranslations:
    def _translator(self, batch_return=None, text_return="Красный Крест"):
        mock = MagicMock()
        mock.translate_text.return_value = text_return
        if batch_return is None:
            mock.translate_batch.side_effect = AssertionError("expected translate_batch")
        else:
            mock.translate_batch.return_value = batch_return
        return mock

    def test_batches_multiple_ns_names_and_persists_russian(self, db_session, app):
        from app.forms.organization.translation_helpers import apply_organization_entity_translations
        from app.models.organization import NationalSociety
        from tests.factories import create_test_country

        country = create_test_country(db_session, name="Bulk RU Country", iso3="BRC", iso2="BR")
        ns1 = NationalSociety(name="Alpha NS", country_id=country.id, is_active=True, name_translations={"fr": "A"})
        ns2 = NationalSociety(name="Beta NS", country_id=country.id, is_active=True, name_translations={"fr": "B"})
        db_session.add_all([ns1, ns2])
        db_session.commit()

        translator = self._translator(batch_return=["Альфа", "Бета"])
        outcome = apply_organization_entity_translations(
            [
                {
                    "id": f"national_societies:{ns1.id}:name:ru",
                    "entity_type": "national_societies",
                    "entity_id": ns1.id,
                    "field": "name",
                    "text": ns1.name,
                    "target_languages": ["ru"],
                },
                {
                    "id": f"national_societies:{ns2.id}:name:ru",
                    "entity_type": "national_societies",
                    "entity_id": ns2.id,
                    "field": "name",
                    "text": ns2.name,
                    "target_languages": ["ru"],
                },
            ],
            auto_translator=translator,
            service_name="ifrc",
        )

        assert outcome["success_count"] == 2
        translator.translate_batch.assert_called_once()
        translator.translate_text.assert_not_called()
        db_session.expire_all()
        assert db_session.get(NationalSociety, ns1.id).name_translations["ru"] == "Альфа"
        assert db_session.get(NationalSociety, ns2.id).name_translations["ru"] == "Бета"

    def test_skips_existing_unless_overwrite(self, db_session, app):
        from app.forms.organization.translation_helpers import apply_organization_entity_translations
        from app.models.organization import NationalSociety
        from tests.factories import create_test_country

        country = create_test_country(db_session, name="Skip RU Country", iso3="SRC", iso2="SR")
        ns = NationalSociety(
            name="Existing RU NS",
            country_id=country.id,
            is_active=True,
            name_translations={"ru": "Старое"},
        )
        db_session.add(ns)
        db_session.commit()
        ns_id = ns.id

        translator = self._translator(text_return="Новое")
        skipped = apply_organization_entity_translations(
            [{
                "entity_type": "national_societies",
                "entity_id": ns_id,
                "field": "name",
                "text": "Existing RU NS",
                "target_languages": ["ru"],
            }],
            overwrite=False,
            auto_translator=translator,
        )
        assert skipped["success_count"] == 0
        assert skipped["skipped_existing"] == 1
        translator.translate_text.assert_not_called()

        overwritten = apply_organization_entity_translations(
            [{
                "entity_type": "national_societies",
                "entity_id": ns_id,
                "field": "name",
                "text": "Existing RU NS",
                "target_languages": ["ru"],
            }],
            overwrite=True,
            auto_translator=translator,
        )
        assert overwritten["success_count"] == 1
        db_session.expire_all()
        assert db_session.get(NationalSociety, ns_id).name_translations["ru"] == "Новое"
