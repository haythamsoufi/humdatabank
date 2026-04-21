"""Scan Jinja HTML templates for <button> tags that omit .btn (dev helper)."""
import re
import pathlib

root = pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
missing = []
for p in sorted(root.rglob("*.html")):
    text = p.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"<button\b[^>]*>", text, re.I):
        tag = m.group(0)
        # .btn*, page-header actions, entry-form FABs — all part of the design system
        if "btn" in tag or "professional-action-btn" in tag or "fab-tooltip" in tag:
            continue
        if "chat-" in tag or "fullscreen-btn" in tag:
            continue
        if "tab-main" in tag or 'role="tab"' in tag:
            continue
        if "confirm_class" in tag:
            continue
        if "language-selector-button" in tag:
            continue
        missing.append((str(p.relative_to(root.parent)), tag[:220]))

print(f"Buttons without .btn: {len(missing)}")
from collections import Counter

c = Counter(x[0] for x in missing)
for f, n in c.most_common(80):
    print(f"{n:4} {f}")
