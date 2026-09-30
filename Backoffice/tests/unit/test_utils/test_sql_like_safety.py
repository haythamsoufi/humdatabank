"""
Unit tests for LIKE/ILIKE safety primitives in ``app/utils/sql_utils.py`` plus a
source-tree scan that fails when a new ``.ilike()`` / ``.like()`` / ``.contains()``
call interpolates a non-constant value without escaping.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import Column, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import declarative_base

from app.utils.sql_utils import (
    contains_literal,
    escape_like_wildcards,
    ilike_contains,
    ilike_equals,
    ilike_prefix,
    like_contains,
    safe_ilike_pattern,
)

BACKOFFICE_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = ("app", "plugins", "scripts")

_Base = declarative_base()


class _Thing(_Base):
    __tablename__ = "thing"
    id = Column(String, primary_key=True)
    name = Column(String)


def _compile(clause):
    compiled = clause.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


@pytest.mark.unit
class TestSqlUtilsPrimitives:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("plain", "plain"),
            ("100%", "100\\%"),
            ("a_b", "a\\_b"),
            ("back\\slash", "back\\\\slash"),
            ("%_\\", "\\%\\_\\\\"),
            (None, ""),
        ],
    )
    def test_escape_like_wildcards(self, raw, expected):
        assert escape_like_wildcards(raw) == expected

    def test_safe_ilike_pattern_variants(self):
        assert safe_ilike_pattern("a%b") == "%a\\%b%"
        assert safe_ilike_pattern("a_b", prefix=False) == "a\\_b%"
        assert safe_ilike_pattern("a_b", prefix=False, suffix=False) == "a\\_b"

    def test_ilike_contains_escapes_and_declares_escape_char(self):
        sql, params = _compile(ilike_contains(_Thing.name, "50%_off"))
        assert "ILIKE" in sql
        assert "ESCAPE '\\\\'" in sql or "ESCAPE '\\'" in sql
        assert list(params.values()) == ["%50\\%\\_off%"]

    def test_ilike_prefix(self):
        _, params = _compile(ilike_prefix(_Thing.name, "a_"))
        assert list(params.values()) == ["a\\_%"]

    def test_ilike_equals(self):
        _, params = _compile(ilike_equals(_Thing.name, "2024_%"))
        assert list(params.values()) == ["2024\\_\\%"]

    def test_like_contains_is_case_sensitive_like(self):
        sql, params = _compile(like_contains(_Thing.name, '"primary": "1_"'))
        assert "LIKE" in sql and "ILIKE" not in sql
        assert list(params.values()) == ['%"primary": "1\\_"%']

    def test_contains_literal_autoescapes(self):
        sql, params = _compile(contains_literal(_Thing.name, "a%b"))
        assert "ESCAPE" in sql
        assert list(params.values()) == ["a/%b"]

    def test_wildcard_only_input_does_not_match_everything(self):
        _, params = _compile(ilike_contains(_Thing.name, "%"))
        assert list(params.values()) == ["%\\%%"]

    def test_period_filter_escapes_wildcards(self):
        from app.services.data_retrieval.aggregation import _period_filter

        _, params = _compile(_period_filter(_Thing.name, ["2024_%"]))
        values = list(params.values())
        assert "2024_%" in values
        assert "%2024\\_\\%%" in values


_LIKE_METHODS = {"ilike", "like", "notilike", "notlike"}
_STR_METHODS = {"contains", "startswith", "endswith"}
_SAFE_FUNCS = {"safe_ilike_pattern", "escape_like_wildcards", "escape_like_pattern"}

# (relative path, unparsed first argument) -> why the value cannot carry user wildcards.
_ALLOWLIST = {
    (
        "app/services/audit/trail_session_query.py",
        "'%.{0}'.format(escape_like_wildcards(suffix))",
    ): "suffix comes from a module constant and is escaped",
}


def _is_column_like(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        base = node.value
        if isinstance(base, ast.Name) and base.id.lstrip("_")[:1].isupper():
            return True
        if isinstance(base, ast.Attribute):
            return _is_column_like(base)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"cast", "as_string", "as_text", "op"}:
            return True
        if isinstance(func, ast.Attribute) and func.attr in {"lower", "upper"}:
            return _is_column_like(func.value)
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in {"func", "db", "sa", "sqlalchemy"}
        ):
            return True
    if isinstance(node, ast.Subscript):
        return _is_column_like(node.value)
    return False


def _collect_env(scope: ast.AST) -> dict[str, list[ast.AST]]:
    env: dict[str, list[ast.AST]] = {}
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    env.setdefault(target.id, []).append(node.value)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            if isinstance(node.target, ast.Name) and node.value is not None:
                env.setdefault(node.target.id, []).append(node.value)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr in {"append", "add"}
                and isinstance(call.func.value, ast.Name)
                and call.args
            ):
                env.setdefault(call.func.value.id, []).append(
                    ast.List(elts=[call.args[0]], ctx=ast.Load())
                )
        elif isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            for gen in node.generators:
                if isinstance(gen.target, ast.Name):
                    env.setdefault(gen.target.id, []).append(
                        ast.Call(func=ast.Name(id="__iter_of__"), args=[gen.iter], keywords=[])
                    )
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            env.setdefault(node.target.id, []).append(
                ast.Call(func=ast.Name(id="__iter_of__"), args=[node.iter], keywords=[])
            )
    return env


def _is_safe(node: ast.AST, env: dict, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_safe(e, env, depth + 1) for e in node.elts)
    if isinstance(node, ast.ListComp):
        return _is_safe(node.elt, env, depth + 1)
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name in _SAFE_FUNCS:
            return True
        if name == "__iter_of__":
            return _is_iterable_safe(node.args[0], env, depth + 1)
        if name in {"list", "sorted", "set", "tuple", "fromkeys"} and node.args:
            return _is_iterable_safe(node.args[0], env, depth + 1)
        if name in {"lower", "upper", "strip", "casefold"} and isinstance(func, ast.Attribute):
            return _is_safe(func.value, env, depth + 1)
        if name in {"format"} and isinstance(func, ast.Attribute):
            return _is_safe(func.value, env, depth + 1) and all(
                _is_safe(a, env, depth + 1) for a in node.args
            )
        return False
    if isinstance(node, ast.JoinedStr):
        return all(
            _is_safe(v.value, env, depth + 1)
            for v in node.values
            if isinstance(v, ast.FormattedValue)
        )
    if isinstance(node, ast.BinOp):
        return _is_safe(node.left, env, depth + 1) and _is_safe(node.right, env, depth + 1)
    if isinstance(node, ast.IfExp):
        return _is_safe(node.body, env, depth + 1) and _is_safe(node.orelse, env, depth + 1)
    if isinstance(node, ast.Name):
        values = env.get(node.id)
        return bool(values) and all(_is_safe(v, env, depth + 1) for v in values)
    return False


def _is_iterable_safe(node: ast.AST, env: dict, depth: int) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name in {"list", "sorted", "set", "tuple", "fromkeys", "dict"} and node.args:
            return _is_iterable_safe(node.args[0], env, depth + 1)
    if isinstance(node, ast.Name):
        values = env.get(node.id)
        return bool(values) and all(_is_safe(v, env, depth + 1) for v in values)
    return _is_safe(node, env, depth + 1)


def scan_source_for_unescaped_like(source: str, rel_path: str) -> list[str]:
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    module_env = _collect_env(tree)
    env_cache: dict[ast.AST, dict] = {}

    def enclosing(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        return tree

    findings = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        method = node.func.attr
        if method in _LIKE_METHODS:
            pass
        elif method in _STR_METHODS and _is_column_like(node.func.value):
            if any(
                kw.arg == "autoescape" and getattr(kw.value, "value", False) is True
                for kw in node.keywords
            ):
                continue
        else:
            continue
        if not node.args:
            continue
        if method in _STR_METHODS and isinstance(node.args[0], (ast.List, ast.Set)):
            continue
        scope = enclosing(node)
        if scope not in env_cache:
            env = dict(module_env) if scope is not tree else {}
            env.update(_collect_env(scope))
            env_cache[scope] = env
        arg = node.args[0]
        if _is_safe(arg, env_cache[scope]):
            continue
        if (rel_path, ast.unparse(arg)) in _ALLOWLIST:
            continue
        findings.append(f"{rel_path}:{node.lineno}: .{method}({ast.unparse(arg)[:100]})")
    return findings


@pytest.mark.unit
class TestLikeScannerSelfCheck:
    @pytest.mark.parametrize(
        "snippet",
        [
            'q.filter(M.c.ilike(f"%{name}%"))',
            'q.filter(M.c.like("%" + term))',
            "q.filter(M.c.ilike(pattern))",
            'q.filter(M.c.contains(search))',
            'q.filter(M.c.startswith(prefix))',
            "def f(x):\n    p = f'%{x}%'\n    return M.c.ilike(p)",
        ],
    )
    def test_scanner_flags_raw_interpolation(self, snippet):
        assert scan_source_for_unescaped_like(snippet, "x.py")

    @pytest.mark.parametrize(
        "snippet",
        [
            'q.filter(M.c.ilike("%constant%"))',
            'q.filter(M.c.ilike(safe_ilike_pattern(x)))',
            'q.filter(M.c.ilike(f"%{escape_like_pattern(x)}%", escape="\\\\"))',
            "def f(x):\n    p = safe_ilike_pattern(x)\n    return M.c.ilike(p)",
            "def f(xs):\n    ps = [safe_ilike_pattern(x) for x in xs]\n    return [M.c.ilike(p) for p in ps]",
            "q.filter(M.c.contains(search, autoescape=True))",
            "q.filter(M.c.contains([tag]))",
            "'abc'.startswith(prefix)",
        ],
    )
    def test_scanner_accepts_escaped_or_constant(self, snippet):
        assert scan_source_for_unescaped_like(snippet, "x.py") == []


@pytest.mark.unit
def test_no_unescaped_like_patterns_in_source_tree():
    findings: list[str] = []
    for root in SCAN_ROOTS:
        for path in sorted((BACKOFFICE_ROOT / root).rglob("*.py")):
            rel = path.relative_to(BACKOFFICE_ROOT).as_posix()
            if "/tests/" in rel or rel.endswith("/conftest.py"):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "like(" not in source and ".contains(" not in source and ".startswith(" not in source and ".endswith(" not in source:
                continue
            try:
                findings.extend(scan_source_for_unescaped_like(source, rel))
            except SyntaxError:
                continue
    assert not findings, (
        "Unescaped LIKE/ILIKE/contains pattern (use app.utils.sql_utils helpers: "
        "ilike_contains, like_contains, safe_ilike_pattern, or contains(..., autoescape=True)):\n"
        + "\n".join(findings)
    )
