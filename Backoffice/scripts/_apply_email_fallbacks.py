"""Apply seed HTML as default template fallbacks in service.py and notifications.py."""
import runpy
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SVC = BACKEND / "app" / "services" / "email" / "service.py"
NOTIF = BACKEND / "app" / "routes" / "admin" / "notifications.py"
SEED = BACKEND / "scripts" / "seed_email_templates.py"

ORDER = [
    "email_template_suggestion_confirmation",
    "email_template_admin_notification",
    "email_template_security_alert",
    "email_template_welcome",
]


def _indent_8(s: str) -> str:
    ind = "        "
    return "        default_template = \"\"\"\n" + "\n".join(
        (ind + line) if line else "" for line in s.splitlines()
    ) + "\n        \"\"\""


def _replace_service_block(text: str, get_key: str, html_en: str) -> str:
    marker = f"        html_template = get_email_template('{get_key}', default_template)\n"
    if marker not in text:
        raise SystemExit(f"service.py: missing marker for {get_key!r}")
    i = text.index(marker)
    before = text[:i]
    load_anch = "        # Load template from database with fallback to default"
    p = before.rfind(load_anch)
    if p < 0:
        raise SystemExit(f"service.py: no load anchor before {get_key!r}")
    chunk = before[:p]
    q = chunk.rindex("        \"\"\"\n")
    start = chunk.rindex("        default_template = ", 0, q)
    new_block = _indent_8(html_en) + "\n"
    return text[:start] + new_block + text[p:]


def _notif_block(html_en: str) -> str:
    ind = "            "
    return "            default_email_template = \"\"\"\n" + "\n".join(
        (ind + line) if line else "" for line in html_en.splitlines()
    ) + "\n            \"\"\""


if __name__ == "__main__":
    d = runpy.run_path(str(SEED))
    t: dict = d["DEFAULT_EMAIL_TEMPLATES"]

    st = SVC.read_text(encoding="utf-8")
    for k in ORDER:
        st = _replace_service_block(st, k, t[k]["en"])
    SVC.write_text(st, encoding="utf-8")
    print("updated", SVC)

    new_block = _notif_block(t["email_template_notification"]["en"]) + "\n"
    nt = NOTIF.read_text(encoding="utf-8")
    a = nt.index("            default_email_template = ")
    b = nt.index("            email_template = get_email_template(", a)
    NOTIF.write_text(nt[:a] + new_block + nt[b:], encoding="utf-8")
    print("updated", NOTIF)
