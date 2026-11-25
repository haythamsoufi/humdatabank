"""Formatted narrative text for the GO chapters.

A chapter is stored as a small, closed subset of HTML: paragraphs (``<p>``), line breaks, bullet
and numbered lists, and runs with bold, italic, underline, strikethrough, a text colour, a
highlight, and a link. Anything else a person pastes in, or a Word file brings along, is dropped
here, so the same text renders safely in the page and maps one to one onto the Word and PDF
exports. Links may only use http, https, or mailto.

Older drafts and model replies are plain text. Plain text is read as paragraphs split by blank
lines, with ``- `` or ``1. `` lines as lists, so nothing stored earlier needs migrating.

Rendering never trusts the stored string: pages, Word and PDF all walk the parsed nodes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser

# Plain characters allowed in one chapter. GO has no stated limit, so this keeps the report readable.
CHAPTER_LIMIT = 6000

_HTML_START = re.compile(
    r"^\s*<(?:p|ul|ol|div|br|strong|b|em|i|u|s|strike|del|a|span|mark)(?:[\s>/])",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^\s*(?:[-*\u2022\u2013])\s+(.*\S)\s*$")
_NUMBERED = re.compile(r"^\s*\d{1,3}[.)]\s+(.*\S)\s*$")
_SPACES = re.compile(r"[ \t\r\f\v\u00a0]+")

_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "section", "article"}
_BOLD_TAGS = {"strong", "b"}
_ITALIC_TAGS = {"em", "i"}
_UNDERLINE_TAGS = {"u", "ins"}
_STRIKE_TAGS = {"s", "strike", "del"}
_SKIPPED_TAGS = {"script", "style", "head", "title", "template", "noscript"}
_NAMED_COLORS = {
    "black": "000000",
    "white": "ffffff",
    "red": "ff0000",
    "green": "008000",
    "blue": "0000ff",
    "yellow": "ffff00",
    "orange": "ffa500",
    "purple": "800080",
    "gray": "808080",
    "grey": "808080",
    "maroon": "800000",
    "navy": "000080",
    "teal": "008080",
    "lime": "00ff00",
    "aqua": "00ffff",
    "fuchsia": "ff00ff",
    "silver": "c0c0c0",
}
_HEX_COLOR = re.compile(r"^#([0-9a-f]{3}|[0-9a-f]{6})$")
_RGB_COLOR = re.compile(r"^rgba?\((\d{1,3}),(\d{1,3}),(\d{1,3})(?:,[\d.]+)?\)$")


@dataclass(frozen=True)
class Run:
    """A stretch of text with one set of marks. ``text == "\\n"`` is a line break."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    href: str = ""
    color: str = ""
    highlight: str = ""

    @property
    def is_break(self) -> bool:
        return self.text == "\n"

    def marks(self) -> tuple:
        return (self.bold, self.italic, self.underline, self.strike, self.href, self.color, self.highlight)


@dataclass
class Node:
    """A paragraph (``runs``) or a list (``items``, each item a tuple of runs)."""

    type: str
    runs: tuple[Run, ...] = ()
    items: tuple[tuple[Run, ...], ...] = field(default_factory=tuple)

    @property
    def is_list(self) -> bool:
        return self.type in ("ul", "ol")


def looks_like_html(text: str | None) -> bool:
    return bool(text) and bool(_HTML_START.match(str(text)))


def _merge(runs: list[Run]) -> tuple[Run, ...]:
    """Join neighbours that share marks, trim the edges, and drop empty runs."""
    merged: list[Run] = []
    for run in runs:
        if not run.text:
            continue
        if merged and not run.is_break and not merged[-1].is_break and merged[-1].marks() == run.marks():
            merged[-1] = Run(merged[-1].text + run.text, *run.marks())
        else:
            merged.append(run)
    while merged and merged[0].is_break:
        merged.pop(0)
    while merged and merged[-1].is_break:
        merged.pop()
    # Spaces at the edges of the text and next to a line break are layout, not content.
    for index, run in enumerate(merged):
        if run.is_break:
            continue
        text = run.text
        if index == 0 or merged[index - 1].is_break:
            text = text.lstrip(" ")
        if index == len(merged) - 1 or merged[index + 1].is_break:
            text = text.rstrip(" ")
        if text != run.text:
            merged[index] = Run(text, *run.marks())
    return tuple(run for run in merged if run.text)


merge_runs = _merge


def _has_text(runs) -> bool:
    return any(run.text.strip() for run in runs if not run.is_break)


has_text = _has_text


def normalize_color(value: str | None) -> str:
    """``#rrggbb``, or ``""`` when the value is not a plain colour."""
    raw = (value or "").strip().lower()
    if not raw or raw in {"inherit", "transparent", "currentcolor", "auto", "none"}:
        return ""
    named = _NAMED_COLORS.get(raw)
    if named:
        return f"#{named}"
    compact = raw.replace(" ", "")
    rgb = _RGB_COLOR.match(compact)
    if rgb:
        parts = [int(rgb.group(index)) for index in (1, 2, 3)]
        if any(part > 255 for part in parts):
            return ""
        return "#" + "".join(f"{part:02x}" for part in parts)
    match = _HEX_COLOR.match(compact)
    if not match:
        return ""
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(character * 2 for character in digits)
    return f"#{digits}"


def safe_href(value: str | None) -> str:
    """An http, https, or mailto address, or ``""``. Scripts and other schemes are refused."""
    raw = (value or "").strip()
    if not raw or len(raw) > 2000 or any(ord(character) < 32 or character == "\\" for character in raw):
        return ""
    lowered = raw.lower()
    if lowered.startswith(("javascript:", "data:", "vbscript:")):
        return ""
    scheme, _, rest = lowered.partition(":")
    if scheme not in {"http", "https", "mailto"} or not rest:
        return ""
    if scheme == "mailto":
        address = raw.split(":", 1)[1].split("?", 1)[0]
        if not re.fullmatch(r"[^\s@]+@[^\s@]+", address):
            return ""
        return "mailto:" + address
    return raw


def _style_marks(style: str) -> tuple[bool, bool, bool, bool, str, str]:
    declared: dict[str, str] = {}
    for piece in (style or "").split(";"):
        if ":" not in piece:
            continue
        name, value = piece.split(":", 1)
        declared[name.strip().lower()] = value.strip()
    weight = declared.get("font-weight", "").lower()
    bold = weight in {"bold", "700", "800", "900"}
    italic = declared.get("font-style", "").lower() == "italic"
    decoration = f"{declared.get('text-decoration', '')} {declared.get('text-decoration-line', '')}".lower()
    underline = "underline" in decoration
    strike = "line-through" in decoration
    return (
        bold,
        italic,
        underline,
        strike,
        normalize_color(declared.get("color")),
        normalize_color(declared.get("background-color")),
    )


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[Node] = []
        self._runs: list[Run] | None = None
        self._list_type: str | None = None
        self._items: list[tuple[Run, ...]] = []
        self._depth = 0
        self._marks: list[tuple] = []
        self._skip = 0
        self._in_item = False

    def _flags(self) -> tuple:
        bold = italic = underline = strike = False
        href = color = highlight = ""
        for mark in self._marks:
            _tag, mark_bold, mark_italic, mark_underline, mark_strike, mark_href, mark_color, mark_highlight = mark
            bold = bold or mark_bold
            italic = italic or mark_italic
            underline = underline or mark_underline
            strike = strike or mark_strike
            if mark_href:
                href = mark_href
            if mark_color:
                color = mark_color
            if mark_highlight:
                highlight = mark_highlight
        return (bold, italic, underline, strike, href, color, highlight)

    def _open_paragraph(self) -> None:
        if self._runs is None:
            self._runs = []

    def _close_paragraph(self) -> None:
        if self._runs is None:
            return
        runs = _merge(self._runs)
        self._runs = None
        if not _has_text(runs):
            return
        self.nodes.append(Node("p", runs=runs))

    def _close_item(self) -> None:
        if not self._in_item:
            return
        runs = _merge(self._runs or [])
        self._runs = None
        self._in_item = False
        if _has_text(runs):
            self._items.append(runs)

    def _close_list(self) -> None:
        self._close_item()
        if self._list_type and self._items:
            self.nodes.append(Node(self._list_type, items=tuple(self._items)))
        self._list_type = None
        self._items = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        attributes = dict(attrs)
        if tag == "br":
            self._open_paragraph()
            self._runs.append(Run("\n", *self._flags()))
            return
        if tag in ("ul", "ol"):
            if self._list_type is not None:
                self._depth += 1
                return
            self._close_paragraph()
            self._list_type = tag
            self._items = []
            return
        if tag == "li":
            if self._list_type is None:
                self._close_paragraph()
                self._list_type = "ul"
                self._items = []
            self._close_item()
            self._in_item = True
            self._runs = []
            return
        if tag in _BLOCK_TAGS:
            if self._in_item:
                if self._runs and not self._runs[-1].is_break:
                    self._runs.append(Run("\n", *self._flags()))
                return
            self._close_paragraph()
            self._runs = []
            return
        bold = tag in _BOLD_TAGS
        italic = tag in _ITALIC_TAGS
        underline = tag in _UNDERLINE_TAGS
        strike = tag in _STRIKE_TAGS
        href = color = highlight = ""
        if tag in {"span", "font", "mark", "a"}:
            styled_bold, styled_italic, styled_underline, styled_strike, color, highlight = _style_marks(
                attributes.get("style") or ""
            )
            bold = bold or styled_bold
            italic = italic or styled_italic
            underline = underline or styled_underline
            strike = strike or styled_strike
        if tag == "font":
            color = color or normalize_color(attributes.get("color") or "")
        if tag == "mark" and not highlight:
            highlight = "#ffff00"
        if tag == "a":
            href = safe_href(attributes.get("href") or "")
        if tag in _BOLD_TAGS | _ITALIC_TAGS | _UNDERLINE_TAGS | _STRIKE_TAGS | {"span", "font", "a", "mark"}:
            self._marks.append((tag, bold, italic, underline, strike, href, color, highlight))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in ("ul", "ol"):
            if self._depth:
                self._depth -= 1
                return
            self._close_list()
            return
        if tag == "li":
            self._close_item()
            return
        if tag in _BLOCK_TAGS:
            if not self._in_item:
                self._close_paragraph()
            return
        if tag in _BOLD_TAGS | _ITALIC_TAGS | _UNDERLINE_TAGS | _STRIKE_TAGS | {"span", "font", "a", "mark"}:
            for index in range(len(self._marks) - 1, -1, -1):
                if self._marks[index][0] == tag:
                    del self._marks[index]
                    break

    def handle_data(self, data):
        if self._skip or not data:
            return
        text = _SPACES.sub(" ", data.replace("\r", "").replace("\n", " "))
        if self._runs is None:
            if not text.strip():
                return
            if self._list_type is not None:
                return
            self._runs = []
        self._runs.append(Run(text, *self._flags()))

    def finish(self) -> list[Node]:
        self.close()
        if self._list_type is not None:
            self._close_list()
        self._close_paragraph()
        return self.nodes


def parse_html(html: str) -> list[Node]:
    reader = _Reader()
    reader.feed(html or "")
    return reader.finish()


def parse_plain(text: str) -> list[Node]:
    """Paragraphs split by blank lines, with ``- `` and ``1. `` lines as lists."""
    nodes: list[Node] = []
    paragraph: list[str] = []
    items: list[str] = []
    list_type = ""

    def flush_paragraph() -> None:
        nonlocal paragraph
        lines = [line.strip() for line in paragraph if line.strip()]
        paragraph = []
        if not lines:
            return
        runs: list[Run] = []
        for index, line in enumerate(lines):
            if index:
                runs.append(Run("\n"))
            runs.append(Run(_SPACES.sub(" ", line)))
        nodes.append(Node("p", runs=_merge(runs)))

    def flush_list() -> None:
        nonlocal items, list_type
        if items:
            nodes.append(Node(list_type, items=tuple((Run(item),) for item in items)))
        items = []
        list_type = ""

    for raw in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        bullet = _BULLET.match(raw)
        numbered = None if bullet else _NUMBERED.match(raw)
        if bullet or numbered:
            kind = "ul" if bullet else "ol"
            if list_type and list_type != kind:
                flush_list()
            flush_paragraph()
            list_type = kind
            items.append(_SPACES.sub(" ", (bullet or numbered).group(1)))
            continue
        if not raw.strip():
            flush_paragraph()
            flush_list()
            continue
        if items:
            flush_list()
        paragraph.append(raw)
    flush_paragraph()
    flush_list()
    return nodes


def parse(text: str | None) -> list[Node]:
    """Nodes for a stored chapter, whether it is HTML or older plain text."""
    value = str(text or "")
    if not value.strip():
        return []
    return parse_html(value) if looks_like_html(value) else parse_plain(value)


def _run_html(run: Run) -> str:
    if run.is_break:
        return "<br>"
    body = escape(run.text, quote=False)
    if run.bold:
        body = f"<strong>{body}</strong>"
    if run.italic:
        body = f"<em>{body}</em>"
    if run.underline:
        body = f"<u>{body}</u>"
    if run.strike:
        body = f"<s>{body}</s>"
    style = []
    if run.color:
        style.append(f"color:{run.color}")
    if run.highlight:
        style.append(f"background-color:{run.highlight}")
    if style:
        body = f'<span style="{";".join(style)}">{body}</span>'
    if run.href:
        body = (
            f'<a href="{escape(run.href, quote=True)}" target="_blank" rel="noopener noreferrer">{body}</a>'
        )
    return body


def _runs_html(runs) -> str:
    return "".join(_run_html(run) for run in runs)


def nodes_to_html(nodes: list[Node]) -> str:
    parts = []
    for node in nodes:
        if node.is_list:
            items = "".join(f"<li>{_runs_html(item)}</li>" for item in node.items)
            parts.append(f"<{node.type}>{items}</{node.type}>")
        else:
            parts.append(f"<p>{_runs_html(node.runs)}</p>")
    return "".join(parts)


def _plain_length(nodes: list[Node]) -> int:
    return len(nodes_to_plain(nodes))


def _runs_plain(runs) -> str:
    return "".join("\n" if run.is_break else run.text for run in runs)


def nodes_to_plain(nodes: list[Node]) -> str:
    blocks = []
    for node in nodes:
        if node.is_list:
            lines = []
            for index, item in enumerate(node.items, start=1):
                marker = "- " if node.type == "ul" else f"{index}. "
                lines.append(marker + _runs_plain(item).replace("\n", " "))
            blocks.append("\n".join(lines))
        else:
            blocks.append(_runs_plain(node.runs))
    return "\n\n".join(blocks)


def _clip_nodes(nodes: list[Node], limit: int) -> list[Node]:
    if limit <= 0 or _plain_length(nodes) <= limit:
        return nodes
    kept: list[Node] = []
    used = 0
    for node in nodes:
        size = len(nodes_to_plain([node])) + 2
        if used + size <= limit:
            kept.append(node)
            used += size
            continue
        room = limit - used
        if room > 40 and not node.is_list:
            text = _runs_plain(node.runs)[: room - 1].rstrip() + "\u2026"
            kept.append(Node("p", runs=(Run(text),)))
        break
    return kept


def to_html(text: str | None, limit: int = 0) -> str:
    """The canonical stored form: safe HTML limited to the allowed tags. Empty text gives ``""``."""
    nodes = parse(text)
    if limit:
        nodes = _clip_nodes(nodes, limit)
    return nodes_to_html(nodes)


def to_plain(text: str | None) -> str:
    """Text for GO, the language model and counts: paragraphs and ``- `` or ``1. `` list lines."""
    return nodes_to_plain(parse(text))


def plain_length(text: str | None) -> int:
    return len(to_plain(text))


def word_count(text: str | None) -> int:
    """Words in the text. List markers are not words."""
    total = 0
    for node in parse(text):
        for runs in node.items if node.is_list else (node.runs,):
            total += len(re.findall(r"\S+", _runs_plain(runs)))
    return total


def same(left: str | None, right: str | None) -> bool:
    return to_html(left) == to_html(right)


def too_long(text: str | None) -> bool:
    return plain_length(text) > CHAPTER_LIMIT
