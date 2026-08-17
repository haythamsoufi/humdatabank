import os
import re
import sys
import zipfile

IMPORTS = os.path.join(os.path.dirname(__file__), "scripts", "imports")
if IMPORTS not in sys.path:
    sys.path.insert(0, IMPORTS)

import openpyxl
from unified_country_plan_excel_template import FUNDING_SHEET, FUNDING_TABLE, read_named_table

TEMPLATE = r"app/static/templates/unified_country_plan.xlsx"

with zipfile.ZipFile(TEMPLATE) as z:
    xml = z.read("xl/tables/table11.xml").decode("utf-8")
xml_cols = re.findall(r'<tableColumn[^>]*name="([^"]+)"', xml)

wb = openpyxl.load_workbook(TEMPLATE, data_only=True)
headers, _ = read_named_table(wb, FUNDING_SHEET, FUNDING_TABLE)
wb.close()

print("len headers", len(headers), "len xml", len(xml_cols))
for i, (h, x) in enumerate(zip(headers, xml_cols)):
    if h != x:
        print(f"TEMPLATE mismatch @{i}: cell={h!r} xml={x!r}")
