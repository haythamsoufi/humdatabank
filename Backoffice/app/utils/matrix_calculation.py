"""Per-row matrix formulas.

Calculated columns use one formula language in the form, the PDF, and the API.
Presets (sum, average, difference, percentage, and so on) compile to that
formula so there is a single evaluator.

Blank number cells stay blank. Tick cells are always 0 or 1. SUM, AVERAGE, MIN,
MAX, and COUNT skip blanks. Arithmetic treats blanks as zero unless the column
sets ``blank_as_zero`` to false. Division by zero and circular references
produce a blank result with an error message. IF short-circuits, matching
spreadsheet tools.
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

Number = float
Value = Union[float, object]

OPERATIONS = (
    'sum',
    'average',
    'min',
    'max',
    'count',
    'count_filled',
    'difference',
    'percentage',
    'product',
    'formula',
)

_BLANK = object()


class FormulaError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class FormulaResult:
    def __init__(self, value: Optional[float], error: Optional[str] = None):
        self.value = value
        self.error = error


def calculation_is_readonly(column: Any) -> bool:
    """Calculated cells are display-only unless the author turns read-only off."""
    if not isinstance(column, dict) or column.get('type') != 'calculated':
        return True
    return column.get('calculation_readonly') is not False


def calculation_saves_value(column: Any) -> bool:
    """Missing flag means the result is recalculated and not stored."""
    return (
        isinstance(column, dict)
        and column.get('type') == 'calculated'
        and column.get('calculation_save_value') is True
    )


def stored_calculation_value(column: Any, matrix_data: Optional[Mapping[str, Any]], row_id: Any):
    """Saved cell for a calculated column that persists its value, or None."""
    if not calculation_saves_value(column):
        return None
    name = column.get('name')
    if not name:
        return None
    number = cell_formula_input((matrix_data or {}).get(f'{row_id}_{name}'), 'number')
    if number is _BLANK:
        return None
    return float(number)


def column_counts_toward_row_total(column: Any) -> bool:
    """Data columns count unless explicitly excluded. Calculated columns do not, unless opted in."""
    if not isinstance(column, dict):
        return True
    if column.get('type') == 'calculated':
        return column.get('include_in_row_total') is True
    return column.get('include_in_row_total') is not False


def _clean_names(raw: Any) -> List[str]:
    names: List[str] = []
    if not isinstance(raw, list):
        return names
    for item in raw:
        if isinstance(item, str) and item.strip():
            names.append(item.strip()[:200])
    return names


def _column_ref(name: str) -> str:
    """A code with no spaces is written bare. Braces stay available for older formulas."""
    if _IDENT.fullmatch(name or ''):
        return name
    return '{' + (name or '').replace('}', '') + '}'


def _ref_list(names: Sequence[str]) -> str:
    return ', '.join(_column_ref(name) for name in names)


def _sum_expr(names: Sequence[str]) -> str:
    if not names:
        return '0'
    return f'SUM({_ref_list(names)})'


def compile_calculation(calculation: Optional[Mapping[str, Any]]) -> str:
    """Compile a preset to a formula. Custom formulas are returned unchanged."""
    calc = calculation if isinstance(calculation, Mapping) else {}
    operation = str(calc.get('operation') or 'formula').strip().lower()
    sources = _clean_names(calc.get('sources'))
    subtrahends = _clean_names(calc.get('subtrahends'))
    denominators = _clean_names(calc.get('denominators'))
    if operation == 'formula':
        return str(calc.get('formula') or '').strip()
    if operation == 'sum':
        return _sum_expr(sources)
    if operation == 'average':
        return f'AVERAGE({_ref_list(sources)})' if sources else ''
    if operation == 'min':
        return f'MIN({_ref_list(sources)})' if sources else ''
    if operation == 'max':
        return f'MAX({_ref_list(sources)})' if sources else ''
    if operation == 'count':
        return f'COUNT({_ref_list(sources)})' if sources else '0'
    if operation == 'count_filled':
        return f'COUNTA({_ref_list(sources)})' if sources else '0'
    if operation == 'difference':
        return f'{_sum_expr(sources)} - {_sum_expr(subtrahends)}'
    if operation == 'percentage':
        numerator = _sum_expr(sources)
        denominator = _sum_expr(denominators)
        return f'IF({denominator} = 0, BLANK(), {numerator} / {denominator} * 100)'
    if operation == 'product':
        if not sources:
            return ''
        if len(sources) == 1:
            return _column_ref(sources[0])
        return ' * '.join(_column_ref(name) for name in sources)
    return str(calc.get('formula') or '').strip()


def normalize_calculation(raw: Any) -> Optional[Dict[str, Any]]:
    """Return a stored calculation object, or None when nothing usable was provided."""
    if not isinstance(raw, dict):
        return None
    operation = str(raw.get('operation') or 'formula').strip().lower()
    if operation not in OPERATIONS:
        operation = 'formula'
    decimals = raw.get('decimals')
    try:
        decimals_int = int(decimals) if decimals is not None and decimals != '' else None
    except (TypeError, ValueError):
        decimals_int = None
    if decimals_int is None:
        decimals_int = 0 if operation in ('sum', 'min', 'max', 'count', 'count_filled') else 2
    decimals_int = max(0, min(6, decimals_int))
    blank_as_zero = True if raw.get('blank_as_zero') is None else bool(raw.get('blank_as_zero'))
    calc: Dict[str, Any] = {
        'operation': operation,
        'sources': _clean_names(raw.get('sources')),
        'subtrahends': _clean_names(raw.get('subtrahends')),
        'denominators': _clean_names(raw.get('denominators')),
        'decimals': decimals_int,
        'blank_as_zero': blank_as_zero,
    }
    if operation == 'formula':
        calc['formula'] = str(raw.get('formula') or '').strip()[:2000]
    else:
        calc['formula'] = compile_calculation(calc)
    if operation != 'formula' and not calc['formula']:
        return None
    if operation == 'formula' and not calc['formula'] and not calc['sources']:
        return None
    return calc


def _unwrap_cell(raw: Any) -> Any:
    if isinstance(raw, dict) and ('original' in raw or 'modified' in raw):
        if raw.get('isModified'):
            return raw.get('modified')
        modified = raw.get('modified')
        if modified not in (None, ''):
            return modified
        return raw.get('original')
    return raw


def _parse_number(raw: Any):
    if raw is None or raw is _BLANK:
        return _BLANK
    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if isinstance(raw, (int, float)):
        number = float(raw)
        return number if number == number and number not in (float('inf'), float('-inf')) else _BLANK
    text = str(raw).strip().replace(',', '').replace('\u00a0', '').replace('\u202f', '')
    if not text:
        return _BLANK
    lowered = text.lower()
    if lowered == 'true':
        return 1.0
    if lowered == 'false':
        return 0.0
    try:
        number = float(text)
    except (TypeError, ValueError):
        return _BLANK
    if number != number or number in (float('inf'), float('-inf')):
        return _BLANK
    return number


def cell_formula_input(raw: Any, column_type: Optional[str]):
    """Map a stored cell to a formula input. Ticks are 0 or 1. Empty numbers are blank."""
    if column_type == 'tick':
        value = _unwrap_cell(raw)
        if value in (True, 1, '1', 'true', 'True', 'yes', 'Yes'):
            return 1.0
        return 0.0
    return _parse_number(_unwrap_cell(raw))


def _round_half_away(value: float, digits: int) -> float:
    quant = Decimal('1') if digits <= 0 else Decimal('1').scaleb(-digits)
    rounded = Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)
    return float(rounded)


def format_formula_number(value: Optional[float], decimals: Optional[int]) -> str:
    if value is None:
        return ''
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ''
    if number != number or number in (float('inf'), float('-inf')):
        return ''
    if decimals is None:
        text = f'{number:.6f}'.rstrip('0').rstrip('.')
        return '0' if text in ('', '-0') else text
    digits = max(0, min(6, int(decimals)))
    rounded = _round_half_away(number, digits)
    text = f'{rounded:.{digits}f}'
    if text in ('-0', '-0.0', '-0.00', '-0.000', '-0.0000', '-0.00000', '-0.000000'):
        return text[1:]
    return text


def _calculation_decimals(column: Mapping[str, Any]) -> int:
    calc = column.get('calculation') if isinstance(column, Mapping) else None
    if not isinstance(calc, dict) or calc.get('decimals') is None:
        return 2
    try:
        return max(0, min(6, int(calc.get('decimals'))))
    except (TypeError, ValueError):
        return 2


def _blank_as_zero(column: Mapping[str, Any]) -> bool:
    calc = column.get('calculation') if isinstance(column, Mapping) else None
    if not isinstance(calc, dict) or calc.get('blank_as_zero') is None:
        return True
    return bool(calc.get('blank_as_zero'))


def _formula_text(column: Mapping[str, Any]) -> str:
    calc = column.get('calculation') if isinstance(column, Mapping) else None
    if not isinstance(calc, dict):
        return ''
    operation = str(calc.get('operation') or 'formula').strip().lower()
    if operation == 'formula':
        return str(calc.get('formula') or '').strip()
    return compile_calculation(calc)


def _formula_refs(formula: str) -> List[str]:
    """Column codes used by a formula, whether written as income or {income}."""
    try:
        tokens = _tokenize(formula or '')
    except FormulaError:
        return _brace_refs(formula or '')
    refs: List[str] = []
    for index, token in enumerate(tokens):
        if token[0] == 'ref':
            refs.append(token[1])
        elif token[0] == 'id':
            nxt = tokens[index + 1] if index + 1 < len(tokens) else None
            if not (nxt and nxt[0] == 'punct' and nxt[1] == '('):
                refs.append(token[1])
    return refs


def _brace_refs(formula: str) -> List[str]:
    refs: List[str] = []
    index = 0
    while True:
        start = formula.find('{', index)
        if start < 0:
            break
        end = formula.find('}', start + 1)
        if end < 0:
            break
        name = formula[start + 1:end].strip()
        if name:
            refs.append(name)
        index = end + 1
    return refs


def _tokenize(formula: str) -> List[tuple]:
    tokens: List[tuple] = []
    index = 0
    length = len(formula)
    while index < length:
        char = formula[index]
        if char.isspace():
            index += 1
            continue
        if char == '{':
            end = formula.find('}', index + 1)
            if end < 0:
                raise FormulaError('Unclosed {')
            name = formula[index + 1:end].strip()
            if not name:
                raise FormulaError('Empty column reference')
            tokens.append(('ref', name))
            index = end + 1
            continue
        if char in '(),':
            tokens.append(('punct', char))
            index += 1
            continue
        pair = formula[index:index + 2]
        if pair in ('>=', '<=', '<>', '!='):
            tokens.append(('op', '<>' if pair == '!=' else pair))
            index += 2
            continue
        if char in '+-*/><=':
            tokens.append(('op', char))
            index += 1
            continue
        if char.isdigit() or (char == '.' and index + 1 < length and formula[index + 1].isdigit()):
            end = index
            seen_dot = False
            while end < length and (formula[end].isdigit() or (formula[end] == '.' and not seen_dot)):
                if formula[end] == '.':
                    seen_dot = True
                end += 1
            tokens.append(('num', float(formula[index:end])))
            index = end
            continue
        if char.isalpha() or char == '_':
            end = index
            while end < length and (formula[end].isalnum() or formula[end] == '_'):
                end += 1
            tokens.append(('id', formula[index:end]))
            index = end
            continue
        raise FormulaError(f'Unexpected character {char!r}')
    tokens.append(('eof', None))
    return tokens


class _Parser:
    def __init__(self, tokens: List[tuple], values: Dict[str, Any], blank_as_zero: bool, known: set):
        self.tokens = tokens
        self.i = 0
        self.values = values
        self.blank_as_zero = blank_as_zero
        self.known = known

    def peek(self):
        return self.tokens[self.i]

    def _is(self, kind: str, value: Optional[str] = None) -> bool:
        token = self.peek()
        if token[0] != kind:
            return False
        return value is None or token[1] == value

    def _as_number(self, value: Any):
        if value is _BLANK:
            return 0.0 if self.blank_as_zero else _BLANK
        return value

    def _arith(self, left: Any, op: str, right: Any):
        a = self._as_number(left)
        b = self._as_number(right)
        if a is _BLANK or b is _BLANK:
            return _BLANK
        if op == '+':
            return a + b
        if op == '-':
            return a - b
        if op == '*':
            return a * b
        if op == '/':
            if b == 0:
                raise FormulaError('Division by zero')
            return a / b
        raise FormulaError(f'Unexpected operator {op}')

    def _compare(self, left: Any, op: str, right: Any):
        a = self._as_number(left)
        b = self._as_number(right)
        if a is _BLANK or b is _BLANK:
            return _BLANK
        checks = {
            '>': a > b,
            '<': a < b,
            '>=': a >= b,
            '<=': a <= b,
            '=': a == b,
            '<>': a != b,
        }
        return 1.0 if checks[op] else 0.0

    def parse(self):
        if self._is('eof'):
            raise FormulaError('Empty formula')
        value = self._comparison()
        if not self._is('eof'):
            raise FormulaError('Unexpected input')
        return value

    def _comparison(self):
        left = self._additive()
        while self._is('op') and self.peek()[1] in ('>', '<', '>=', '<=', '=', '<>'):
            op = self.tokens[self.i][1]
            self.i += 1
            right = self._additive()
            left = self._compare(left, op, right)
        return left

    def _additive(self):
        left = self._multiplicative()
        while self._is('op') and self.peek()[1] in ('+', '-'):
            op = self.tokens[self.i][1]
            self.i += 1
            right = self._multiplicative()
            left = self._arith(left, op, right)
        return left

    def _multiplicative(self):
        left = self._unary()
        while self._is('op') and self.peek()[1] in ('*', '/'):
            op = self.tokens[self.i][1]
            self.i += 1
            right = self._unary()
            left = self._arith(left, op, right)
        return left

    def _unary(self):
        if self._is('op', '-'):
            self.i += 1
            value = self._unary()
            coerced = self._as_number(value)
            if coerced is _BLANK:
                return _BLANK
            return -coerced
        return self._primary()

    def _skip_expr(self):
        depth = 0
        while True:
            token = self.peek()
            if token[0] == 'eof':
                raise FormulaError("Expected ')'")
            if token[0] == 'punct' and token[1] == '(':
                depth += 1
            elif token[0] == 'punct' and token[1] == ')':
                if depth == 0:
                    return
                depth -= 1
            elif token[0] == 'punct' and token[1] == ',' and depth == 0:
                return
            self.i += 1

    def _args(self, fname: str):
        if not self._is('punct', '('):
            raise FormulaError(f'Expected ( after {fname}')
        self.i += 1
        args = []
        if self._is('punct', ')'):
            self.i += 1
            return args
        while True:
            args.append(self._comparison())
            if self._is('punct', ','):
                self.i += 1
                continue
            break
        if not self._is('punct', ')'):
            raise FormulaError("Expected ')'")
        self.i += 1
        return args

    def _call_if(self):
        if not self._is('punct', '('):
            raise FormulaError('Expected ( after IF')
        self.i += 1
        condition = self._comparison()
        if not self._is('punct', ','):
            raise FormulaError('IF needs 2 or 3 arguments')
        self.i += 1
        cond_num = condition if condition is not _BLANK else 0.0
        taken = cond_num != 0
        if taken:
            value = self._comparison()
            if self._is('punct', ','):
                self.i += 1
                self._skip_expr()
        else:
            self._skip_expr()
            value = _BLANK
            if self._is('punct', ','):
                self.i += 1
                value = self._comparison()
        if not self._is('punct', ')'):
            raise FormulaError("Expected ')'")
        self.i += 1
        return value

    def _numeric_args(self, args: List[Any]) -> List[float]:
        numbers = []
        for arg in args:
            if arg is _BLANK:
                continue
            numbers.append(float(arg))
        return numbers

    def _call(self, fname: str, args: List[Any]):
        if fname == 'BLANK':
            if args:
                raise FormulaError('BLANK takes no arguments')
            return _BLANK
        if fname in ('SUM', 'AVERAGE', 'MIN', 'MAX', 'COUNT', 'COUNTA'):
            if not args:
                raise FormulaError(f'{fname} needs at least 1 argument')
            if fname == 'SUM':
                return float(sum(self._numeric_args(args)))
            if fname == 'COUNT':
                return float(len(self._numeric_args(args)))
            if fname == 'COUNTA':
                return float(sum(1 for arg in args if arg is not _BLANK))
            numbers = self._numeric_args(args)
            if not numbers:
                return _BLANK
            if fname == 'AVERAGE':
                return float(sum(numbers) / len(numbers))
            if fname == 'MIN':
                return float(min(numbers))
            return float(max(numbers))
        if fname == 'ABS':
            if len(args) != 1:
                raise FormulaError('ABS needs 1 argument')
            value = self._as_number(args[0])
            if value is _BLANK:
                return _BLANK
            return abs(value)
        if fname == 'ROUND':
            if len(args) not in (1, 2):
                raise FormulaError('ROUND needs 1 or 2 arguments')
            value = self._as_number(args[0])
            if value is _BLANK:
                return _BLANK
            digits = 0
            if len(args) == 2:
                digit_value = self._as_number(args[1])
                if digit_value is _BLANK:
                    digits = 0
                else:
                    digits = int(digit_value)
            digits = max(0, min(6, digits))
            return _round_half_away(value, digits)
        raise FormulaError(f'Unknown function {fname}')

    def _primary(self):
        token = self.peek()
        if token[0] == 'num':
            self.i += 1
            return float(token[1])
        if token[0] == 'ref':
            self.i += 1
            name = token[1]
            if name in self.values:
                return self.values[name]
            if name not in self.known:
                raise FormulaError(f'Unknown column {{{name}}}')
            return _BLANK
        if token[0] == 'id':
            name = str(token[1])
            nxt = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
            if nxt and nxt[0] == 'punct' and nxt[1] == '(':
                fname = name.upper()
                self.i += 1
                if fname == 'IF':
                    return self._call_if()
                return self._call(fname, self._args(fname))
            self.i += 1
            if name in self.values:
                return self.values[name]
            if name not in self.known:
                raise FormulaError(f'Unknown column {name}')
            return _BLANK
        if token[0] == 'punct' and token[1] == '(':
            self.i += 1
            value = self._comparison()
            if not self._is('punct', ')'):
                raise FormulaError("Expected ')'")
            self.i += 1
            return value
        raise FormulaError('Unexpected input')


def evaluate_formula(formula: str, values: Mapping[str, Any], *, blank_as_zero: bool = True, known: Optional[Iterable[str]] = None):
    text = (formula or '').strip()
    if not text:
        raise FormulaError('Empty formula')
    known_names = set(known if known is not None else values.keys())
    parser = _Parser(_tokenize(text), dict(values), blank_as_zero, known_names)
    return parser.parse()


def _to_result(value: Any) -> FormulaResult:
    if isinstance(value, FormulaError):
        return FormulaResult(None, value.message)
    if value is _BLANK:
        return FormulaResult(None, None)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return FormulaResult(None, 'Not a number')
    if number != number or number in (float('inf'), float('-inf')):
        return FormulaResult(None, 'Not a number')
    return FormulaResult(number, None)


def evaluate_matrix_row(columns: Sequence[Any], inputs: Mapping[str, Any]) -> Dict[str, FormulaResult]:
    """Evaluate every calculated column for one row.

    ``inputs`` maps data-column names to stored cell values. Calculated columns
    may reference each other. A cycle returns a blank result and
    ``Circular reference``.
    """
    column_list = [col for col in (columns or []) if isinstance(col, dict) and col.get('name')]
    known = {str(col['name']) for col in column_list}
    values: Dict[str, Any] = {}
    for col in column_list:
        if col.get('type') == 'calculated':
            continue
        values[str(col['name'])] = cell_formula_input(inputs.get(col['name']), col.get('type'))

    pending: Dict[str, dict] = {}
    for col in column_list:
        if col.get('type') == 'calculated':
            pending[str(col['name'])] = col

    results: Dict[str, FormulaResult] = {}
    guard = 0
    limit = len(pending) + 1
    while pending and guard < limit:
        guard += 1
        progressed = False
        for name, col in list(pending.items()):
            formula = _formula_text(col)
            refs = _formula_refs(formula)
            if any(ref in pending for ref in refs):
                continue
            progressed = True
            try:
                raw = evaluate_formula(
                    formula,
                    values,
                    blank_as_zero=_blank_as_zero(col),
                    known=known,
                )
                result = _to_result(raw)
            except FormulaError as exc:
                result = FormulaResult(None, exc.message)
            results[name] = result
            values[name] = result.value if result.error is None and result.value is not None else _BLANK
            del pending[name]
        if not progressed:
            for name in list(pending):
                results[name] = FormulaResult(None, 'Circular reference')
                values[name] = _BLANK
                del pending[name]
            break
    return results


def _row_inputs(columns: Sequence[Any], matrix_data: Optional[Mapping[str, Any]], row_id: Any) -> Dict[str, Any]:
    inputs: Dict[str, Any] = {}
    data = matrix_data or {}
    for col in columns or []:
        if not isinstance(col, dict) or not col.get('name') or col.get('type') == 'calculated':
            continue
        inputs[col['name']] = data.get(f'{row_id}_{col["name"]}')
    return inputs


def matrix_formula_result(columns: Sequence[Any], matrix_data: Optional[Mapping[str, Any]], row_id: Any, column: Any) -> FormulaResult:
    name = column.get('name') if isinstance(column, dict) else column
    if not name:
        return FormulaResult(None, None)
    results = evaluate_matrix_row(columns or [], _row_inputs(columns or [], matrix_data, row_id))
    return results.get(str(name), FormulaResult(None, None))


def matrix_formula_number(columns, matrix_data, row_id, column_name) -> float:
    column = None
    for col in columns or []:
        if isinstance(col, dict) and str(col.get('name')) == str(column_name):
            column = col
            break
    if isinstance(column, dict):
        stored = stored_calculation_value(column, matrix_data, row_id)
        if stored is not None:
            return stored
    result = matrix_formula_result(columns, matrix_data, row_id, column or column_name)
    if result.error or result.value is None:
        return 0.0
    return float(result.value)


def _with_thousands_separator(text: str) -> str:
    """Group the integer part the same way PDF number cells do (1,234.50)."""
    if not text:
        return text
    sign = ''
    body = text
    if body.startswith('-'):
        sign = '-'
        body = body[1:]
    if '.' in body:
        whole, frac = body.split('.', 1)
        if not whole.isdigit() or not frac.isdigit():
            return text
        return f'{sign}{int(whole):,}.{frac}'
    if not body.isdigit():
        return text
    return f'{sign}{int(body):,}'


def matrix_formula_display(columns, matrix_data, row_id, column) -> str:
    decimals = _calculation_decimals(column) if isinstance(column, dict) else 2
    if isinstance(column, dict):
        stored = stored_calculation_value(column, matrix_data, row_id)
        if stored is not None:
            return _with_thousands_separator(format_formula_number(stored, decimals))
    result = matrix_formula_result(columns, matrix_data, row_id, column)
    if result.error or result.value is None:
        return ''
    return _with_thousands_separator(format_formula_number(result.value, decimals))


def matrix_formula_column_sum(columns, matrix_data, rows, column_name) -> float:
    total = 0.0
    for item in rows or []:
        if isinstance(item, dict):
            row_id = item.get('row_id', item.get('text'))
        else:
            row_id = item
        if row_id in (None, ''):
            continue
        total += matrix_formula_number(columns, matrix_data, row_id, column_name)
    return total


def matrix_counts_toward_row_total(column: Any) -> bool:
    """Jinja name for :func:`column_counts_toward_row_total`."""
    return column_counts_toward_row_total(column)
