from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import connect, init_db, now_iso
from exports import CURRENCY_FORMAT, HOURS_FORMAT, build_excel, build_html_report


class ExportTests(unittest.TestCase):
    def test_excel_export_formats_values_and_adds_charts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / 'export.db'
            engagement_id = self._seed_export_data(db_file)
            with connect(db_file) as conn:
                _, content = build_excel(conn, engagement_id)

        workbook = load_workbook(io.BytesIO(content))
        summary = workbook['Engagement Summary']
        weekly = workbook['Weekly Detail']
        self.assertEqual(summary['A5'].value, 'Budget Run Date')
        self.assertEqual(summary['B8'].number_format, HOURS_FORMAT)
        self.assertEqual(summary['B11'].number_format, CURRENCY_FORMAT)
        self.assertGreaterEqual(len(summary._charts), 2)
        self.assertEqual(weekly['L2'].number_format, HOURS_FORMAT)
        self.assertEqual(weekly['M2'].number_format, CURRENCY_FORMAT)
        self.assertEqual(weekly['N2'].number_format, CURRENCY_FORMAT)

    def test_html_export_formats_money_hours_and_visuals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / 'export.db'
            engagement_id = self._seed_export_data(db_file)
            with connect(db_file) as conn:
                html = build_html_report(conn, engagement_id, 'Narrative')

        self.assertIn('Budget Run Date', html)
        self.assertIn('$10,000.00', html)
        self.assertIn('1,234.50', html)
        self.assertIn('bar-track', html)
        self.assertIn('Team Budget Visualization', html)

    def _seed_export_data(self, db_file: Path) -> int:
        init_db(db_file)
        with connect(db_file) as conn:
            engagement_id = conn.execute(
                """
                INSERT INTO engagements (
                  engagement_code, client_name, max_sow_fees, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ('P100', 'Export Client', 10000, 'Active', now_iso(), now_iso()),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO team_members (
                  engagement_id, name, role, internal_rate, engagement_rate, budgeted_hours
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (engagement_id, 'Smith, Jane', 'Manager', 300, 350, 1234.5),
            )
            snapshot_id = conn.execute(
                """
                INSERT INTO weekly_snapshots (engagement_id, week_end_date, imported_at, row_count)
                VALUES (?, ?, ?, ?)
                """,
                (engagement_id, '2026-06-19', now_iso(), 1),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO time_entries (
                  snapshot_id, engagement_id, transaction_id, worker_name, entry_date,
                  week_end_date, hours, fees_std_rate, fees_contract_rate, memo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (snapshot_id, engagement_id, 'T1', 'Smith, Jane', '2026-06-18', '2026-06-19', 12.5, 4500, 4375, 'Memo'),
            )
        return engagement_id


if __name__ == '__main__':
    unittest.main()
