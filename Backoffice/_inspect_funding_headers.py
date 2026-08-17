import os
import sys

IMPORTS = os.path.join(os.path.dirname(__file__), "scripts", "imports")
if IMPORTS not in sys.path:
    sys.path.insert(0, IMPORTS)

import openpyxl
from unified_country_plan_excel_template import (
    FUNDING_AREAS_PER_YEAR,
    FUNDING_SHEET,
    FUNDING_TABLE,
    parse_funding_column_header,
    read_named_table,
)

TEMPLATE = r"app/static/templates/unified_country_plan.xlsx"
wb = openpyxl.load_workbook(TEMPLATE, data_only=True)
headers, _ = read_named_table(wb, FUNDING_SHEET, FUNDING_TABLE)
wb.close()

funding = [h for h in headers if parse_funding_column_header(h)]
print("FUNDING_AREAS_PER_YEAR len", len(FUNDING_AREAS_PER_YEAR), FUNDING_AREAS_PER_YEAR)
print("funding header count", len(funding))
print("all headers:", headers)
print("funding headers:")
for i, h in enumerate(funding):
    parsed = parse_funding_column_header(h)
    print(f"  {i:2d}: {h} -> {parsed}")
