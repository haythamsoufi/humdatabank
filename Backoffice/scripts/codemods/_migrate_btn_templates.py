"""One-off helper: report button-like elements with legacy Tailwind fills."""
import re
import pathlib

root = pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
pat = re.compile(
    r"<(button|a)\b[^>]*class=\"([^\"]{10,600})\"",
    re.I,
)
skip_sub = ("sidebar-item", "hover:bg-gray-700", "chip-", "tab-", "method-option")

for p in sorted(root.rglob("*.html")):
    t = p.read_text(encoding="utf-8", errors="replace")
    for m in pat.finditer(t):
        cls = m.group(2)
        if "text-white" not in cls:
            continue
        if not re.search(r"bg-(blue|green|red|orange|purple|indigo|teal|sky)-[56]00", cls):
            continue
        if any(s in cls for s in skip_sub):
            continue
        rel = p.relative_to(root.parent.parent)
        print(f"{rel}:<{m.group(1)}> {cls[:100]}")
