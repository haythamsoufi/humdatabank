"""Unit tests for UPR import row/transform caching helpers."""

import pickle
import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from import_upr_excel_data import (  # noqa: E402
    ROWS_CACHE_VERSION,
    TRANSFORM_CACHE_VERSION,
    _file_fingerprint,
    _normalize_round_set,
    _transform_cache_key,
    _write_transform_cache,
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
            {"Round": "AR25", "Section": "Funding", "ISO3": "KEN", "Year": 2025},
            {"Round": "MYR26", "Section": "Core indicators", "ISO3": "UGA", "Year": 2026},
        ]
        summary = summarize_workbook_from_rows(["Round", "Section", "ISO3"], rows)
        assert summary["total_rows"] == 3
        assert summary["countries"] == 2
        assert summary["planning_rounds"] == ["P26"]
        assert summary["ar_rounds"] == ["AR25"]
        assert summary["myr_rounds"] == ["MYR26"]
        assert "NS Data" in summary["sections"]


class TestNormalizeRoundSet:
    def test_empty_returns_none(self):
        assert _normalize_round_set([]) is None
        assert _normalize_round_set(["", "  "]) is None

    def test_uppercases_and_trims(self):
        assert _normalize_round_set([" p26 ", "ar25"]) == {"P26", "AR25"}


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
