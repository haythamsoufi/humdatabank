"""Tests for app/routes/api/indicator_bank_compat.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

pytestmark = [pytest.mark.unit]

_AUTH_PATCH = "app.routes.api.indicator_bank_compat.authenticate_db_api_key_only"
_API_HEADERS = {"Authorization": "Bearer test-key-123"}


class _FakeKey:
    is_active = True
    key_id = "test"
    client_name = "Test"
    rate_limit_per_minute = 1000
    is_revoked = False


def _make_indicator(id=1, name="Test Indicator", archived=False):
    ind = MagicMock()
    ind.id = id
    ind.name = name
    ind.archived = archived
    ind.name_translations = {"en": name}
    ind.definition = "A definition"
    ind.definition_translations = {"en": "A definition"}
    ind.unit = "Number"
    ind.type = "Output"
    ind.comments = ""
    ind.emergency = False
    ind.disaggregation_guidance = ""
    ind.data_source = ""
    ind.area = ""
    ind.sector = {}
    ind.sub_sector = {}
    ind.related_programs_list = []
    ind.monitoring_questions_list = []
    ind.tags_list = []
    ind.created_at = MagicMock()
    ind.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    ind.updated_at = MagicMock()
    ind.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
    ind.measurement_type = None
    ind.measurement_unit = None
    return ind


def _make_sector(id=1, name="Health"):
    s = MagicMock()
    s.id = id
    s.name = name
    s.display_order = 1
    s.is_active = True
    s.logo_filename = None
    s.get_name_translation = MagicMock(return_value=name)
    return s


def _make_subsector(id=1, name="Sub Health", sector_id=1):
    s = MagicMock()
    s.id = id
    s.name = name
    s.display_order = 1
    s.sector_id = sector_id
    s.is_active = True
    s.get_name_translation = MagicMock(return_value=name)
    return s


def _mock_indicator_query(items):
    q = MagicMock()
    q.options.return_value = q
    q.order_by.return_value = q
    q.filter.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.count.return_value = len(items)
    q.all.return_value = items
    return q


class TestIndicatorList:
    """Tests for GET /Indicator."""

    URL = "/Indicator"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_empty_list(self, client, app):
        q = _mock_indicator_query([])
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0
        assert data["values"] == []

    def test_returns_indicators(self, client, app):
        ind = _make_indicator(id=1, name="Test Ind")
        q = _mock_indicator_query([ind])
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert len(data["values"]) == 1
        assert data["values"][0]["id"] == 1

    def test_pagination_params_respected(self, client, app):
        q = _mock_indicator_query([])
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(f"{self.URL}?Offset=10&Limit=5", headers=_API_HEADERS)
        assert resp.status_code == 200
        q.offset.assert_called_with(10)
        q.limit.assert_called_with(5)

    def test_filter_text(self, client, app):
        q = _mock_indicator_query([])
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(f"{self.URL}?Filter=health", headers=_API_HEADERS)
        assert resp.status_code == 200
        q.filter.assert_called()

    def test_show_archived_true(self, client, app):
        q = _mock_indicator_query([])
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(f"{self.URL}?ShowIsArchived=true", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_show_archived_false(self, client, app):
        q = _mock_indicator_query([])
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(f"{self.URL}?ShowIsArchived=false", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_language_header(self, client, app):
        q = _mock_indicator_query([])
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(self.URL, headers={**_API_HEADERS, "X-Language": "fr"})
        assert resp.status_code == 200


class TestIndicatorDetail:
    """Tests for GET /Indicator/<id>."""

    def _url(self, iid):
        return f"/Indicator/{iid}"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self._url(1))
        assert resp.status_code == 401

    def test_not_found_returns_404(self, client, app):
        from app import db
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch.object(db.session, "get", return_value=None):
            resp = client.get(self._url(999), headers=_API_HEADERS)
        assert resp.status_code == 404

    def test_returns_indicator_detail(self, client, app):
        from app import db
        ind = _make_indicator(id=1)
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch.object(db.session, "get", return_value=ind), \
             patch("app.routes.api.indicator_bank_compat._load_sector_maps",
                   return_value=({}, {}, {}, {})):
            resp = client.get(self._url(1), headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 1
        assert "title" in data
        assert "definition" in data


class TestIndicatorSearch:
    """Tests for GET /Indicator/search."""

    URL = "/Indicator/search"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_empty_query_returns_empty(self, client, app):
        with patch(_AUTH_PATCH, return_value=_FakeKey()):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_with_embeddings(self, client, app):
        mock_svc = MagicMock()
        mock_svc.has_embeddings.return_value = True
        ind = _make_indicator(id=1, name="Water Sanitation")
        mock_svc.resolve.return_value = [(ind, 0.95)]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorResolutionService",
                   return_value=mock_svc):
            resp = client.get(f"{self.URL}?filter=water", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert "score" in data[0]

    def test_without_embeddings_falls_back_to_query(self, client, app):
        mock_svc = MagicMock()
        mock_svc.has_embeddings.return_value = False
        ind = _make_indicator(id=2, name="Health Indicator")
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = [ind]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorResolutionService",
                   return_value=mock_svc), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q):
            resp = client.get(f"{self.URL}?Filter=health", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["score"] == 1.0


class TestIndicatorTags:
    """Tests for GET /Indicator/tags."""

    URL = "/Indicator/tags"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_returns_sorted_tags(self, client, app):
        ind1 = MagicMock()
        ind1.tags_list = ["water", "health"]
        ind2 = MagicMock()
        ind2.tags_list = ["shelter"]
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [ind1, ind2]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        tags = resp.get_json()
        assert isinstance(tags, list)
        assert tags == sorted(tags)

    def test_empty_tags(self, client, app):
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestIndicatorSelectOptions:
    """Tests for GET /Indicator/selectOptions."""

    URL = "/Indicator/selectOptions"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_returns_option_lists(self, client, app):
        ind = MagicMock()
        ind.unit = "Number"
        ind.type = "Output"
        ind.disaggregation_guidance = "By sex"
        ind.tags_list = ["tag1"]
        ind.monitoring_questions_list = ["Q1"]
        ind.related_programs_list = ["P1"]
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [ind]
        type_q = MagicMock()
        type_q.filter_by.return_value = type_q
        type_q.order_by.return_value = type_q
        type_q.all.return_value = []
        unit_q = MagicMock()
        unit_q.filter_by.return_value = unit_q
        unit_q.order_by.return_value = unit_q
        unit_q.all.return_value = []
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBank.query", q), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBankType.query", type_q), \
             patch("app.routes.api.indicator_bank_compat.IndicatorBankUnit.query", unit_q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "unitOfMeasurements" in data
        assert "typeOfMeasurements" in data
        assert "tags" in data
        assert "emergencies" in data


class TestIndicatorSuggestion:
    """Tests for POST /Indicator/Suggestion."""

    URL = "/Indicator/Suggestion"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.post(self.URL, json={})
        assert resp.status_code == 401

    def test_recaptcha_failure_returns_400(self, client, app):
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._verify_recaptcha", return_value=False):
            resp = client.post(self.URL, json={"token": "bad_token"},
                               headers=_API_HEADERS, content_type="application/json")
        assert resp.status_code == 400

    def test_missing_required_fields_returns_400(self, client, app):
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._verify_recaptcha", return_value=True):
            resp = client.post(self.URL, json={"token": "valid"},
                               headers=_API_HEADERS, content_type="application/json")
        assert resp.status_code == 400

    def test_successful_suggestion_submission(self, client, app):
        from app import db
        payload = {
            "token": "valid",
            "name": "Test User",
            "email": "test@example.com",
            "motivation": "This indicator needs improvement",
            "operation": 0,
            "title": "New Indicator",
        }
        mock_suggestion = MagicMock()
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._verify_recaptcha", return_value=True), \
             patch("app.routes.api.indicator_bank_compat.IndicatorSuggestion",
                   return_value=mock_suggestion), \
             patch.object(db.session, "add"), \
             patch.object(db.session, "commit"):
            resp = client.post(self.URL, json=payload,
                               headers=_API_HEADERS, content_type="application/json")
        assert resp.status_code == 200

    def test_operation_integer_mapping(self, client, app):
        """Operation integer 1 maps to 'correction' suggestion type."""
        from app import db
        payload = {
            "token": "valid",
            "name": "User",
            "email": "user@example.com",
            "motivation": "Correction needed",
            "operation": 1,
            "title": "Correction",
        }
        captured = {}
        def capture_suggestion(**kwargs):
            captured.update(kwargs)
            return MagicMock()
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._verify_recaptcha", return_value=True), \
             patch("app.routes.api.indicator_bank_compat.IndicatorSuggestion",
                   side_effect=lambda **kw: (captured.update(kw), MagicMock())[1]), \
             patch.object(db.session, "add"), \
             patch.object(db.session, "commit"):
            resp = client.post(self.URL, json=payload,
                               headers=_API_HEADERS, content_type="application/json")
        assert resp.status_code == 200
        assert captured.get("suggestion_type") == "correction"

    def test_operation_string_new(self, client, app):
        """Operation string 'new' maps to 'new_indicator'."""
        from app import db
        payload = {
            "token": "valid",
            "name": "User",
            "email": "user@test.com",
            "motivation": "Need a new indicator",
            "operation": "new",
            "title": "New",
        }
        captured = {}
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._verify_recaptcha", return_value=True), \
             patch("app.routes.api.indicator_bank_compat.IndicatorSuggestion",
                   side_effect=lambda **kw: (captured.update(kw), MagicMock())[1]), \
             patch.object(db.session, "add"), \
             patch.object(db.session, "commit"):
            resp = client.post(self.URL, json=payload,
                               headers=_API_HEADERS, content_type="application/json")
        assert resp.status_code == 200
        assert captured.get("suggestion_type") == "new_indicator"

    def test_related_programs_as_list(self, client, app):
        """relatedPrograms as list is joined into a string."""
        from app import db
        payload = {
            "token": "valid",
            "name": "User",
            "email": "user@test.com",
            "motivation": "Needs link",
            "operation": 2,
            "title": "Ind",
            "relatedPrograms": ["Program A", "Program B"],
        }
        captured = {}
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._verify_recaptcha", return_value=True), \
             patch("app.routes.api.indicator_bank_compat.IndicatorSuggestion",
                   side_effect=lambda **kw: (captured.update(kw), MagicMock())[1]), \
             patch.object(db.session, "add"), \
             patch.object(db.session, "commit"):
            resp = client.post(self.URL, json=payload,
                               headers=_API_HEADERS, content_type="application/json")
        assert resp.status_code == 200
        assert "Program A" in (captured.get("related_programs") or "")

    def test_sector_data_included(self, client, app):
        """primarySector in payload → sector_data passed to IndicatorSuggestion."""
        from app import db
        payload = {
            "token": "valid",
            "name": "User",
            "email": "user@test.com",
            "motivation": "Sector info needed",
            "operation": "other",
            "title": "Ind",
            "primarySector": "Health",
        }
        captured = {}
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._verify_recaptcha", return_value=True), \
             patch("app.routes.api.indicator_bank_compat.IndicatorSuggestion",
                   side_effect=lambda **kw: (captured.update(kw), MagicMock())[1]), \
             patch.object(db.session, "add"), \
             patch.object(db.session, "commit"):
            resp = client.post(self.URL, json=payload,
                               headers=_API_HEADERS, content_type="application/json")
        assert resp.status_code == 200
        assert captured.get("sector") is not None


class TestSectorList:
    """Tests for GET /Sector."""

    URL = "/Sector"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_empty_sector_list(self, client, app):
        sector_q = MagicMock()
        sector_q.filter_by.return_value = sector_q
        sector_q.order_by.return_value = sector_q
        sector_q.all.return_value = []
        subsector_q = MagicMock()
        subsector_q.filter_by.return_value = subsector_q
        subsector_q.order_by.return_value = subsector_q
        subsector_q.all.return_value = []
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.Sector.query", sector_q), \
             patch("app.routes.api.indicator_bank_compat.SubSector.query", subsector_q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_sectors_with_subsectors(self, client, app):
        sector = _make_sector(id=1, name="Health")
        subsector = _make_subsector(id=1, name="Primary Health", sector_id=1)
        sector_q = MagicMock()
        sector_q.filter_by.return_value = sector_q
        sector_q.order_by.return_value = sector_q
        sector_q.all.return_value = [sector]
        subsector_q = MagicMock()
        subsector_q.filter_by.return_value = subsector_q
        subsector_q.order_by.return_value = subsector_q
        subsector_q.all.return_value = [subsector]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.Sector.query", sector_q), \
             patch("app.routes.api.indicator_bank_compat.SubSector.query", subsector_q), \
             patch("app.routes.api.indicator_bank_compat._sector_image_bytes", return_value=None):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert "subsectors" in data[0]


class TestSubsectorList:
    """Tests for GET /Subsector."""

    URL = "/Subsector"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_returns_subsectors(self, client, app):
        subsector = _make_subsector(id=1, name="Sub Health", sector_id=1)
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.all.return_value = [subsector]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.SubSector.query", q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["id"] == 1

    def test_empty_subsector_list(self, client, app):
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.all.return_value = []
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.SubSector.query", q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestListHome:
    """Tests for GET /list-home."""

    URL = "/list-home"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_returns_sector_list(self, client, app):
        sector = _make_sector(id=1, name="Health")
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.all.return_value = [sector]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.Sector.query", q), \
             patch("app.routes.api.indicator_bank_compat._count_indicators_for_sector",
                   return_value=5), \
             patch("app.routes.api.indicator_bank_compat._sector_image_bytes",
                   return_value=None):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["indicatorsCount"] == 5


class TestExportExcel:
    """Tests for GET /Excel."""

    URL = "/Excel"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_returns_excel_file(self, client, app):
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._build_legacy_excel_export",
                   return_value=b"fake_excel_bytes"):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type

    def test_excel_export_failure_returns_500(self, client, app):
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat._build_legacy_excel_export",
                   side_effect=RuntimeError("boom")):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 500


class TestCommonWordList:
    """Tests for GET /CommonWord."""

    URL = "/CommonWord"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_empty_common_words(self, client, app):
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.all.return_value = []
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.CommonWord.query", q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_common_words(self, client, app):
        word = MagicMock()
        word.term = "indicator"
        word.meaning = "A measurable value"
        word.get_meaning_translation = MagicMock(return_value="A measurable value")
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.all.return_value = [word]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.CommonWord.query", q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["term"] == "indicator"
        assert "meaning" in data[0]

    def test_word_without_translation_method(self, client, app):
        """Words without get_meaning_translation use .meaning directly."""
        word = MagicMock(spec=["term", "meaning"])
        word.term = "capacity"
        word.meaning = "Ability to do something"
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.all.return_value = [word]
        with patch(_AUTH_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.indicator_bank_compat.CommonWord.query", q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data[0]["meaning"] == "Ability to do something"


class TestCompatHelpers:
    """Unit tests for helper functions in indicator_bank_compat."""

    def test_compat_locale_default_en(self, app):
        from app.routes.api.indicator_bank_compat import _compat_locale
        with app.test_request_context("/"):
            result = _compat_locale()
        assert result == "en"

    def test_compat_locale_from_query_param(self, app):
        from app.routes.api.indicator_bank_compat import _compat_locale
        with app.test_request_context("/?language=fr"):
            result = _compat_locale()
        assert result == "fr"

    def test_compat_locale_from_header(self, app):
        from app.routes.api.indicator_bank_compat import _compat_locale
        with app.test_request_context("/", headers={"X-Language": "es"}):
            result = _compat_locale()
        assert result == "es"

    def test_compat_locale_normalizes_subtag(self, app):
        from app.routes.api.indicator_bank_compat import _compat_locale
        with app.test_request_context("/?language=fr_FR"):
            result = _compat_locale()
        assert result == "fr"

    def test_localized_text_found(self, app):
        from app.routes.api.indicator_bank_compat import _localized_text
        translations = {"en": "Hello", "fr": "Bonjour"}
        with app.test_request_context("/"):
            result = _localized_text(translations, "fr", "Hello")
        assert result == "Bonjour"

    def test_localized_text_fallback(self, app):
        from app.routes.api.indicator_bank_compat import _localized_text
        with app.test_request_context("/"):
            result = _localized_text(None, "fr", "Fallback")
        assert result == "Fallback"

    def test_localized_text_empty_translation_falls_back(self, app):
        from app.routes.api.indicator_bank_compat import _localized_text
        translations = {"fr": ""}
        with app.test_request_context("/"):
            result = _localized_text(translations, "fr", "Fallback")
        assert result == "Fallback"

    def test_emergency_to_string_true(self, app):
        from app.routes.api.indicator_bank_compat import _emergency_to_string
        with app.test_request_context("/"):
            result = _emergency_to_string(True)
        assert result == "Yes"

    def test_emergency_to_string_false(self, app):
        from app.routes.api.indicator_bank_compat import _emergency_to_string
        with app.test_request_context("/"):
            result = _emergency_to_string(False)
        assert result == ""

    def test_emergency_to_string_none(self, app):
        from app.routes.api.indicator_bank_compat import _emergency_to_string
        with app.test_request_context("/"):
            result = _emergency_to_string(None)
        assert result == ""

    def test_emergency_to_string_string_value(self, app):
        from app.routes.api.indicator_bank_compat import _emergency_to_string
        with app.test_request_context("/"):
            result = _emergency_to_string("Emergency")
        assert result == "Emergency"

    def test_select_option_format(self, app):
        from app.routes.api.indicator_bank_compat import _select_option
        with app.test_request_context("/"):
            result = _select_option("Yes")
        assert result == {"text": "Yes", "value": "Yes"}

    def test_verify_recaptcha_empty_token(self, app):
        from app.routes.api.indicator_bank_compat import _verify_recaptcha
        with app.test_request_context("/"):
            result = _verify_recaptcha("")
        assert result is False

    def test_verify_recaptcha_no_project_config(self, app):
        """Missing RECAPTCHA_PROJECT_ID config → returns True (skip validation)."""
        from app.routes.api.indicator_bank_compat import _verify_recaptcha
        with app.test_request_context("/"):
            app.config.pop("RECAPTCHA_PROJECT_ID", None)
            app.config.pop("RECAPTCHA_API_KEY", None)
            result = _verify_recaptcha("some_token")
        assert result is True

    def test_localized_sector_subsector_name_none(self, app):
        from app.routes.api.indicator_bank_compat import _localized_sector_subsector_name
        with app.test_request_context("/"):
            result = _localized_sector_subsector_name(None, "en")
        assert result is None

    def test_localized_sector_subsector_name_with_translation(self, app):
        from app.routes.api.indicator_bank_compat import _localized_sector_subsector_name
        entity = MagicMock()
        entity.get_name_translation = MagicMock(return_value="Health")
        entity.name = "Health"
        with app.test_request_context("/"):
            result = _localized_sector_subsector_name(entity, "en")
        assert result == "Health"

    def test_sector_image_bytes_no_logo(self, app):
        from app.routes.api.indicator_bank_compat import _sector_image_bytes
        sector = MagicMock()
        sector.logo_filename = None
        with app.test_request_context("/"):
            result = _sector_image_bytes(sector)
        assert result is None

    def test_legacy_excel_emergency_true(self, app):
        from app.routes.api.indicator_bank_compat import _legacy_excel_emergency
        ind = MagicMock()
        ind.emergency = True
        with app.test_request_context("/"):
            result = _legacy_excel_emergency(ind)
        assert result == "Emergency"

    def test_legacy_excel_emergency_false(self, app):
        from app.routes.api.indicator_bank_compat import _legacy_excel_emergency
        ind = MagicMock()
        ind.emergency = False
        with app.test_request_context("/"):
            result = _legacy_excel_emergency(ind)
        assert result == ""
