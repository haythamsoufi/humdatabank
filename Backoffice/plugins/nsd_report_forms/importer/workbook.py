"""Read and validate the NSD master import workbook. No database access here."""
import datetime as dt
import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.utils.safe_workbook import load_workbook_safe, read_workbook_file_bytes

from . import layout

MAX_MESSAGES_PER_KIND = 25


class Book:
    """Parsed workbook: rows per sheet plus blocking errors and non-blocking warnings."""

    def __init__(self):
        self.rows: Dict[str, List[dict]] = {name: [] for name in layout.SHEETS}
        self.sheets_found: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self._warn_counts = defaultdict(int)

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, kind: str, msg: str):
        """Warnings of one kind are capped; the rest are only counted."""
        self._warn_counts[kind] += 1
        if self._warn_counts[kind] <= MAX_MESSAGES_PER_KIND:
            self.warnings.append(msg)

    def finish(self):
        for kind, n in self._warn_counts.items():
            if n > MAX_MESSAGES_PER_KIND:
                self.warnings.append(f'... and {n - MAX_MESSAGES_PER_KIND} more warnings of the same kind ({kind})')


def _clean(v: Any) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _to_date(v: Any) -> Optional[str]:
    if v is None or v == '':
        return ''
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S'):
        try:
            return dt.datetime.strptime(s[:19] if ' ' in s else s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_number(v: Any) -> Optional[str]:
    """Numbers are kept as plain decimal strings (the forms store text)."""
    if v is None or v == '':
        return ''
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f.is_integer() else repr(f)
    s = re.sub(r'[\s,]', '', str(v))
    try:
        f = float(s)
    except ValueError:
        return None
    return str(int(f)) if f.is_integer() else repr(f)


def _to_json(v: Any):
    if v is None or v == '':
        return None
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(str(v))
    except ValueError:
        return False


def _choice(v: Any, choices, aliases=()) -> Optional[str]:
    s = _clean(v)
    if not s:
        return ''
    for old, canonical in aliases:
        if old.casefold() == s.casefold():
            return canonical
    for c in choices:
        if c.casefold() == s.casefold():
            return c
    return None


def _read_sheet(book: Book, ws, name: str):
    cols = layout.SHEETS[name]
    header = [_clean(c) for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])]
    index = {h: i for i, h in enumerate(header) if h}
    missing = [c.name for c in cols if c.required and c.name not in index]
    if missing:
        book.error(f'Sheet {name}: required column(s) missing: {", ".join(missing)}')
        return
    known = {c.name for c in cols}
    unknown = [h for h in index if h not in known]
    if unknown:
        book.warn('unknown-column', f'Sheet {name}: unknown column(s) ignored: {", ".join(unknown)}')
    for rn, raw in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        if raw is None or all(v is None or str(v).strip() == '' for v in raw):
            continue
        row = {'_row': rn}
        bad = False
        for col in cols:
            if col.name not in index:
                row[col.name] = None if col.kind in ('json',) else ''
                continue
            v = raw[index[col.name]] if index[col.name] < len(raw) else None
            if col.kind == 'date':
                val = _to_date(v)
            elif col.kind == 'number':
                val = _to_number(v)
            elif col.kind == 'json':
                val = _to_json(v)
            elif col.kind == 'choice':
                val = _choice(v, col.choices, col.aliases)
            else:
                val = _clean(v)
            invalid = (val is False) if col.kind == 'json' else (val is None or val is False)
            if invalid:
                what = 'is not a valid ' + {'date': 'date (use yyyy-mm-dd)', 'number': 'number', 'json': 'JSON',
                                            'choice': 'value (allowed: ' + ', '.join(col.choices) + ')'}.get(col.kind, 'value')
                if col.required:
                    book.error(f'{name} row {rn}: "{col.name}" {what}: {_clean(v)[:60]!r}')
                    bad = True
                else:
                    book.warn(f'{name}-{col.name}', f'{name} row {rn}: "{col.name}" {what}: {_clean(v)[:40]!r} (ignored)')
                val = None if col.kind == 'json' else ''
            if col.required and (val is None or val == '') and not bad:
                book.error(f'{name} row {rn}: required "{col.name}" is empty')
                bad = True
            row[col.name] = val
        if not bad:
            book.rows[name].append(row)


def parse(path: str) -> Book:
    book = Book()
    try:
        wb = load_workbook_safe(read_workbook_file_bytes(path), read_only=True, data_only=True)
    except Exception as exc:  # UnsafeWorkbookError, corrupt file, ...
        book.error(f'The file could not be read as an Excel workbook: {exc}')
        return book
    book.sheets_found = list(wb.sheetnames)
    for name in layout.REQUIRED_SHEETS:
        if name not in wb.sheetnames:
            book.error(f'Required sheet "{name}" is missing.')
    if book.errors:
        return book
    for name in layout.SHEETS:
        if name in wb.sheetnames:
            _read_sheet(book, wb[name], name)
    _cross_check(book)
    book.finish()
    return book


def _cross_check(book: Book):
    projects = {}
    for r in book.rows['Projects']:
        ref = r['reference']
        if ref in projects:
            book.error(f'Projects row {r["_row"]}: reference {ref} appears more than once')
        projects[ref] = r
    for r in list(book.rows['Projects']):
        if r['fund'] != 'CBF':
            book.warn('fund', f'Projects row {r["_row"]}: {r["reference"]} is not CBF, skipped')
            book.rows['Projects'].remove(r)
            projects.pop(r['reference'], None)

    def known(sheet: str, rows: List[dict]) -> List[dict]:
        keep = []
        for r in rows:
            if r['reference'] in projects:
                keep.append(r)
            else:
                book.warn(f'{sheet}-ref', f'{sheet} row {r["_row"]}: project {r["reference"]} is not in the Projects sheet (row skipped)')
        return keep

    for sheet in ('Logframe', 'Schedule', 'Quarterly', 'FinalCBF'):
        book.rows[sheet] = known(sheet, book.rows[sheet])

    seen = set()
    for r in list(book.rows['Schedule']):
        key = (r['reference'], r['report_type'], r['period'])
        if key in seen:
            book.warn('schedule-dup', f'Schedule row {r["_row"]}: duplicate {key[0]} / {key[1]} / {key[2]} (skipped)')
            book.rows['Schedule'].remove(r)
        seen.add(key)

    quarters = {(r['reference'], r['period']) for r in book.rows['Schedule'] if r['report_type'] == 'CBF quarter'}
    for r in list(book.rows['Quarterly']):
        if (r['reference'], r['period']) not in quarters:
            book.warn('quarterly-period', f'Quarterly row {r["_row"]}: {r["reference"]} has no CBF quarter {r["period"]} in Schedule (row skipped)')
            book.rows['Quarterly'].remove(r)

    seen_final = set()
    for r in list(book.rows['FinalCBF']):
        if r['reference'] in seen_final:
            book.warn('final-dup', f'FinalCBF row {r["_row"]}: second final report for {r["reference"]} (skipped)')
            book.rows['FinalCBF'].remove(r)
        seen_final.add(r['reference'])


def logframe_structure(rows: List[dict]) -> List[dict]:
    """Build the nested outcomes structure the NSD field stores from the flat Logframe rows of one project."""
    outcomes: Dict[int, dict] = {}
    order: List[int] = []

    def num(v) -> Optional[float]:
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return None

    for r in rows:
        o = int(float(r['outcome_no'] or 0))
        if o not in outcomes:
            outcomes[o] = {'category': '', 'definition': '', 'planned_budget': None, 'indicators': [], 'outputs': []}
            order.append(o)
        oc = outcomes[o]
        u = int(float(r['output_no'])) if r.get('output_no') not in (None, '') else None
        t = r['row_type']
        if t == 'Outcome':
            oc['definition'] = r['text']
            oc['category'] = r.get('category') or ''
            oc['planned_budget'] = num(r.get('planned_budget_chf'))
        elif u is None and t == 'Indicator':
            oc['indicators'].append({'name': r['text'], 'baseline': r.get('baseline') or '', 'target': r.get('target') or ''})
        else:
            while len(oc['outputs']) < (u or 0):
                oc['outputs'].append({'name': '', 'planned_budget': None, 'indicators': [], 'activities': []})
            if u is None:
                continue
            out = oc['outputs'][u - 1]
            if t == 'Output':
                out['name'] = r['text']
                out['planned_budget'] = num(r.get('planned_budget_chf'))
            elif t == 'Activity':
                out['activities'].append({'name': r['text'], 'planned_budget': num(r.get('planned_budget_chf')) or 0})
            elif t == 'Indicator':
                out['indicators'].append({'name': r['text'], 'baseline': r.get('baseline') or '', 'target': r.get('target') or ''})
    return [outcomes[o] for o in sorted(order)]
