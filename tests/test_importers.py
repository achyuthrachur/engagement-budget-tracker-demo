from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import connect, init_db, now_iso
from importers import (
    EXPECTED_COLUMNS,
    excel_serial_to_iso,
    parse_text_export,
    parse_xlsx_export,
    preview_rows,
)


class ImporterTests(unittest.TestCase):
    def test_excel_serial_date_conversion(self):
        self.assertEqual(excel_serial_to_iso("45123"), "2023-07-16")

    def test_parse_xlsx_export_finds_header_below_preamble(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Time Detail"
        sheet["B2"] = "Time and Cost Detail for Customer: Sample"
        sheet["B4"] = "Project: P100 - Sample"
        sheet["B6"] = "From: 4/1/2026 to 6/17/2026"
        sheet["B8"] = "Confidential data for internal use only."
        for col, header in enumerate(EXPECTED_COLUMNS, 2):
            sheet.cell(row=11, column=col, value=header)
        values = [
            "T1",
            "W1",
            "Smith, Jane",
            "Manager",
            "CONSULT RISK",
            "MRLR",
            "45123",
            "45129",
            "2026-06",
            "P100",
            "Project",
            "P100",
            "Phase",
            "Task",
            "Remote",
            "Billable",
            1.5,
            300,
            250,
            "Memo",
        ]
        for col, value in enumerate(values, 2):
            sheet.cell(row=12, column=col, value=value)
        sheet["B13"] = "Overall- Summary"
        sheet["R13"] = 1.5
        output = io.BytesIO()
        workbook.save(output)

        rows = parse_xlsx_export(output.getvalue())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Transaction ID"], "T1")
        self.assertEqual(rows[0]["Date"], "2023-07-16")
        self.assertEqual(rows[0]["Worker"], "Smith, Jane")

    def test_preview_flags_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / "test.db"
            init_db(db_file)
            with connect(db_file) as conn:
                engagement_id = conn.execute(
                    """
                    INSERT INTO engagements (
                      engagement_code, client_name, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("P100", "Client", "active", now_iso(), now_iso()),
                ).lastrowid
                conn.execute(
                    "INSERT INTO phases (engagement_id,phase_name,is_default) VALUES (?,'General',1)",
                    (engagement_id,),
                )
                conn.execute(
                    """
                    INSERT INTO team_members (engagement_id, name, role)
                    VALUES (?, ?, ?)
                    """,
                    (engagement_id, "Smith, Jane", "Manager"),
                )
                conn.execute(
                    """
                    INSERT INTO weekly_snapshots (engagement_id, week_end_date, imported_at, row_count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (engagement_id, "2026-06-19", now_iso(), 1),
                )
                snapshot_id = conn.execute("SELECT id FROM weekly_snapshots").fetchone()["id"]
                conn.execute(
                    """
                    INSERT INTO time_entries (snapshot_id, engagement_id, transaction_id)
                    VALUES (?, ?, ?)
                    """,
                    (snapshot_id, engagement_id, "DUP"),
                )
                rows = [
                    self._row("OK", "Smith, Jane", "P100", 1),
                    self._row("MIS", "Smith, Jane", "P200", 1),
                    self._row("UNK", "Unknown, Worker", "P100", 1),
                    self._row("ZERO", "Smith, Jane", "P100", 0),
                    self._row("DUP", "Smith, Jane", "P100", 1),
                ]
                preview = preview_rows(conn, engagement_id, rows)

        flags = {row["transaction_id"]: row["flag"] for row in preview["rows"]}
        self.assertIsNone(flags["OK"])
        self.assertEqual(flags["MIS"], "project_mismatch")
        self.assertEqual(flags["UNK"], "worker_unknown")
        self.assertEqual(flags["ZERO"], "zero_hours")
        self.assertEqual(flags["DUP"], "duplicate")
        self.assertEqual(preview["summary"]["to_import"], 2)

    def test_parse_tab_delimited_export(self):
        line = "\t".join(EXPECTED_COLUMNS)
        values = ["T1", "W1", "Smith, Jane", "Manager", "", "", "45123", "45129", "2026-06", "P100", "Project", "", "Phase", "Task", "Remote", "Billable", "1.5", "300", "250", "Memo"]
        rows = parse_text_export(line + "\n" + "\t".join(values))
        self.assertEqual(rows[0]["Date"], "2023-07-16")
        self.assertEqual(rows[0]["Worker"], "Smith, Jane")

    def _row(self, transaction_id: str, worker: str, project_id: str, hours: float):
        return {
            "Transaction ID": transaction_id,
            "Worker ID": "W1",
            "Worker": worker,
            "Title": "Manager",
            "Date": "45123",
            "Week End Date": "45129",
            "Financial Period": "2026-06",
            "Project ID": project_id,
            "Project": "Project",
            "Phase Desc": "Phase",
            "Task Desc": "Task",
            "Work Loc": "Remote",
            "Billing Status": "Billable",
            "Hours": hours,
            "Fees @ Std Rate": 300,
            "Fees @ Contract Rate": 250,
            "Memo": "",
        }


if __name__ == "__main__":
    unittest.main()
