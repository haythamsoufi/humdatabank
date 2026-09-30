"""Guard: broad ``except Exception`` handlers must not echo the exception into JSON responses."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_RESPONSE = re.compile(
    r"(json_server_error|json_bad_request|api_error|jsonify|json_response|json_error)\("
    r".*(str\((e|exc|err|ex|error)\)|\{(e|exc|err|ex|error)\})"
)
_BROAD_EXCEPT = re.compile(r"\s*except\s+(Exception|BaseException)\b")
_ANY_EXCEPT = re.compile(r"\s*except\b(.*):")
_ALLOWLIST: set[str] = set()


def _offenders():
    found = []
    for base in ("app", "plugins"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or rel in _ALLOWLIST or rel == "app/utils/api_errors.py":
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for idx, line in enumerate(lines):
                if not _RESPONSE.search(line) or line.lstrip().startswith(("#", '"""', "``")):
                    continue
                j = idx
                while j >= 0 and idx - j < 30 and not _ANY_EXCEPT.match(lines[j]):
                    j -= 1
                if j >= 0 and idx - j < 30 and _BROAD_EXCEPT.match(lines[j]):
                    if any("isinstance(" in prev for prev in lines[max(j, idx - 4):idx]):
                        continue
                    found.append(f"{rel}:{idx + 1}")
    return found


def test_no_exception_text_in_json_responses_from_broad_handlers():
    offenders = _offenders()
    assert not offenders, (
        "Use handle_json_view_exception(e, GENERIC_ERROR_MESSAGE) instead of echoing exceptions: "
        + ", ".join(offenders)
    )
