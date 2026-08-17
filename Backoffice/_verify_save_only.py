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
)

TEMPLATE = r"app/static/templates/unified_country_plan.xlsx"


def xml_cols(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("xl/tables/table11.xml").decode("utf-8")
    return re.findall(r'<tableColumn[^>]*name="([^"]+)"', xml)


def check(label, path):
    wb = openpyxl.load_workbook(path, data_only=True)
    headers, _ = read_named_table(wb, FUNDING_SHEET, FUNDING_TABLE)
    wb.close()
    cols = xml_cols(path)
    mism = [(i, h, c) for i, (h, c) in enumerate(zip(headers, cols)) if h != c]
    print(label, "mismatches:", len(mism))
    for i, h, c in mism[:5]:
        print(f"  @{i}: cell={h!r} xml={c!r}")


with _quiet_openpyxl_io():
    wb = openpyxl.load_workbook(TEMPLATE)
with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
    path = tmp.name
with _quiet_openpyxl_io():
    wb.save(path)
wb.close()
check("save-only", path)
