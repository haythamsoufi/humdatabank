"""AppealsD365 API probe behaviour — fixture-backed unit tests + optional live smoke."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

import pytest

from plugins.emergency_operations.appeals_d365 import (
    appeal_matches_country_iso,
    classify_gec_tokens,
    is_emergency_appeal_code,
    normalize_appeal_record,
    parse_gec_code,
)

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "fixtures", "appeals_d365_per_code.json"
)


@pytest.fixture(scope="module")
def d365_fixture() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def per_code(d365_fixture) -> dict:
    return d365_fixture["per_code"]


class TestParseGecCode:
    def test_multi_country_semicolon(self):
        assert parse_gec_code("CD;UG") == ["CD", "UG"]

    def test_single_country(self):
        assert parse_gec_code("JM") == ["JM"]

    def test_empty(self):
        assert parse_gec_code("") == []
        assert parse_gec_code(None) == []


class TestAppealMatchesCountryIso:
    def test_jamaica_single_country_appeal(self, per_code):
        assert appeal_matches_country_iso(per_code["MDRJM005"], "JM") is True
        assert appeal_matches_country_iso(per_code["MDRJM005"], "JAM") is True
        assert appeal_matches_country_iso(per_code["MDRJM005"], "TT") is False

    def test_grouped_appeal_country_tokens(self, per_code):
        assert appeal_matches_country_iso(per_code["MDRS1007"], "CD") is True
        assert appeal_matches_country_iso(per_code["MDRS1007"], "UG") is True
        assert appeal_matches_country_iso(per_code["MDRS1007"], "COD") is True

    def test_regional_gec_does_not_match_country_iso_without_mapping(self, per_code):
        # Live API returns region cluster codes for some grouped appeals.
        assert parse_gec_code(per_code["MDRS2001"]["GEC_code"]) == ["CAR"]
        assert appeal_matches_country_iso(per_code["MDRS2001"], "JM") is False
        assert appeal_matches_country_iso(per_code["MDRS2001"], "TT") is False

        assert parse_gec_code(per_code["MGR65002"]["GEC_code"]) == ["EUR"]
        assert appeal_matches_country_iso(per_code["MGR65002"], "UA") is False
        assert appeal_matches_country_iso(per_code["MGR65002"], "UKR") is False


class TestClassifyGecTokens:
    def test_mixed_country_and_region(self):
        out = classify_gec_tokens(["CD", "UG", "CAR", "EUR"])
        assert out["countries"] == ["CD", "UG"]
        assert "CAR" in out["regions"]
        assert "EUR" in out["regions"]


class TestNormalizeAppealRecord:
    def test_mdr_record_shape(self, per_code):
        norm = normalize_appeal_record(per_code["MDRMM023"])
        assert norm["code"] == "MDRMM023"
        assert norm["name"] == "Myanmar - Earthquake"
        assert norm["label"] == "Myanmar - Earthquake (MDRMM023)"
        assert norm["source"] == "D365 Bronze"
        assert norm["gec_tokens"] == ["MM"]
        assert norm["disaster_name"] == "Red"
        assert norm["details_count"] >= 1

    def test_grouped_source_flag(self, per_code):
        norm = normalize_appeal_record(per_code["MGR65002"])
        assert norm["source"] == "D365 Bronze (G)"


class TestEmergencyCodePattern:
    @pytest.mark.parametrize(
        "code,expected",
        [
            ("MDRS2001", True),
            ("MGR65002", True),
            ("M000", False),
            ("MDRNG045", True),
        ],
    )
    def test_code_patterns(self, code, expected):
        assert is_emergency_appeal_code(code) is expected


class TestLiveAppealsD365ProbeMetadata:
    """Documents live probe results stored in the fixture (Aug 2026)."""

    def test_bulk_endpoint_not_a_catalogue(self, d365_fixture):
        assert "bulk_list_note" in d365_fixture
        json_probe = next(p for p in d365_fixture["probes"] if p.get("accept") == "application/json")
        assert json_probe["bytes"] > 1_000_000
        assert json_probe["record_count"] == 1

    def test_per_code_fixture_has_focus_codes(self, per_code):
        assert set(per_code) >= {
            "MDRS2001",
            "MDRS1007",
            "MGR65002",
            "MDRMM023",
            "MDRJM005",
            "MDRNG045",
        }

    def test_grouped_appeal_has_multi_detail_phases(self, per_code):
        mgr = per_code["MGR65002"]
        assert mgr["source"] == "D365 Bronze (G)"
        assert len(mgr["Details"]) >= 5


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_APPEALS_D365_LIVE") != "1",
    reason="Set RUN_APPEALS_D365_LIVE=1 with valid GO API basic-auth creds",
)
class TestAppealsD365LiveSmoke:
    """Optional live checks — off by default (API rate-limits / 403)."""

    @staticmethod
    def _auth_header() -> dict:
        import base64
        import os

        basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        env_path = os.path.join(basedir, ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        user = (os.environ.get("IFRC_API_USER") or os.environ.get("IFRC_API_USERNAME") or "").strip()
        pwd = (os.environ.get("IFRC_API_PASSWORD") or "").strip()
        if not user or not pwd:
            pytest.skip("IFRC_API_USER / IFRC_API_PASSWORD not configured in Backoffice/.env")
        token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "User-Agent": "IFRC-Network-Databank/1.0",
        }

    def test_per_code_lookup_returns_json(self):
        url = "https://go-api.ifrc.org/api/AppealsD365?APP_code=MDRJM005"
        req = urllib.request.Request(url, headers=self._auth_header())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            pytest.skip(f"Live API unavailable: HTTP {exc.code}")
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["APP_code"] == "MDRJM005"
        assert data[0]["GEC_code"] == "JM"

    def test_bulk_endpoint_returns_single_m000_row(self):
        url = "https://go-api.ifrc.org/api/AppealsD365"
        req = urllib.request.Request(url, headers=self._auth_header())
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            pytest.skip(f"Live API unavailable: HTTP {exc.code}")
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["APP_code"] == "M000"
