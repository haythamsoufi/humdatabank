"""
Shared CSV and Excel file parsing utilities.
Reduces duplication of import/encoding logic across lookup lists, indicators, etc.
"""
import csv
import codecs
import io
import json
from typing import List, Dict, Any, Tuple
from werkzeug.datastructures import FileStorage

from app.utils.safe_workbook import UnsafeWorkbookError, load_workbook_safe, safe_iter_rows

MAX_CSV_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 100_000
MAX_JSON_UPLOAD_BYTES = 5 * 1024 * 1024


# Extensions for CSV and Excel
CSV_EXCEL_EXTENSIONS = {".csv", ".xlsx", ".xls"}
EXCEL_EXTENSIONS = {".xlsx", ".xls"}
# Strict subset for routes backed by openpyxl (which only reads .xlsx natively)
XLSX_EXTENSIONS = {".xlsx"}


class UploadLimitError(ValueError):
    """An uploaded text file exceeds a size or row limit. The message is user-safe."""


def read_stream_capped(stream, max_bytes: int, what: str = "file") -> bytes:
    """Read at most ``max_bytes`` from ``stream``; raise :class:`UploadLimitError` if there is more."""
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadLimitError(f"The uploaded {what} is too large (limit {max_bytes // (1024 * 1024)} MB).")
    return data


def load_json_upload(file: FileStorage, max_bytes: int = MAX_JSON_UPLOAD_BYTES) -> Any:
    """Parse an uploaded JSON document with a size cap; parse failures become ``ValueError``."""
    raw = read_stream_capped(file.stream, max_bytes, "JSON file")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("The uploaded JSON file is not valid.") from exc


def _decode_csv_content(file_content: bytes) -> str:
    """Decode CSV file content, handling BOM and common encodings."""
    if file_content.startswith(codecs.BOM_UTF8):
        return file_content.decode("utf-8-sig")
    try:
        return file_content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return file_content.decode("latin-1")


def parse_csv_to_rows(file: FileStorage) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parse a CSV file into columns and row dicts.

    Args:
        file: FileStorage object (position will be consumed)

    Returns:
        Tuple of (columns: list of header names, rows: list of dicts)
    """
    file_content = read_stream_capped(file.stream, MAX_CSV_UPLOAD_BYTES, "CSV file")
    text = _decode_csv_content(file_content)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = list(reader.fieldnames or [])
    rows: List[Dict[str, Any]] = []
    try:
        for row in reader:
            if len(rows) >= MAX_CSV_ROWS:
                raise UploadLimitError(f"The CSV file has too many rows (limit {MAX_CSV_ROWS}).")
            rows.append(row)
    except csv.Error as exc:
        raise ValueError("The CSV file is malformed.") from exc
    return columns, rows


def parse_excel_to_rows(file: FileStorage) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parse an Excel file (.xlsx, .xls) into columns and row dicts.

    Args:
        file: FileStorage object (position will be consumed)

    Returns:
        Tuple of (columns: list of header names, rows: list of dicts)
    """
    wb = load_workbook_safe(file, read_only=True, data_only=False)
    ws = wb.active
    rows_iter = safe_iter_rows(ws, values_only=True)
    try:
        headers = next(rows_iter, None) or []
        columns = [str(h) for h in headers]
        rows = []
        for values in rows_iter:
            row = {columns[i]: (values[i] if i < len(values) else None) for i in range(len(columns))}
            rows.append(row)
    finally:
        wb.close()
    return columns, rows


def parse_csv_or_excel_to_rows(file: FileStorage, filename: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parse a CSV or Excel file into columns and row dicts.
    Chooses parser based on filename extension.

    Args:
        file: FileStorage object (position will be consumed)
        filename: Original filename (used to determine format)

    Returns:
        Tuple of (columns: list of header names, rows: list of dicts)

    Raises:
        ValueError: If file format is not .csv, .xlsx, or .xls
    """
    fn = filename.lower()
    if fn.endswith(".csv"):
        return parse_csv_to_rows(file)
    if fn.endswith((".xlsx", ".xls")):
        return parse_excel_to_rows(file)
    raise ValueError(f"Unsupported file format: {filename}. Expected CSV or Excel.")
