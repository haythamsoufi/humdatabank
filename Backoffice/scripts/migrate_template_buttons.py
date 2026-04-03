#!/usr/bin/env python3
"""
Normalize legacy Tailwind-filled <button> and <a> actions to the unified .btn system.

Run from Backoffice/:  python scripts/migrate_template_buttons.py
Dry-run:               python scripts/migrate_template_buttons.py --dry-run

Skips: sidebar/nav, chat-*, language-selector, alert-close, tab list buttons,
       elements with rounded-full FAB sizing (w-12 h-12 rounded-full etc.).
"""
from __future__ import annotations

import argparse
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"

# Tailwind utilities to remove when converting a filled action control.
STRIP_TOKENS = [
    "inline-flex",
    "flex",
    "items-center",
    "justify-center",
    "justify-between",
    "min-w-[200px]",
    "border",
    "border-transparent",
    "border-blue-600",
    "border-gray-300",
    "shadow-sm",
    "shadow",
    "shadow-lg",
    "text-xs",
    "text-sm",
    "text-base",
    "text-white",
    "font-medium",
    "font-semibold",
    "font-bold",
    "uppercase",
    "tracking-wide",
    "transition",
    "transition-colors",
    "transition-all",
    "duration-150",
    "duration-200",
    "duration-300",
    "ease-in-out",
    "ease-out",
    "focus:outline-none",
    "focus:ring-2",
    "focus:ring-4",
    "focus:ring-offset-2",
    "focus:ring-blue-500",
    "focus:ring-blue-600",
    "focus:ring-green-500",
    "focus:ring-orange-500",
    "focus:ring-purple-500",
    "focus:ring-red-500",
    "focus:ring-indigo-500",
    "focus:ring-yellow-500",
    "focus:ring-gray-500",
    "disabled:opacity-50",
    "disabled:cursor-not-allowed",
    "disabled:pointer-events-none",
    "cursor-pointer",
    "select-none",
    "no-underline",
    "whitespace-nowrap",
    "rounded",
    "rounded-md",
    "rounded-lg",
    "rounded-full",
    "rounded-l-md",
    "rounded-r-md",
    "rounded-t-lg",
    "rounded-b-lg",
    "gap-1",
    "gap-2",
    "gap-3",
    "space-x-2",
    "space-x-3",
    # spacing (common button paddings)
    "px-2",
    "px-2.5",
    "px-3",
    "px-3.5",
    "px-4",
    "px-5",
    "px-6",
    "py-0.5",
    "py-1",
    "py-1.5",
    "py-2",
    "py-2.5",
    "py-3",
    "py-4",
    "mt-2",
    "mt-3",
    "mt-4",
    "mb-2",
    "ml-3",
    "mr-2",
    "sm:inline",
    "sm:flex",
    "sm:hidden",
    "xl:flex",
    "xl:hidden",
    "relative",
    "absolute",
    "fixed",
    "z-40",
    "z-50",
    "bottom-6",
    "left-6",
    "top-6",
    "right-3",
    "top-3",
    "w-12",
    "w-14",
    "h-12",
    "h-14",
    "active:bg-purple-800",
    "active:scale-95",
    "hover:scale-105",
]

# bg + hover pairs → btn variant (first match wins)
COLOR_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbg-red-[567]00\b"), "btn-danger"),
    (re.compile(r"\bbg-green-[567]00\b"), "btn-success"),
    (re.compile(r"\bbg-orange-[567]00\b"), "btn-warning"),
    (re.compile(r"\bbg-purple-[567]00\b"), "btn-purple"),
    (re.compile(r"\bbg-indigo-[567]00\b"), "btn-primary"),
    (re.compile(r"\bbg-teal-[567]00\b"), "btn-primary"),
    (re.compile(r"\bbg-sky-[567]00\b"), "btn-primary"),
    (re.compile(r"\bbg-blue-[567]00\b"), "btn-primary"),
    (re.compile(r"\bbg-gray-[567]00\b"), "btn-dark"),
    (re.compile(r"\bbg-yellow-[567]00\b"), "btn-warning"),
    (re.compile(r"\bbg-amber-[567]00\b"), "btn-warning"),
]

HOVER_BG = re.compile(
    r"\bhover:bg-(?:blue|green|red|orange|purple|indigo|teal|sky|gray|yellow|amber)-[567]00\b"
)
FOCUS_RING = re.compile(r"\bfocus:ring-(?:blue|green|red|orange|purple|indigo|teal|sky|gray|yellow|amber)-[567]00\b")
OTHER_BG = re.compile(r"\b(?:hover|focus|active):bg-[a-z0-9-]+\b")
PLAIN_BG = re.compile(r"\bbg-[a-z0-9-]+\b")

SKIP_SUBSTR = (
    "sidebar-item",
    "chat-",
    "language-selector",
    "alert-close",
    "nav-menu",
    "select2-",
    "method-option",
    "imputation-method-btn",
    "user-analytics-period-btn",
    "tab-panel",
    "chip-remove",
    "insert-variable-btn",
    "fullscreen-btn",
    "exit-fullscreen",
    "fab-tooltip",
    "pagination",
    "page-link",
    "rounded-full",  # FAB / bell — keep as-is when paired with circular dimensions
    "copy-url-btn",  # may get btn via conversion
)

TOKEN_RE = re.compile(r"\S+")


def _detect_variant(classes: str) -> str | None:
    for pat, variant in COLOR_RULES:
        if pat.search(classes):
            return variant
    return None


def _strip_utilities(classes: str) -> str:
    parts = TOKEN_RE.findall(classes)
    out: list[str] = []
    for p in parts:
        if p in STRIP_TOKENS:
            continue
        if HOVER_BG.match(p) or p.startswith("hover:") and "bg-" in p:
            continue
        if FOCUS_RING.match(p) or (p.startswith("focus:") and "ring-" in p):
            continue
        if OTHER_BG.match(p) and p != p.strip():
            continue
        if p.startswith("focus:ring-offset-"):
            continue
        # drop remaining hover:/focus: text-color utilities
        if p.startswith("hover:text-") or p.startswith("focus:text-"):
            continue
        out.append(p)
    return " ".join(out).strip()


def _normalize_class(classes: str) -> str | None:
    raw = classes.strip()
    if not raw:
        return None
    if re.search(r"\bbtn btn-(primary|success|danger|secondary|warning|purple|dark|ghost|ghost-danger)\b", raw):
        return None
    if "professional-action-btn" in raw or "btn-login-oauth" in raw:
        return None
    if any(s in raw for s in SKIP_SUBSTR):
        return None
    # Keep circular FAB / mobile FAB (rounded-full + explicit square size)
    if "rounded-full" in raw and re.search(r"\b(w|h)-(10|11|12|14|16)\b", raw):
        return None
    if "text-white" not in raw:
        return None
    variant = _detect_variant(raw)
    if not variant:
        return None
    # Must look like a filled control (had a solid bg-*-600)
    rest = _strip_utilities(raw)
    # Remove plain bg/hover bg tokens left
    rest_parts = []
    for p in TOKEN_RE.findall(rest):
        if PLAIN_BG.match(p):
            continue
        if p.startswith("hover:") or p.startswith("focus:") or p.startswith("active:"):
            continue
        rest_parts.append(p)
    rest = " ".join(rest_parts).strip()
    # Size hint
    size = ""
    if "text-xs" in classes or "py-1 " in classes + " " or classes.endswith("py-1") or " px-2 " in f" {classes} ":
        if "btn-sm" not in rest and "py-3" not in classes:
            size = " btn-sm"
    if "px-6 py-3" in classes or "py-3 px-4" in classes:
        size = ""  # default btn is fine
    merged = f"btn {variant}{size} {rest}".strip()
    merged = re.sub(r"\s+", " ", merged)
    return merged


TAG_CLASS_RE = re.compile(
    r"<(button|a)\b([^>]*?)\sclass=([\"'])([^\"']*)\3",
    re.IGNORECASE | re.DOTALL,
)


def migrate_html(text: str) -> tuple[str, int]:
    changes = 0

    def repl(m: re.Match) -> str:
        nonlocal changes
        tag, mid, quote, cls = m.group(1), m.group(2), m.group(3), m.group(4)
        if "sidebar-item" in cls or "chat-" in cls:
            return m.group(0)
        new_cls = _normalize_class(cls)
        if not new_cls or new_cls == cls.strip():
            return m.group(0)
        changes += 1
        return f"<{tag}{mid} class={quote}{new_cls}{quote}"

    out = TAG_CLASS_RE.sub(repl, text)
    return out, changes


def migrate_file(path: pathlib.Path, dry: bool) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = migrate_html(text)
    if n and new_text != text and not dry:
        path.write_text(new_text, encoding="utf-8", newline="\n")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = 0
    touched = 0
    for p in sorted(ROOT.rglob("*.html")):
        n = migrate_file(p, args.dry_run)
        if n:
            touched += 1
            total += n
            print(f"{'[dry] ' if args.dry_run else ''}{p.relative_to(ROOT)}: {n} class attr(s)")
    print(f"Done. Files touched: {touched}, class attrs updated: {total}")


if __name__ == "__main__":
    main()
