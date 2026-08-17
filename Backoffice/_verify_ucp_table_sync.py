"""Verify UCP export does not desync Excel table column metadata."""
import os
import re
import sys
import tempfile
import zipfile

IMPORTS = os.path.join(os.path.dirname(__file__), "scripts", "imports")
if IMPORTS not in sys.path:
    sys.path.insert(0, IMPORTS)

import openpyxl

from unified_country_plan_excel_template import (
    FUNDING_SHEET,
    FUNDING_TABLE,
    _quiet_openpyxl_io,
    read_named_table,
    rewrite_planning_year_headers,
)

TEMPLATE = r"app/static/templates/unified_country_plan.xlsx"


def table_column_names_from_xml(xlsx_path: str, table_file: str = "xl/tables/table11.xml"):
    with zipfile.ZipFile(xlsx_path) as z:
        xml = z.read(table_file).decode("utf-8")
    return re.findall(r'<tableColumn[^>]*name="([^"]+)"', xml)


with _quiet_openpyxl_io():
    wb = openpyxl.load_workbook(TEMPLATE)
rewrite_planning_year_headers(wb, "2027")
with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
    path = tmp.name
with _quiet_openpyxl_io():
    wb.save(path)
wb.close()

headers, _ = read_named_table(openpyxl.load_workbook(path, data_only=True), FUNDING_SHEET, FUNDING_TABLE)
xml_cols = table_column_names_from_xml(path)
funding_headers = [h for h in headers if h and h != "NS" and "_" in h]
xml_funding = [c for c in xml_cols if c != "NS" and "_" in c]
print("cell headers sample:", funding_headers[:3], funding_headers[-3:])
print("xml cols sample:", xml_funding[:3], xml_funding[-3:])
print("MISMATCH:", funding_headers != xml_funding)
if funding_headers != xml_funding:
    for i, (a, b) in enumerate(zip(funding_headers, xml_funding)):
        if a != b:
            print(f"  diff@{i}: cell={a!r} xml={b!r}")
