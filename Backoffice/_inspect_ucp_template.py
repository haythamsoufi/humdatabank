import re
import zipfile

tpl = r"app/static/templates/unified_country_plan.xlsx"
with zipfile.ZipFile(tpl) as z:
    tables = sorted(n for n in z.namelist() if n.startswith("xl/tables/"))
    print("tables:", tables)
    for i, t in enumerate(tables, 1):
        xml = z.read(t).decode("utf-8", errors="replace")
        name = re.search(r'name="([^"]+)"', xml)
        ref = re.search(r'ref="([^"]+)"', xml)
        cols = re.findall(r'<tableColumn[^>]*name="([^"]+)"', xml)
        print(f"  table{i}: file={t} name={name.group(1) if name else '?'} ref={ref.group(1) if ref else '?'}")
        if "Data_FR" in (name.group(1) if name else ""):
            print("    funding cols sample:", cols[:5], "...", cols[-3:])
    print("drawings:", [n for n in z.namelist() if "drawing" in n.lower()])
