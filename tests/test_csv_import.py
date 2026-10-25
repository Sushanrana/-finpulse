"""Feature 2b: CSV import validation."""
import io
import re
from pathlib import Path

import pytest

from helpers import csrf_from
from services import csv_import
from services.csv_import import CSVImportError, parse_csv

SAMPLES = Path(__file__).resolve().parents[1] / "sample_data"
HEADER = "date,description,category,amount,type\n"


def test_valid_sample_file_parses_fully():
    data = (SAMPLES / "transactions_sample.csv").read_bytes()
    result = parse_csv(data, "transactions_sample.csv")
    assert result.errors == []
    assert len(result.rows) == result.total_rows == 30


def test_signed_bank_export_infers_type():
    data = (SAMPLES / "bank_export_signed.csv").read_bytes()
    result = parse_csv(data, "bank_export_signed.csv")
    assert result.errors == []
    salary = result.rows[0]
    assert salary["type"] == "income" and salary["amount"] == 1450.0
    assert result.rows[1]["type"] == "expense" and result.rows[1]["amount"] == 1040.0


def test_error_sample_reports_each_bad_row():
    data = (SAMPLES / "transactions_with_errors.csv").read_bytes()
    result = parse_csv(data, "transactions_with_errors.csv")
    errors = "\n".join(result.errors)
    assert "Row 4: Invalid date" in errors
    assert "Row 5: Invalid amount" in errors
    assert "Row 6: Invalid amount" in errors          # 3 decimals
    assert "Row 7: Description is required" in errors
    assert "Row 8: Type must be" in errors
    assert "Row 9: Description cannot start with" in errors  # formula injection
    assert "Row 10: Amount cannot be zero" in errors
    assert "Row 12: duplicate" in errors
    assert len(result.rows) == 4


@pytest.mark.parametrize("filename,data,message", [
    ("data.txt", b"date,description,category,amount\n", "Only .csv"),
    ("data.csv", b"", "empty"),
    ("data.csv", b"\x89PNG\r\n\x1a\n\x00\x00", "binary"),
    ("data.csv", "date,description,category,amount\n2025-01-01,Caf\xe9,Dining,5\n".encode("latin-1"), "UTF-8"),
    ("data.csv", b"date,description,amount\n2025-01-01,x,5\n", "Missing required column(s): category"),
    ("data.csv", b"date,description,category,amount\n", "no data rows"),
    ("data.csv", b"date,description,category,amount\n2025-01-01,a,b,1,extra,more\n", "malformed"),
])
def test_file_level_rejections(filename, data, message):
    with pytest.raises(CSVImportError, match=re.escape(message)):
        parse_csv(data, filename)


def test_rejects_disallowed_mimetype():
    with pytest.raises(CSVImportError, match="not allowed"):
        parse_csv(b"date,description,category,amount\n2025-01-01,a,Other,1\n", "x.csv", mimetype="image/png")


def test_row_limit_is_5000():
    ok = HEADER + "".join(f"2025-01-01,Item {i},Other,1.00,expense\n" for i in range(5000))
    assert len(parse_csv(ok.encode(), "ok.csv").rows) == 5000
    too_many = HEADER + "".join(f"2025-01-01,Item {i},Other,1.00,expense\n" for i in range(5001))
    with pytest.raises(CSVImportError, match="maximum is 5,000"):
        parse_csv(too_many.encode(), "big.csv")


def test_size_limit():
    big = b"x" * (csv_import.MAX_BYTES + 1)
    with pytest.raises(CSVImportError, match="too large"):
        parse_csv(big, "big.csv")


def test_duplicates_against_existing_data():
    row = {"date": "2025-01-01", "description": "Rent", "category": "Rent", "amount": 1000.0, "type": "expense"}
    existing = {csv_import.dedupe_key(row)}
    result = parse_csv((HEADER + "2025-01-01,rent,rent,1000,expense\n").encode(), "x.csv", existing)
    assert result.rows == [] and "already exists" in result.errors[0]


def _upload(client, content: bytes, filename: str = "upload.csv", content_type: str = "text/csv"):
    token = csrf_from(client, "/transactions")
    return client.post("/transactions/import", data={
        "csrf_token": token, "csv_file": (io.BytesIO(content), filename, content_type),
    }, content_type="multipart/form-data")


def test_import_route_inserts_valid_rows_and_reports_errors(alice, query):
    resp = _upload(alice, (SAMPLES / "transactions_with_errors.csv").read_bytes())
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "4 imported" in body and "8 skipped" in body
    assert "Row 4: Invalid date" in body
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 4
    # Re-importing the same file is fully de-duplicated
    body = _upload(alice, (SAMPLES / "transactions_with_errors.csv").read_bytes()).get_data(as_text=True)
    assert "0 imported" in body and "already exists" in body
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 4


def test_import_route_rejects_wrong_file_type(alice, query):
    resp = _upload(alice, b"not a csv", filename="malware.exe", content_type="application/x-msdownload")
    assert resp.status_code == 400
    assert "Only .csv files are accepted" in resp.get_data(as_text=True)
    assert query("SELECT COUNT(*) AS n FROM transactions")[0]["n"] == 0


def test_import_requires_csrf(alice):
    resp = alice.post("/transactions/import", data={"csv_file": (io.BytesIO(b"a"), "a.csv")},
                      content_type="multipart/form-data")
    assert resp.status_code == 400
