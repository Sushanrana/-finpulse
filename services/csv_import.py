"""CSV import with strict validation.

File-level checks (whole file rejected): extension, MIME type, size, encoding,
parseability, required columns, row limit (5,000).
Row-level checks (bad rows skipped with a clear message): date format, amount
format, text fields, type, duplicates (within the file and against existing data).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd

from .validation import ValidationError, clean_category, clean_text, parse_amount, parse_date, parse_type

MAX_ROWS = 5000
MAX_BYTES = 2 * 1024 * 1024  # 2 MB
REQUIRED_COLUMNS = ("date", "description", "category", "amount")
OPTIONAL_COLUMNS = ("type",)
ALLOWED_MIMETYPES = {
    "", "text/csv", "application/csv", "text/plain", "application/vnd.ms-excel",
    "text/comma-separated-values", "application/octet-stream",
}


class CSVImportError(Exception):
    """Whole-file problem; nothing is imported."""


@dataclass
class ImportResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_rows: int = 0
    duplicates: int = 0


def dedupe_key(row: dict[str, Any]) -> tuple:
    return (
        str(row["date"]),
        str(row["description"]).strip().lower(),
        str(row["category"]).strip().lower(),
        round(float(row["amount"]), 2),
        str(row["type"]),
    )


def _cell(record: dict[str, Any], column: str) -> str:
    value = record.get(column, "")
    return value if isinstance(value, str) else ""


def parse_csv(data: bytes, filename: str, existing_keys: Iterable[tuple] = (),
              mimetype: str | None = None) -> ImportResult:
    name = (filename or "").strip().lower()
    if not name.endswith(".csv"):
        raise CSVImportError("Only .csv files are accepted.")
    if mimetype is not None and mimetype.split(";")[0].strip().lower() not in ALLOWED_MIMETYPES:
        raise CSVImportError(f"File type '{mimetype}' is not allowed. Upload a plain CSV file.")
    if not data:
        raise CSVImportError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise CSVImportError(f"The file is too large (max {MAX_BYTES // (1024 * 1024)} MB).")
    if b"\x00" in data[:4096]:
        raise CSVImportError("This looks like a binary file, not a CSV.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVImportError("The file must be UTF-8 encoded text.") from exc

    # pandas silently turns surplus fields into an index, so check row widths explicitly.
    header_width = None
    for line_no, fields in enumerate(csv.reader(io.StringIO(text)), start=1):
        if header_width is None:
            header_width = len(fields)
        elif len(fields) > header_width:
            raise CSVImportError(
                f"The CSV is malformed: row {line_no} has more columns than the header.")

    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False,
                         skipinitialspace=True, on_bad_lines="error")
    except pd.errors.EmptyDataError as exc:
        raise CSVImportError("The file has no header row.") from exc
    except pd.errors.ParserError as exc:
        raise CSVImportError("The CSV is malformed: some rows have more columns than the header.") from exc

    columns = [str(c).strip().lower() for c in df.columns]
    if len(set(columns)) != len(columns):
        raise CSVImportError("The header contains duplicate column names.")
    df.columns = columns
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise CSVImportError(
            f"Missing required column(s): {', '.join(missing)}. "
            "Expected header: date,description,category,amount[,type]"
        )
    if len(df) == 0:
        raise CSVImportError("The file has a header but no data rows.")
    if len(df) > MAX_ROWS:
        raise CSVImportError(f"The file has {len(df):,} rows; the maximum is {MAX_ROWS:,}.")

    has_type = "type" in columns
    existing = set(existing_keys)
    seen: set[tuple] = set()
    result = ImportResult(total_rows=int(len(df)))

    for idx, record in enumerate(df.to_dict("records")):
        line = idx + 2  # +1 for the header, +1 for 1-based numbering
        try:
            row_date = parse_date(_cell(record, "date"))
            description = clean_text(_cell(record, "description"), "Description", 120)
            category = clean_category(_cell(record, "category"))
            amount = parse_amount(_cell(record, "amount"), allow_negative=True)
            type_raw = _cell(record, "type").strip() if has_type else ""
            tx_type = parse_type(type_raw) if type_raw else ("expense" if amount < 0 else "income")
        except ValidationError as exc:
            result.errors.append(f"Row {line}: {exc}")
            continue

        row = {"date": row_date, "description": description, "category": category,
               "amount": abs(amount), "type": tx_type}
        key = dedupe_key(row)
        if key in seen:
            result.duplicates += 1
            result.errors.append(f"Row {line}: duplicate of an earlier row in this file, so it was skipped.")
            continue
        if key in existing:
            result.duplicates += 1
            result.errors.append(f"Row {line}: this transaction already exists in your account, so it was skipped.")
            continue
        seen.add(key)
        result.rows.append(row)

    return result
