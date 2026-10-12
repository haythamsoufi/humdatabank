"""Guard: server-rendered matrix inputs must opt out of browser form restore.

Firefox (and Chrome on soft reload / back-forward) can put a previously typed value
back into an input after the server rendered a fresh one. For matrices that made an
old auto-filled value override the saved state, so every server-rendered cell and the
hidden JSON payload carry ``autocomplete="off"``.
"""
import re
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "app" / "templates" / "forms" / "entry_form" / "partials" / "matrix_table.html"
)


def _input_tags(source: str):
    return re.findall(r"<input\b[^>]*>", source, flags=re.DOTALL)


def test_cell_inputs_disable_browser_form_restore():
    tags = [t for t in _input_tags(TEMPLATE.read_text(encoding="utf-8")) if "data-cell-key=" in t]
    assert len(tags) >= 6, "expected the matrix cell input variants to be present"
    missing = [t for t in tags if 'autocomplete="off"' not in t]
    assert not missing, f"matrix cell inputs without autocomplete=off: {missing}"


def test_hidden_matrix_payload_disables_browser_form_restore():
    tags = [
        t for t in _input_tags(TEMPLATE.read_text(encoding="utf-8"))
        if 'id="matrix-data-{{ field.id }}"' in t
    ]
    assert len(tags) == 1
    assert 'autocomplete="off"' in tags[0]
