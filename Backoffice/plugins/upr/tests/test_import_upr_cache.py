"""Unit tests for UPR import row/transform caching helpers."""

import pickle
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
_core_imports = _HERE.parents[3] / "scripts" / "imports"
for _p in (_plugin_scripts, _core_imports):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from import_upr_excel_data import (  # noqa: E402
    ROWS_CACHE_VERSION,
    TRANSFORM_CACHE_VERSION,
    UPR_MASTER_ALLOWED_ROUNDS,
    _file_fingerprint,
    _normalize_round_set,
    _periods_for_import_rounds,
    _transform_cache_key,
    _write_transform_cache,
    is_upr_master_importable_round,
    load_transform_cache,
    load_upr_data_sheet_cached,
    rows_cache_path,
    summarize_workbook_from_rows,
    UprImportContext,
)


class TestSummarizeWorkbookFromRows:
    def test_counts_rounds_sections_and_countries(self):
        rows = [
            {"Round": "P26", "Section": "NS Data", "ISO3": "UGA", "Year": 2026},
            {"Round": "P27", "Section": "NS Data", "ISO3": "UGA", "Year": 2027},
            {"Round": "AR25", "Section": "Funding", "ISO3": "KEN", "Year": 2025},
            {"Round": "AR26", "Section": "Funding", "ISO3": "KEN", "Year": 2026},
            {"Round": "MYR26", "Section": "Core indicators", "ISO3": "UGA", "Year": 2026},
        ]
        summary = summarize_workbook_from_rows(["Round", "Section", "ISO3"], rows)
        assert summary["total_rows"] == 5
        assert summary["countries"] == 2
        assert summary["planning_rounds"] == ["P26", "P27"]
        assert summary["ar_rounds"] == ["AR25", "AR26"]
        assert summary["myr_rounds"] == ["MYR26"]
        assert summary["excluded_rounds"] == ["AR26", "MYR26", "P27"]
        assert "NS Data" in summary["sections"]


class TestNormalizeRoundSet:
    def test_empty_returns_none(self):
        assert _normalize_round_set([]) is None
        assert _normalize_round_set(["", "  "]) is None

    def test_uppercases_and_trims(self):
        assert _normalize_round_set([" p26 ", "ar25"]) == {"P26", "AR25"}


class TestUprMasterAllowedRounds:
    def test_closed_set(self):
        assert UPR_MASTER_ALLOWED_ROUNDS == {
            "P23", "P24", "P25", "P26",
            "AR21", "AR22", "AR23", "AR24", "AR25",
            "MYR23", "MYR24", "MYR25",
        }
        assert is_upr_master_importable_round("P26")
        assert is_upr_master_importable_round("AR25")
        assert is_upr_master_importable_round("MYR25")
        assert not is_upr_master_importable_round("P27")
        assert not is_upr_master_importable_round("AR26")
        assert not is_upr_master_importable_round("MYR26")

    def test_later_selected_rounds_do_not_map_to_periods(self):
        assert _periods_for_import_rounds({"P26", "P27"}) == {"2026"}
        assert _periods_for_import_rounds({"MYR26"}) == set()
        assert _periods_for_import_rounds(None) is None


class TestRowCache:
    def test_loads_cached_rows_without_reparsing_excel(self, tmp_path):
        workbook = tmp_path / "sample.xlsx"
        workbook.write_bytes(b"not-a-real-xlsx")
        fingerprint = _file_fingerprint(str(workbook))
        headers = ["Round", "ISO3"]
        rows = [{"Round": "P26", "ISO3": "UGA"}]
        cache_path = rows_cache_path(str(workbook))
        with open(cache_path, "wb") as fh:
            pickle.dump((fingerprint, headers, rows), fh, protocol=pickle.HIGHEST_PROTOCOL)

        loaded_headers, loaded_rows = load_upr_data_sheet_cached(str(workbook), use_cache=True)
        assert loaded_headers == headers
        assert loaded_rows == rows


class TestTransformCache:
    def test_round_trip_by_template_and_rounds(self, tmp_path):
        workbook = tmp_path / "sample.xlsx"
        workbook.write_bytes(b"workbook")
        template_ids = [24, 22]
        rounds = {"P26"}
        ctx = UprImportContext(template_ids=template_ids, warnings=["warn"])
        import_rows = [{"assignment_entity_status_id": "1", "form_item_id": "2"}]

        _write_transform_cache(str(workbook), template_ids, rounds, import_rows, ctx)
        cache_key = _transform_cache_key(str(workbook), template_ids, rounds)
        assert (tmp_path / f"sample.xlsx.transform.{cache_key}.pkl").is_file()

        loaded_rows, loaded_ctx = load_transform_cache(str(workbook), template_ids, rounds)
        assert loaded_rows == import_rows
        assert loaded_ctx.warnings == ["warn"]

    def test_cache_miss_when_rounds_change(self, tmp_path):
        workbook = tmp_path / "sample.xlsx"
        workbook.write_bytes(b"workbook")
        template_ids = [24]
        ctx = UprImportContext(template_ids=template_ids)
        import_rows = [{"assignment_entity_status_id": "1", "form_item_id": "2"}]
        _write_transform_cache(str(workbook), template_ids, {"P26"}, import_rows, ctx)

        assert load_transform_cache(str(workbook), template_ids, {"P27"}) is None


def test_cache_versions_are_integers():
    assert isinstance(ROWS_CACHE_VERSION, int)
    assert isinstance(TRANSFORM_CACHE_VERSION, int)
