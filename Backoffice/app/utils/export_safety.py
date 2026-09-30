"""Spreadsheet export safety (CSV / XLSX formula injection).

Cells that begin with ``=``, ``+``, ``-``, ``@``, TAB or CR are interpreted as formulas
by Excel, LibreOffice and Google Sheets. User-controlled text written to an export must be
neutralised by prefixing an apostrophe so it renders as literal text.

Numbers and booleans are left untouched: a Python ``-5`` is a numeric cell, not a formula.
Only *strings* are rewritten, so numeric columns keep their type.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Sequence

_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
_LEADING_STRIP = " \u00a0\u200b\ufeff"


def sanitize_spreadsheet_cell(value: Any) -> Any:
    """Return ``value`` safe to write into a CSV/XLSX cell.

    Non-string values are returned unchanged. Strings whose first significant character is a
    formula trigger (after ignoring leading spaces/zero-width characters that spreadsheet
    apps trim) get a leading apostrophe.
    """
    if not isinstance(value, str) or not value:
        return value
    probe = value.lstrip(_LEADING_STRIP)
    if probe and probe[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def sanitize_spreadsheet_row(row: Iterable[Any]) -> List[Any]:
    """Sanitise every cell of an iterable row."""
    return [sanitize_spreadsheet_cell(v) for v in row]


def sanitize_spreadsheet_mapping(
    row: Mapping[str, Any], *, keys: Optional[Sequence[str]] = None
) -> dict:
    """Sanitise the values of a mapping (e.g. for ``csv.DictWriter.writerow``)."""
    selected = keys if keys is not None else list(row.keys())
    return {k: sanitize_spreadsheet_cell(row.get(k)) for k in selected}


class SafeCsvWriter:
    """Thin wrapper around ``csv.writer`` that sanitises every cell it writes."""

    def __init__(self, writer: Any) -> None:
        self._writer = writer

    def writerow(self, row: Iterable[Any]) -> Any:
        return self._writer.writerow(sanitize_spreadsheet_row(row))

    def writerows(self, rows: Iterable[Iterable[Any]]) -> None:
        for row in rows:
            self.writerow(row)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._writer, name)


def safe_csv_writer(fileobj: Any, **kwargs: Any) -> SafeCsvWriter:
    """``csv.writer`` that neutralises formula-injection payloads."""
    import csv

    return SafeCsvWriter(csv.writer(fileobj, **kwargs))


class SafeCsvDictWriter:
    """Wrapper around ``csv.DictWriter`` that sanitises every value it writes."""

    def __init__(self, writer: Any) -> None:
        self._writer = writer

    def writerow(self, row: Mapping[str, Any]) -> Any:
        return self._writer.writerow({k: sanitize_spreadsheet_cell(v) for k, v in row.items()})

    def writerows(self, rows: Iterable[Mapping[str, Any]]) -> None:
        for row in rows:
            self.writerow(row)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._writer, name)


def safe_csv_dict_writer(fileobj: Any, fieldnames: Sequence[str], **kwargs: Any) -> SafeCsvDictWriter:
    import csv

    return SafeCsvDictWriter(csv.DictWriter(fileobj, fieldnames=fieldnames, **kwargs))


def sanitize_worksheet_cell_value(value: Any) -> Any:
    """Alias for openpyxl ``ws.cell(value=...)`` / ``ws.append([...])`` call sites."""
    return sanitize_spreadsheet_cell(value)


def sanitize_dataframe(df: Any) -> Any:
    """Return a copy of a pandas DataFrame with object/string columns sanitised."""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(sanitize_spreadsheet_cell)
    return out


def sanitize_workbook(workbook: Any) -> Any:
    """Neutralise formula-injection payloads in every string cell of an openpyxl workbook.

    Call immediately before ``workbook.save`` for exports that carry only data (never
    intentional formulas). Returns the workbook for chaining.
    """
    for ws in workbook.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if isinstance(value, str):
                    safe = sanitize_spreadsheet_cell(value)
                    if safe is not value:
                        cell.value = safe
                        cell.data_type = "s"
    return workbook
