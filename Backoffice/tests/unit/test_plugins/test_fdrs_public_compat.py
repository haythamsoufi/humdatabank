"""Tests for the FDRS public-frontend adapter (legacy data.ifrc.org contract).

Covers ``plugins/fdrs/services/fdrs_public_adapter.py`` (code parsing, value
extraction), ``plugins/fdrs/public_compat_routes.py`` (paths, auth, shapes,
passthrough) and ``plugins/fdrs/services/fdrs_society_import.py``.

The route tests use a real ``APIKey`` row and the legacy ``?apiKey=`` query form; no
auth is mocked. Only the published snapshot of ``privacy = public`` items may appear.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

from app.models import FormData, IndicatorBank, NationalSociety
from app.models.assignments import AssignmentEntityStatus
from app.services.security.api_key_permissions import CONTENT_READ, build_permissions_document
from app.utils.datetime_helpers import utcnow
from plugins.fdrs.services import fdrs_public_adapter as adapter
from plugins.fdrs.services.fdrs_society_import import entity_fields, upsert_societies
from tests.factories import (
    create_test_api_key,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_section,
    create_test_template,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Pure parsing / extraction (no database)
# ---------------------------------------------------------------------------


class TestParseCode:
    def test_headline_total_has_bank_candidates(self):
        spec = adapter.parse_code("KPI_PeopleVol_Tot")
        assert spec.kind == adapter.KIND_TOTAL
        assert spec.candidates == ("KPI_PeopleVol_Tot", "KPI_PeopleVol")
        assert spec.reported_only is True

    def test_cpd_suffix_is_stripped(self):
        assert adapter.parse_code("KPI_ReachH_CPD").candidates[-1] == "KPI_ReachH"

    def test_plain_bank_code_has_single_candidate(self):
        assert adapter.parse_code("KPI_IncomeLC_CHF").candidates == ("KPI_IncomeLC_CHF",)

    def test_imputed_suffix_includes_imputed_values(self):
        spec = adapter.parse_code("KPI_PeopleVol_Tot_IP")
        assert spec.reported_only is False
        assert spec.code == "KPI_PeopleVol_Tot_IP"

    def test_sex_series(self):
        spec = adapter.parse_code("KPI_PeopleVol_Tot_F")
        assert (spec.kind, spec.sex, spec.age) == (adapter.KIND_SEX, "female", None)
        assert spec.candidates[-1] == "KPI_PeopleVol"

    def test_age_series(self):
        spec = adapter.parse_code("KPI_PeopleVol_M_age_6_12")
        assert (spec.kind, spec.sex, spec.age) == (adapter.KIND_AGE, "male", "6_12")
        assert adapter.parse_code("KPI_PeopleVol_F_age_80").age == "80"

    def test_unknown_age_band_is_dropped(self):
        assert adapter.parse_code("KPI_PeopleVol_M_age_5_9") is None

    def test_income_question_and_network_codes(self):
        assert adapter.parse_code("si_CHF").kind == adapter.KIND_INCOME
        assert adapter.parse_code("si_CHF").income_row == "Service income"
        assert adapter.parse_code("KPI_pr_sex").kind == adapter.KIND_QUESTION
        network = adapter.parse_code("received_support1")
        assert (network.kind, network.network_prefix, network.network_slot) == (
            adapter.KIND_NETWORK, "received_support", 1,
        )
        assert adapter.parse_code("supported1_amount").network_amount is True

    def test_blank_is_none(self):
        assert adapter.parse_code("  ") is None


class TestResolveRequested:
    def test_unscoped_request_returns_only_the_requested_series(self):
        specs = adapter.resolve_requested("KPI_PeopleVol_Tot,KPI_PStaff_Tot", society_scoped=False)
        assert [s.code for s in specs] == ["KPI_PeopleVol_Tot", "KPI_PStaff_Tot"]

    def test_headline_code_on_a_society_adds_sex_series_only(self):
        codes = [s.code for s in adapter.resolve_requested("KPI_PeopleVol_Tot", society_scoped=True)]
        assert codes == ["KPI_PeopleVol_Tot", "KPI_PeopleVol_Tot_M", "KPI_PeopleVol_Tot_F"]

    def test_bare_code_on_a_society_adds_every_age_band(self):
        codes = [s.code for s in adapter.resolve_requested("KPI_PeopleVol", society_scoped=True)]
        assert len(codes) == 1 + 2 + 2 * len(adapter.AGE_BANDS)
        assert "KPI_PeopleVol_M_age_6_12" in codes
        assert "KPI_PeopleVol_F_age_80" in codes

    def test_imputed_read_gets_no_breakdowns(self):
        codes = [s.code for s in adapter.resolve_requested("KPI_PeopleVol_Tot_IP", society_scoped=True)]
        assert codes == ["KPI_PeopleVol_Tot_IP"]

    def test_duplicates_collapse(self):
        specs = adapter.resolve_requested("KPI_PeopleVol_Tot,KPI_PeopleVol_Tot", society_scoped=False)
        assert len(specs) == 1


class TestValueExtraction:
    def test_sex_age_cells(self):
        disagg = {
            "mode": "sex_age",
            "values": {"male_6_12": 100, "female_6_12": "200", "male_13_17": 300, "male_80_": 5, "total": 999},
        }
        cells = adapter.breakdown_cells(disagg)
        assert cells[("male", "6_12")] == 100
        assert cells[("female", "6_12")] == 200
        assert cells[("male", "80")] == 5
        assert adapter.sex_total(disagg, "male") == 405
        assert adapter.sex_total(disagg, "female") == 200
        assert adapter.age_value(disagg, "male", "13_17") == 300
        assert adapter.age_value(disagg, "female", "13_17") is None

    def test_sex_only_cells(self):
        disagg = {"values": {"male": 10, "female": 20, "non_binary": 3}}
        assert adapter.sex_total(disagg, "male") == 10
        assert adapter.sex_total(disagg, "female") == 20

    def test_age_only_cells_have_no_sex_split(self):
        assert adapter.sex_total({"values": {"6_12": 5}}, "male") is None

    def test_disagg_total_ignores_structure_keys(self):
        assert adapter.disagg_total({"mode": "sex", "values": {"male": 1, "female": 2, "total": 50}}) == 3

    def test_json_number_drops_trailing_zero(self):
        assert adapter.json_number(1500.0) == 1500
        assert adapter.json_number(1.5) == 1.5

    def test_constants_match_the_sync_scripts(self):
        from plugins.fdrs.scripts_path import ensure_fdrs_scripts_in_path

        ensure_fdrs_scripts_in_path()
        sys.modules.pop("fdrs_sync_constants", None)
        import fdrs_sync_constants as legacy

        assert adapter.INCOME_MATRIX_ITEM_ID == legacy.FDRS_INCOME_SOURCES_MATRIX_ITEM_ID
        assert adapter.INCOME_MATRIX_COLUMN == legacy.FDRS_INCOME_SOURCES_MATRIX_COLUMN
        assert adapter.INCOME_KPI_TO_ROW == legacy.FDRS_INCOME_KPI_TO_MATRIX_ROW
        assert adapter.QUESTION_KPI_TO_ITEM["KPI_pr_sex"] == legacy.FDRS_QUESTION_KPI_TO_ITEM["KPI_pr_sex"]
        assert adapter.QUESTION_KPI_TO_ITEM["KPI_sg_sex"] == legacy.FDRS_QUESTION_KPI_TO_ITEM["KPI_sg_sex"]
        assert adapter.NETWORK_ITEMS["supported"] == (
            legacy.FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID, legacy.FDRS_NETWORK_SUPPORT_GIVEN_COLUMN,
        )
        assert adapter.NETWORK_ITEMS["received_support"] == (
            legacy.FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID, legacy.FDRS_NETWORK_SUPPORT_RECEIVED_COLUMN,
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _public(item):
    item.set_privacy("public")
    flag_modified(item, "config")


def _publish(db_session, aes, item, *, value=None, disagg=None, source=FormData.PUBLISHED_SOURCE_REPORTED):
    row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item.id,
        value=None if value is None else str(value),
        published_value=None if value is None else str(value),
        published_numeric_value=float(value) if isinstance(value, (int, float)) else None,
        published_disagg_data=disagg,
        published_source=source,
        published_at=utcnow(),
    )
    db_session.add(row)
    return row


@pytest.fixture
def scenario(db_session, monkeypatch):
    template = create_test_template(db_session, name="FDRS Compat Test Template")
    monkeypatch.setattr(adapter, "FDRS_TEMPLATE_ID", template.id)
    section = create_test_section(db_session, template)

    volunteers = IndicatorBank(
        name="Compat volunteers", type="number", unit="people", archived=False, fdrs_kpi_code="KPI_PeopleVol",
    )
    secret = IndicatorBank(
        name="Compat secret", type="number", unit="people", archived=False, fdrs_kpi_code="KPI_CompatSecret",
    )
    db_session.add_all([volunteers, secret])
    db_session.commit()

    item_vol = create_test_item(db_session, section, template, label="Volunteers", indicator_bank_id=volunteers.id)
    item_secret = create_test_item(db_session, section, template, label="Secret", indicator_bank_id=secret.id)
    item_income = create_test_item(db_session, section, template, label="Income sources", type="matrix")
    item_given = create_test_item(db_session, section, template, label="Network given", type="matrix")
    item_president = create_test_item(db_session, section, template, label="President sex", type="text")
    for item in (item_vol, item_income, item_given, item_president):
        _public(item)
    db_session.commit()

    monkeypatch.setattr(adapter, "INCOME_MATRIX_ITEM_ID", item_income.id)
    monkeypatch.setitem(adapter.QUESTION_KPI_TO_ITEM, "KPI_pr_sex", item_president.id)
    monkeypatch.setitem(adapter.NETWORK_ITEMS, "supported", (item_given.id, "Funding provided"))

    country_a = create_test_country(db_session, name="Compatland A", iso2="CA", iso3="CAA")
    country_b = create_test_country(db_session, name="Compatland B", iso2="CB", iso3="CBB")
    society_a = NationalSociety(
        country_id=country_a.id, name="Society A", fdrs_don_code="DCAA001", fdrs_zone_code="S1",
        latitude=1.5, longitude=2.5,
    )
    society_b = NationalSociety(
        country_id=country_b.id, name="Society B", fdrs_don_code="DCBB001", fdrs_zone_code="S2",
    )
    db_session.add_all([society_a, society_b])
    db_session.commit()

    aes_a_2023 = create_test_assignment_entity_status(db_session, country=country_a, template=template, period_name="2023")
    aes_a_2024 = create_test_assignment_entity_status(db_session, country=country_a, template=template, period_name="2024")
    # One assignment per (template, period); each country is a separate entity status on it.
    aes_b_2024 = AssignmentEntityStatus(
        assigned_form_id=aes_a_2024.assigned_form_id,
        entity_type="country",
        entity_id=country_b.id,
        status="in_progress",
    )
    db_session.add(aes_b_2024)
    db_session.commit()

    _publish(db_session, aes_a_2023, item_vol, value=1000)
    _publish(
        db_session, aes_a_2024, item_vol, value=1500,
        disagg={"mode": "sex_age", "values": {
            "male_6_12": 100, "female_6_12": 200, "male_13_17": 300, "female_13_17": 400, "male_80_": 5,
        }},
    )
    _publish(db_session, aes_b_2024, item_vol, value=700, source=FormData.PUBLISHED_SOURCE_IMPUTED)
    _publish(db_session, aes_a_2024, item_secret, value=42)
    _publish(
        db_session, aes_a_2024, item_income,
        disagg={"Home Government_Funding": 50, "Service income_Funding": 25},
    )
    _publish(db_session, aes_a_2024, item_given, disagg={"Society B_Funding provided": 10})
    _publish(db_session, aes_a_2024, item_president, value="Female")
    # An unpublished edit must never surface, even on a public item.
    db_session.add(FormData(assignment_entity_status_id=aes_b_2024.id, form_item_id=item_income.id, value="draft"))
    db_session.commit()
    return SimpleNamespace(template=template, country_a=country_a, country_b=country_b)


@pytest.fixture
def key(db_session):
    _api_key, full_key = create_test_api_key(
        db_session,
        permissions=build_permissions_document([CONTENT_READ], allow_query_api_key=True),
    )
    return full_key


def _get(client, key, path, **params):
    return client.get(path, query_string={"apiKey": key, **params})


def _series(response):
    return {s["id"]: {n["id"]: n["data"] for n in s["data"]} for s in response.get_json()["data"]}


class TestAuth:
    def test_missing_key_is_rejected(self, client, scenario):
        assert client.get("/api/data", query_string={"indicator": "KPI_PeopleVol_Tot"}).status_code == 401

    def test_unknown_key_is_rejected(self, client, scenario):
        assert _get(client, "nope", "/api/data", indicator="KPI_PeopleVol_Tot").status_code == 401

    def test_legacy_apikey_parameter_authenticates(self, client, scenario, key):
        assert _get(client, key, "/api/lastpublishedyear").status_code == 200

    def test_snake_case_parameter_still_authenticates(self, client, scenario, key):
        assert client.get("/api/lastpublishedyear", query_string={"api_key": key}).status_code == 200

    def test_key_without_query_opt_in_is_refused_in_the_query_string(self, client, db_session, scenario):
        _k, plain = create_test_api_key(db_session, permissions=build_permissions_document([CONTENT_READ]))
        assert _get(client, plain, "/api/lastpublishedyear").status_code == 403
        assert client.get("/api/lastpublishedyear", headers={"X-API-Key": plain}).status_code == 200

    def test_key_without_content_read_is_refused(self, client, db_session, scenario):
        _k, plain = create_test_api_key(
            db_session, permissions=build_permissions_document(["users:read"], allow_query_api_key=True),
        )
        assert _get(client, plain, "/api/lastpublishedyear").status_code == 403


class TestReferenceEndpoints:
    def test_last_published_year(self, client, scenario, key):
        response = _get(client, key, "/api/lastpublishedyear")
        assert response.get_json() == 2024

    def test_society_list_uses_legacy_field_names(self, client, scenario, key):
        rows = _get(client, key, "/api/entities/ns").get_json()
        by_don = {r["KPI_DON_code"]: r for r in rows}
        assert {"DCAA001", "DCBB001"} <= set(by_don)
        row = by_don["DCAA001"]
        assert row["NSO_DON_name"] == "Society A"
        assert row["ZON_Code"] == "S1"
        assert row["NSO_ZON_name"] == "Africa"
        assert row["iso_3"] == "CAA"
        assert row["iso_2"] == "CA"
        assert (row["lat"], row["long"]) == (1.5, 2.5)

    def test_one_society(self, client, scenario, key):
        assert _get(client, key, "/api/entities/ns/dcaa001").get_json()["KPI_DON_code"] == "DCAA001"

    def test_unknown_society_is_404(self, client, scenario, key):
        assert _get(client, key, "/api/entities/ns/NOPE").status_code == 404

    def test_inactive_society_is_hidden(self, client, db_session, scenario, key):
        NationalSociety.query.filter_by(fdrs_don_code="DCBB001").one().is_active = False
        db_session.commit()
        codes = {r["KPI_DON_code"] for r in _get(client, key, "/api/entities/ns").get_json()}
        assert "DCBB001" not in codes


class TestData:
    def test_reported_series_excludes_imputed_societies(self, client, scenario, key):
        response = _get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot")
        assert response.status_code == 200
        series = _series(response)
        assert list(series) == ["KPI_PeopleVol_Tot"]
        assert series["KPI_PeopleVol_Tot"] == {
            "DCAA001": [{"year": 2023, "value": 1000}, {"year": 2024, "value": 1500}],
        }

    def test_imputed_read_includes_imputed_societies(self, client, scenario, key):
        series = _series(_get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot_IP", year=2024))
        assert series["KPI_PeopleVol_Tot_IP"] == {
            "DCAA001": [{"year": 2024, "value": 1500}],
            "DCBB001": [{"year": 2024, "value": 700}],
        }

    def test_dataimputed_serves_the_same_tree(self, client, scenario, key):
        series = _series(_get(client, key, "/api/dataimputed", indicator="KPI_PeopleVol_Tot_IP", year=2024))
        assert "DCBB001" in series["KPI_PeopleVol_Tot_IP"]

    def test_year_filter(self, client, scenario, key):
        series = _series(_get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot", year=2023))
        assert series["KPI_PeopleVol_Tot"]["DCAA001"] == [{"year": 2023, "value": 1000}]

    def test_zone_filter(self, client, scenario, key):
        series = _series(
            _get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot_IP", year=2024, zon_code="S2")
        )
        assert list(series["KPI_PeopleVol_Tot_IP"]) == ["DCBB001"]

    def test_society_filter_accepts_several_codes(self, client, scenario, key):
        series = _series(
            _get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot_IP", year=2024, KPI_Don_Code="DCAA001,DCBB001")
        )
        assert set(series["KPI_PeopleVol_Tot_IP"]) == {"DCAA001", "DCBB001"}

    def test_age_chart_request_returns_sex_age_series(self, client, scenario, key):
        series = _series(
            _get(client, key, "/api/data", indicator="KPI_PeopleVol", year=2024, KPI_Don_Code="DCAA001")
        )
        assert series["KPI_PeopleVol_M_age_6_12"]["DCAA001"] == [{"year": 2024, "value": 100}]
        assert series["KPI_PeopleVol_F_age_13_17"]["DCAA001"] == [{"year": 2024, "value": 400}]
        assert series["KPI_PeopleVol_M_age_80"]["DCAA001"] == [{"year": 2024, "value": 5}]
        assert "KPI_PeopleVol_M_age_18_29" not in series

    def test_sex_chart_request_returns_sex_series(self, client, scenario, key):
        series = _series(
            _get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot", year=2024, KPI_Don_Code="DCAA001")
        )
        assert series["KPI_PeopleVol_Tot_M"]["DCAA001"] == [{"year": 2024, "value": 405}]
        assert series["KPI_PeopleVol_Tot_F"]["DCAA001"] == [{"year": 2024, "value": 600}]

    def test_world_request_does_not_expand_breakdowns(self, client, scenario, key):
        series = _series(_get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot", year=2024))
        assert list(series) == ["KPI_PeopleVol_Tot"]

    def test_income_sources_come_from_the_matrix(self, client, scenario, key):
        series = _series(
            _get(client, key, "/api/data", indicator="h_gov_CHF,si_CHF,ifrc_CHF", year=2024, KPI_Don_Code="DCAA001")
        )
        assert series["h_gov_CHF"]["DCAA001"] == [{"year": 2024, "value": 50}]
        assert series["si_CHF"]["DCAA001"] == [{"year": 2024, "value": 25}]
        assert "ifrc_CHF" not in series

    def test_president_sex_is_text(self, client, scenario, key):
        series = _series(_get(client, key, "/api/data", indicator="KPI_pr_sex", year=2024, KPI_Don_Code="DCAA001"))
        assert series["KPI_pr_sex"]["DCAA001"] == [{"year": 2024, "value": "Female"}]

    def test_network_support_is_a_comma_separated_don_list(self, client, scenario, key):
        series = _series(_get(client, key, "/api/data", indicator="supported1", KPI_Don_Code="DCAA001"))
        assert series["supported1"]["DCAA001"] == [{"year": 2024, "value": "DCBB001"}]
        amounts = _series(_get(client, key, "/api/data", indicator="supported1_amount", KPI_Don_Code="DCAA001"))
        assert amounts["supported1_amount"]["DCAA001"] == [{"year": 2024, "value": "10"}]
        assert "supported2" not in _series(_get(client, key, "/api/data", indicator="supported2"))

    def test_private_and_unknown_codes_return_an_empty_tree(self, client, scenario, key):
        response = _get(client, key, "/api/data", indicator="KPI_CompatSecret,KPI_DoesNotExist")
        assert response.get_json() == {"data": []}

    def test_unpublished_draft_is_not_returned(self, client, scenario, key):
        series = _series(_get(client, key, "/api/data", indicator="h_gov_CHF", year=2024))
        assert list(series["h_gov_CHF"]) == ["DCAA001"]

    def test_indicator_is_required(self, client, scenario, key):
        assert _get(client, key, "/api/data").status_code == 400

    def test_year_must_be_an_integer(self, client, scenario, key):
        assert _get(client, key, "/api/data", indicator="KPI_PeopleVol_Tot", year="abc").status_code == 400


class TestMapAndSummaries:
    def test_imputed_value_list_flags_imputed_rows(self, client, scenario, key):
        rows = _get(client, key, "/api/KpiImputedValue", kpicode="KPI_PeopleVol_Tot_IP", year=2024).get_json()
        assert rows == [
            {"doncode": "DCAA001", "value": 1500, "source": "R"},
            {"doncode": "DCBB001", "value": 700, "source": "I"},
        ]

    def test_imputed_value_requires_kpicode(self, client, scenario, key):
        assert _get(client, key, "/api/KpiImputedValue").status_code == 400

    def test_imputed_value_defaults_to_the_latest_year(self, client, scenario, key):
        rows = _get(client, key, "/api/KpiImputedValue", kpicode="KPI_PeopleVol_Tot_IP").get_json()
        assert {r["doncode"] for r in rows} == {"DCAA001", "DCBB001"}

    def test_global_validation_sums_volunteers_by_zone(self, client, scenario, key):
        rows = _get(client, key, "/api/globalvalidationdata", year=2024).get_json()
        by_zone = {r["ZoneCode"]: r["IntValue"] for r in rows}
        assert by_zone["S1"] == 1500
        assert by_zone["S2"] == 700
        assert by_zone["S3"] == 0
        assert by_zone[""] == 2200

    def test_kpivalue_without_kpicode_is_empty(self, client, scenario, key):
        assert _get(client, key, "/api/kpivalue", year=2024, showunpublished="true").get_json() == []

    def test_kpivalue_returns_both_code_spellings(self, client, scenario, key):
        rows = _get(client, key, "/api/kpivalue", year=2024, kpicode="KPI_PeopleVol").get_json()
        row = next(r for r in rows if r["doncode"] == "DCAA001")
        assert row["DONCode"] == "DCAA001"
        assert row["value"] == 1500


class _FakeUpstream:
    status_code = 200
    ok = True
    headers = {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=x.csv"}

    def iter_content(self, chunk_size=0):
        yield b"a,b\n1,2\n"

    def close(self):
        pass


class TestPassthrough:
    def test_needs_the_legacy_key(self, client, app, scenario, key, monkeypatch):
        monkeypatch.setitem(app.config, "FDRS_DATA_API_KEY", None)
        assert _get(client, key, "/api/embeddedcontent").status_code == 501

    def test_forwards_with_the_server_key(self, client, app, scenario, key, monkeypatch):
        import plugins.fdrs.public_compat_routes as routes

        monkeypatch.setitem(app.config, "FDRS_DATA_API_BASE", "https://legacy.example.org")
        monkeypatch.setitem(app.config, "FDRS_DATA_API_KEY", "server-key")
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return _FakeUpstream()

        monkeypatch.setattr(routes.requests, "request", fake_request)
        response = _get(client, key, "/api/embeddedcontent", type="OCAC")
        assert response.status_code == 200
        assert response.data == b"a,b\n1,2\n"
        assert response.headers["Content-Type"].startswith("text/csv")
        method, url, kwargs = calls[0]
        assert (method, url) == ("GET", "https://legacy.example.org/api/embeddedcontent")
        params = dict(kwargs["params"])
        assert params["apiKey"] == "server-key"
        assert params["type"] == "OCAC"
        assert key not in params.values()
        assert kwargs["allow_redirects"] is False

    def test_refuses_to_call_itself(self, client, app, scenario, key, monkeypatch):
        monkeypatch.setitem(app.config, "FDRS_DATA_API_BASE", "http://localhost")
        monkeypatch.setitem(app.config, "FDRS_DATA_API_KEY", "server-key")
        assert _get(client, key, "/api/embeddedcontent").status_code == 502

    def test_subscribe_posts_json_without_csrf_token(self, client, app, scenario, key, monkeypatch):
        import plugins.fdrs.public_compat_routes as routes

        monkeypatch.setitem(app.config, "FDRS_DATA_API_BASE", "https://legacy.example.org")
        monkeypatch.setitem(app.config, "FDRS_DATA_API_KEY", "server-key")
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(method=method, url=url, json=kwargs["json"])
            return _FakeUpstream()

        monkeypatch.setattr(routes.requests, "request", fake_request)
        response = client.post(
            "/api/documentSubscribe",
            query_string={"apiKey": key},
            json={"email": "a@example.org", "name": "A", "organization": "B"},
        )
        assert response.status_code == 200
        assert seen["method"] == "POST"
        assert seen["json"]["email"] == "a@example.org"

    def test_subscribe_requires_a_key(self, client, scenario):
        assert client.post("/api/documentSubscribe", json={"email": "a@example.org"}).status_code == 401


def _csv_rows(response):
    import csv
    import io

    text = response.data.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


class TestDocuments:
    def test_publications_follow_the_subcategory(self, client, db_session, scenario, key):
        from datetime import date

        from app.models.documents import Resource, ResourceSubcategory, ResourceTranslation

        counts = ResourceSubcategory(name="Everyone Counts", display_order=1)
        analysis = ResourceSubcategory(name="Analysis", display_order=2)
        report = Resource(
            resource_type="publication",
            default_title="Everyone Counts 2024",
            default_description="The report",
            publication_date=date(2024, 6, 1),
            resource_subcategory=counts,
        )
        other = Resource(
            resource_type="publication",
            default_title="Finance analysis",
            publication_date=date(2023, 1, 1),
            resource_subcategory=analysis,
        )
        not_a_publication = Resource(resource_type="resource", default_title="Toolkit")
        db_session.add_all([counts, analysis, report, other, not_a_publication])
        db_session.flush()
        db_session.add(ResourceTranslation(
            resource_id=report.id,
            language_code="en",
            title="Everyone Counts 2024",
            filename="ec2024.pdf",
            file_relative_path="resources/ec2024.pdf",
            thumbnail_relative_path="resources/ec2024.png",
        ))
        db_session.commit()

        payload = _get(client, key, "/api/documents", type="EveryoneCounts", isglobal="true").get_json()
        documents = payload[0]["documents"]
        assert payload[0]["code"] == ""
        assert len(documents) == 1
        assert documents[0]["name"] == "ec2024.pdf"
        assert documents[0]["document_type"] == "EveryoneCounts"
        assert documents[0]["year"] == 2024
        assert documents[0]["LangCode"] == "en"
        assert documents[0]["url"].endswith("/resources/download/%s/en" % report.id)
        assert "Toolkit" not in {row["name"] for row in documents}
        assert _get(client, key, "/api/documents", type="Analysis").get_json()[0]["documents"][0]["title"] == "Finance analysis"

    def test_videos_and_document_guides_keep_their_urls(self, client, db_session, scenario, key):
        from datetime import date

        from app.models.documents import Resource, ResourceSubcategory, ResourceTranslation

        videos = ResourceSubcategory(name="Frontend Video", display_order=3)
        guides = ResourceSubcategory(name="Video Guide", display_order=4)
        documents = ResourceSubcategory(name="Document Guide", display_order=5)
        video = Resource(
            resource_type="publication",
            default_title="FDRS user guide",
            publication_date=date(2021, 1, 1),
            resource_subcategory=videos,
        )
        guide = Resource(
            resource_type="publication",
            default_title="How to add a user",
            publication_date=date(2021, 1, 1),
            resource_subcategory=guides,
        )
        handbook = Resource(
            resource_type="publication",
            default_title="User guide 2021",
            publication_date=date(2021, 1, 1),
            resource_subcategory=documents,
        )
        blocked = Resource(
            resource_type="publication",
            default_title="Blocked video",
            publication_date=date(2021, 1, 1),
            resource_subcategory=videos,
        )
        db_session.add_all([videos, guides, documents, video, guide, handbook, blocked])
        db_session.flush()
        db_session.add_all([
            ResourceTranslation(
                resource_id=video.id,
                language_code="en",
                title="FDRS user guide",
                external_url="https://youtu.be/s8gWS22wpro",
            ),
            ResourceTranslation(
                resource_id=video.id,
                language_code="fr",
                title="Guide FR",
                external_url="https://www.youtube.com/watch?v=abcdef12345",
            ),
            ResourceTranslation(
                resource_id=guide.id,
                language_code="en",
                title="How to add a user",
                external_url="https://youtube.com/watch?v=zzzzzzzzzzz",
            ),
            ResourceTranslation(
                resource_id=handbook.id,
                language_code="en",
                title="User guide 2021",
                filename="guide.pdf",
                file_relative_path="resources/guide.pdf",
            ),
            ResourceTranslation(
                resource_id=blocked.id,
                language_code="en",
                title="Blocked video",
                external_url="https://evil.example/watch",
            ),
        ])
        db_session.commit()

        rows = _get(client, key, "/api/documents", type="FrontendVideo").get_json()[0]["documents"]
        by_title = {row["title"]: row for row in rows}
        assert set(by_title) == {"FDRS user guide", "Guide FR", "How to add a user"}
        assert by_title["FDRS user guide"]["url"] == "https://youtu.be/s8gWS22wpro"
        assert by_title["FDRS user guide"]["document_type"] == "FrontendVideo"
        assert by_title["FDRS user guide"]["LangCode"] == "en"
        assert by_title["Guide FR"]["url"] == "https://www.youtube.com/watch?v=abcdef12345"
        assert by_title["How to add a user"]["document_type"] == "FrontendVideo"
        assert "Blocked video" not in by_title

        guides_payload = _get(client, key, "/api/documents", type="DocumentGuide").get_json()[0]["documents"]
        assert len(guides_payload) == 1
        assert guides_payload[0]["document_type"] == "DocumentGuide"
        assert guides_payload[0]["url"].endswith("/resources/download/%s/en" % handbook.id)

    def test_ns_returns_public_approved_submitted_documents(self, client, db_session, scenario, key):
        from app.models.documents import SubmittedDocument
        from app.models.enums import DocumentStatus
        from tests.factories import create_test_user

        user = create_test_user(db_session)
        country = scenario.country_a
        public = SubmittedDocument(
            filename="annual-report.pdf",
            uploaded_by_user_id=user.id,
            country_id=country.id,
            document_type="Annual Report",
            language="en",
            period="2024",
            is_public=True,
            status=DocumentStatus.APPROVED,
            storage_path="docs/annual-report.pdf",
        )
        hidden = SubmittedDocument(
            filename="draft.pdf",
            uploaded_by_user_id=user.id,
            country_id=country.id,
            is_public=False,
            status=DocumentStatus.APPROVED,
            storage_path="docs/draft.pdf",
        )
        db_session.add_all([public, hidden])
        db_session.commit()

        payload = _get(client, key, "/api/documents", ns="dcaa001").get_json()
        documents = payload[0]["documents"]
        assert payload[0]["code"] == "DCAA001"
        assert [row["name"] for row in documents] == ["annual-report.pdf"]
        assert documents[0]["document_type"] == "Annual Report"
        assert documents[0]["year"] == 2024
        assert documents[0]["Public"] == 1
        assert str(public.public_id) in documents[0]["url"]
        assert _get(client, key, "/api/documents", ns="NOPE").status_code == 404


class TestExport:
    def test_full_export_is_the_published_snapshot(self, client, scenario, key):
        rows = _csv_rows(_get(client, key, "/csv/export"))
        by_key = {(row["KPI_DON_code"], row["year"], row["KPI_code"]): row for row in rows}
        reported = by_key[("DCAA001", "2024", "KPI_PeopleVol")]
        assert reported["Value"] == "1500"
        assert reported["source"] == "reported"
        assert reported["iso_3"] == "CAA"
        assert reported["ZON_Code"] == "S1"
        assert by_key[("DCAA001", "2024", "KPI_PeopleVol_M_age_6_12")]["Value"] == "100"
        assert by_key[("DCAA001", "2024", "KPI_PeopleVol_M")]["Value"] == "405"
        assert by_key[("DCAA001", "2024", "h_gov_CHF")]["Value"] == "50"
        assert by_key[("DCAA001", "2024", "KPI_pr_sex")]["Value"] == "Female"
        assert by_key[("DCAA001", "2024", "supported1")]["Value"] == "DCBB001"
        imputed = by_key[("DCBB001", "2024", "KPI_PeopleVol")]
        assert imputed["Value"] == "700"
        assert imputed["source"] == "imputed"
        assert "KPI_CompatSecret" not in {row["KPI_code"] for row in rows}
        assert _get(client, key, "/csv/export").headers["Content-Disposition"].endswith('filename="fdrs.csv"')

    def test_one_society_export(self, client, scenario, key):
        rows = _csv_rows(_get(client, key, "/csv/exportns", doncode="dcaa001"))
        assert rows
        assert {row["KPI_DON_code"] for row in rows} == {"DCAA001"}
        assert _get(client, key, "/csv/exportns").status_code == 400
        assert _get(client, key, "/csv/exportns", doncode="NOPE").status_code == 404

    def test_excel_is_a_workbook(self, client, scenario, key):
        response = _get(client, key, "/csv/export", excel="1")
        assert response.status_code == 200
        assert response.data[:2] == b"PK"
        assert response.headers["Content-Disposition"].endswith('filename="fdrs.xlsx"')
        assert "spreadsheetml" in response.headers["Content-Type"]


class TestRegistry:
    def test_plugin_lists_the_compat_endpoints(self):
        from plugins.fdrs.plugin import FdrsPlugin

        paths = {ep["path"] for ep in FdrsPlugin().get_api_endpoints()}
        assert {"/api/data", "/api/entities/ns/<don_code>", "/api/KpiImputedValue", "/csv/export"} <= paths

    def test_every_registered_compat_path_is_live_and_documented(self, app):
        from app.routes.admin.api_management import scan_flask_routes

        with app.app_context():
            scan = scan_flask_routes(app)
        live = {r["path"] for r in scan["live"]}
        undocumented = {r["path"] for r in scan["undocumented"]}
        stale = {ep["path"] for ep in scan["stale"]}
        for path in ("/api/data", "/api/entities/ns", "/api/documents", "/csv/export", "/api/documentSubscribe"):
            assert path in live
            assert path not in undocumented
            assert path not in stale


# ---------------------------------------------------------------------------
# Society seeding
# ---------------------------------------------------------------------------

_ENTITY = {
    "KPI_DON_code": "dxx001",
    "NSO_DON_name": "Xland Red Cross",
    "NSO_ZON_name": "Asia Pacific",
    "ZON_Code": "S3",
    "iso_3": "xxl",
    "iso_2": "xl",
    "country": "Xland",
    "lat": "10.5",
    "long": 20,
    "admission_date": "05.03.1999",
    "cur_code": "XLD",
    "Url": "https://xland.example.org",
}


class TestSocietyImport:
    def test_entity_fields_normalise_legacy_values(self):
        fields = entity_fields(_ENTITY)
        assert fields["don_code"] == "DXX001"
        assert (fields["iso3"], fields["iso2"], fields["zone_code"]) == ("XXL", "XL", "S3")
        assert (fields["latitude"], fields["longitude"]) == (10.5, 20.0)
        assert fields["admission_date"].isoformat() == "1999-03-05"
        assert fields["website"] == "https://xland.example.org"

    def test_entity_without_don_code_is_skipped(self):
        assert entity_fields({"NSO_DON_name": "No code"}) is None

    def test_dry_run_writes_nothing(self, db_session):
        stats = upsert_societies([_ENTITY], apply=False)
        assert stats["unlinked"] == ["DXX001"]
        assert stats["created"] == 0
        assert NationalSociety.query.filter_by(fdrs_don_code="DXX001").first() is None

    def test_apply_creates_and_links_by_iso3(self, db_session):
        country = create_test_country(db_session, name="Xland", iso2="XL", iso3="XXL")
        stats = upsert_societies([_ENTITY, {"NSO_DON_name": "skip me"}], apply=True)
        assert (stats["created"], stats["skipped"], stats["unlinked"]) == (1, 1, [])
        society = NationalSociety.query.filter_by(fdrs_don_code="DXX001").one()
        assert society.country_id == country.id
        assert society.fdrs_zone_code == "S3"

    def test_unmatched_country_is_reported(self, db_session):
        stats = upsert_societies([{**_ENTITY, "iso_3": "QQQ", "iso_2": "QQ"}], apply=True)
        assert stats["unlinked"] == ["DXX001"]
        assert NationalSociety.query.filter_by(fdrs_don_code="DXX001").first() is None

    def test_rerun_fills_blanks_but_keeps_backoffice_edits(self, db_session):
        create_test_country(db_session, name="Xland", iso2="XL", iso3="XXL")
        upsert_societies([_ENTITY], apply=True)
        society = NationalSociety.query.filter_by(fdrs_don_code="DXX001").one()
        society.name = "Edited in Backoffice"
        society.website = None
        db_session.commit()

        stats = upsert_societies([_ENTITY], apply=True)
        db_session.refresh(society)
        assert stats["updated"] == 1
        assert society.name == "Edited in Backoffice"
        assert society.website == "https://xland.example.org"

        upsert_societies([_ENTITY], apply=True, overwrite=True)
        db_session.refresh(society)
        assert society.name == "Xland Red Cross"

    def test_unchanged_rerun(self, db_session):
        create_test_country(db_session, name="Xland", iso2="XL", iso3="XXL")
        upsert_societies([_ENTITY], apply=True)
        assert upsert_societies([_ENTITY], apply=True)["unchanged"] == 1
