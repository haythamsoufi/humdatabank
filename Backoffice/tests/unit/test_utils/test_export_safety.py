import csv
import io

import pytest

from app.utils.export_safety import (
    safe_csv_dict_writer,
    safe_csv_writer,
    sanitize_dataframe,
    sanitize_spreadsheet_cell,
    sanitize_spreadsheet_row,
    sanitize_workbook,
)


@pytest.mark.parametrize(
    "payload",
    ["=1+1", "+SUM(A1)", "-2+3", "@cmd", "\t=1", "\r=1", " =HYPERLINK(\"x\")", "\u200b=1", "\u00a0+1"],
)
def test_formula_triggers_are_neutralised(payload):
    assert sanitize_spreadsheet_cell(payload) == "'" + payload


@pytest.mark.parametrize("value", ["hello", "", "a=b", "1-2", "Kenya", None, 5, -5, 3.5, True])
def test_safe_values_untouched(value):
    assert sanitize_spreadsheet_cell(value) == value


def test_row_sanitiser_keeps_numbers():
    assert sanitize_spreadsheet_row(["=x", -1, "ok"]) == ["'=x", -1, "ok"]


def test_safe_csv_writer_prefixes_dangerous_cells():
    buf = io.StringIO()
    w = safe_csv_writer(buf)
    w.writerow(["name", "=cmd|' /C calc'!A0"])
    w.writerows([["+1", "fine"]])
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert rows[0][1].startswith("'=")
    assert rows[1][0] == "'+1"
    assert rows[1][1] == "fine"


def test_safe_csv_dict_writer():
    buf = io.StringIO()
    w = safe_csv_dict_writer(buf, ["a", "b"])
    w.writeheader()
    w.writerow({"a": "@evil", "b": 3})
    lines = buf.getvalue().splitlines()
    assert lines[1].startswith("'@evil")


def test_sanitize_workbook_neutralises_openpyxl_cells():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "=1+1"
    ws["A2"] = "safe"
    ws["A3"] = 7
    ws2 = wb.create_sheet("second")
    ws2["B2"] = "-cmd"
    sanitize_workbook(wb)
    assert ws["A1"].value == "'=1+1"
    assert ws["A1"].data_type == "s"
    assert ws["A2"].value == "safe"
    assert ws["A3"].value == 7
    assert ws2["B2"].value == "'-cmd"


def test_sanitize_dataframe_only_touches_text_columns():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"t": ["=1", "ok"], "n": [-1, 2]})
    out = sanitize_dataframe(df)
    assert list(out["t"]) == ["'=1", "ok"]
    assert list(out["n"]) == [-1, 2]
    assert list(df["t"]) == ["=1", "ok"]
