from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from openpyxl import load_workbook

from calculations import as_float, money


EXPECTED_COLUMNS = [
    "Transaction ID",
    "Worker ID",
    "Worker",
    "Title",
    "Worker BU DU CC",
    "Competency Center",
    "Date",
    "Week End Date",
    "Financial Period",
    "Project ID",
    "Project",
    "Xref",
    "Phase Desc",
    "Task Desc",
    "Work Loc",
    "Billing Status",
    "Hours",
    "Fees @ Std Rate",
    "Fees @ Contract Rate",
    "Memo",
]

DATE_COLUMNS = {"Date", "Week End Date"}
HEADER_MARKERS = {"Transaction ID", "Worker", "Hours", "Fees @ Contract Rate"}


def normalize_header(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def excel_serial_to_iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        serial = float(text)
    except ValueError:
        return text
    return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()


def parse_text_export(text: str) -> list[dict[str, Any]]:
    text = text.strip("\ufeff\r\n ")
    if not text:
        return []
    sample = text[:2048]
    delimiter = "\t" if "\t" in sample else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    raw_rows = [list(row) for row in reader]
    header_index, headers = _find_header_row(raw_rows)
    if header_index is None:
        return []
    return _records_from_rows(headers, raw_rows[header_index + 1 :])


def parse_xlsx_export(file_bytes: bytes) -> list[dict[str, Any]]:
    workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheet = workbook.active
    raw_rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    workbook.close()
    header_index, headers = _find_header_row(raw_rows)
    if header_index is None:
        return []
    return _records_from_rows(headers, raw_rows[header_index + 1 :])


def _find_header_row(rows: list[list[Any]]) -> tuple[int | None, list[str]]:
    best_index: int | None = None
    best_headers: list[str] = []
    best_score = 0
    for index, row in enumerate(rows):
        headers = [normalize_header(cell) for cell in row]
        present = {header for header in headers if header}
        score = sum(1 for column in EXPECTED_COLUMNS if column in present)
        if HEADER_MARKERS.issubset(present) and score > best_score:
            best_index = index
            best_headers = headers
            best_score = score
    return best_index, best_headers


def _records_from_rows(headers: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for values in rows:
        if not any(value not in (None, "") for value in values):
            continue
        record = _row_from_values(headers, values)
        if _is_footer_or_non_entry(record):
            continue
        records.append(record)
    return records


def _is_footer_or_non_entry(record: dict[str, Any]) -> bool:
    transaction_id = str(record.get("Transaction ID", "")).strip()
    if not transaction_id:
        return True
    lowered = transaction_id.lower()
    if "summary" in lowered or lowered.startswith("overall"):
        return True
    return False


def _row_from_values(headers: list[str], values: list[Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for idx, header in enumerate(headers):
        if not header:
            continue
        value = values[idx] if idx < len(values) else ""
        if header in DATE_COLUMNS:
            value = excel_serial_to_iso(value)
        record[header] = "" if value is None else value
    return record


def validate_columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return EXPECTED_COLUMNS
    present = set(rows[0].keys())
    return [column for column in EXPECTED_COLUMNS if column not in present]


def preview_rows(
    conn: sqlite3.Connection, engagement_id: int, parsed_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    engagement = conn.execute(
        "SELECT engagement_code FROM engagements WHERE id = ?", (engagement_id,)
    ).fetchone()
    if engagement is None:
        raise ValueError("Engagement not found")

    team_names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM team_members WHERE engagement_id = ?", (engagement_id,)
        ).fetchall()
    }
    existing_ids = {
        row["transaction_id"]
        for row in conn.execute(
            "SELECT transaction_id FROM time_entries WHERE transaction_id IS NOT NULL"
        ).fetchall()
    }

    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    summary = {"total": 0, "to_import": 0, "duplicates": 0, "flagged": 0}
    for record in parsed_rows:
        transaction_id = str(record.get("Transaction ID", "")).strip()
        worker_name = str(record.get("Worker", "")).strip()
        project_id = str(record.get("Project ID", "")).strip()
        hours = as_float(record.get("Hours"))
        flag = None
        selectable = True
        included = True
        if not transaction_id or transaction_id in existing_ids or transaction_id in seen_ids:
            flag = "duplicate"
            selectable = False
            included = False
        elif hours == 0:
            flag = "zero_hours"
            included = False
        elif worker_name and worker_name not in team_names:
            flag = "worker_unknown"
            included = False
        elif project_id and project_id != engagement["engagement_code"]:
            flag = "project_mismatch"

        seen_ids.add(transaction_id)
        if flag == "duplicate":
            summary["duplicates"] += 1
        elif flag is not None:
            summary["flagged"] += 1
        if included:
            summary["to_import"] += 1
        summary["total"] += 1

        rows.append(
            {
                "transaction_id": transaction_id,
                "worker_id": str(record.get("Worker ID", "")).strip(),
                "worker_name": worker_name,
                "title": str(record.get("Title", "")).strip(),
                "entry_date": excel_serial_to_iso(record.get("Date")),
                "week_end_date": excel_serial_to_iso(record.get("Week End Date")),
                "financial_period": str(record.get("Financial Period", "")).strip(),
                "project_id": project_id,
                "project": str(record.get("Project", "")).strip(),
                "xref": str(record.get("Xref", "")).strip(),
                "phase_desc": str(record.get("Phase Desc", "")).strip(),
                "task_desc": str(record.get("Task Desc", "")).strip(),
                "work_location": str(record.get("Work Loc", "")).strip(),
                "billing_status": str(record.get("Billing Status", "")).strip(),
                "hours": hours,
                "fees_std_rate": money(record.get("Fees @ Std Rate")),
                "fees_contract_rate": money(record.get("Fees @ Contract Rate")),
                "memo": str(record.get("Memo", "")).strip(),
                "flag": flag,
                "included": included,
                "selectable": selectable,
            }
        )

    return {"rows": rows, "summary": summary}
