from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calculations import engagement_metrics, team_summary
from db import connect, init_db, now_iso


class CalculationTests(unittest.TestCase):
    def test_engagement_metrics_project_from_team_budgeted_fees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / "test.db"
            init_db(db_file)
            with connect(db_file) as conn:
                engagement_id = self._insert_engagement(conn, "P100", 10000, 1000, 500)
                conn.execute(
                    """
                    INSERT INTO team_members (
                      engagement_id, name, role, internal_rate, engagement_rate, budgeted_hours
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (engagement_id, "Smith, Jane", "Manager", 300, 350, 100),
                )
                snapshot_id = self._insert_snapshot(conn, engagement_id)
                conn.execute(
                    """
                    INSERT INTO time_entries (
                      snapshot_id, engagement_id, transaction_id, worker_name, hours, fees_contract_rate,
                      fees_std_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, engagement_id, "T1", "Smith, Jane", 50, 7000, 8000),
                )
                conn.execute(
                    """
                    INSERT INTO budget_adjustments (
                      engagement_id, effective_date, adjustment_type, amount, description, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (engagement_id, "2026-06-20", "markdown", -500, "Markdown", now_iso()),
                )

                metrics = engagement_metrics(conn, engagement_id)
                team = team_summary(conn, engagement_id)

            self.assertEqual(metrics["net_budget"], 11500)
            self.assertEqual(metrics["total_budgeted_fees"], 35000)
            self.assertEqual(metrics["projected_final"], 36000)
            self.assertEqual(metrics["projected_remaining"], 29000)
            self.assertTrue(metrics["markdown_required"])
            self.assertEqual(metrics["status"], "Over Budget")
            self.assertEqual(team[0]["hours_remaining"], 50)
            self.assertEqual(team[0]["rate_diff_total"], 2500)

    def test_demo_projection_subtracts_bima_from_projected_fees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / "demo.db"
            init_db(db_file)
            with connect(db_file) as conn:
                engagement_id = self._insert_engagement(conn, "DEMO-ALPHA-001", 24000, 0, 0)
                team = [
                    ("Analyst One", "Staff", 225, 225, 55),
                    ("Manager Two", "Senior Manager", 500, 500, 20),
                    ("Partner Three", "Partner", 900, 900, 3),
                    ("Project Services", "Project Services", 175, 175, 5),
                ]
                conn.executemany(
                    """
                    INSERT INTO team_members (
                      engagement_id, name, role, internal_rate, engagement_rate, budgeted_hours
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [(engagement_id, *member) for member in team],
                )
                snapshot_id = self._insert_snapshot(conn, engagement_id)
                entries = [
                    ("T1", "Analyst One", 40.25, 9056.25),
                    ("T2", "Manager Two", 8.5, 3125.0),
                    ("T3", "Partner Three", 2.0, 1800.0),
                ]
                conn.executemany(
                    """
                    INSERT INTO time_entries (
                      snapshot_id, engagement_id, transaction_id, worker_name, hours, fees_contract_rate
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [(snapshot_id, engagement_id, *entry) for entry in entries],
                )

                conn.execute(
                    """
                    INSERT INTO budget_adjustments (
                      engagement_id, effective_date, adjustment_type, amount, description, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (engagement_id, "2026-05-20", "bima", 1950, "BIMA discount", now_iso()),
                )

                metrics = engagement_metrics(conn, engagement_id)

            self.assertEqual(metrics["fees_to_date_contract"], 13981.25)
            self.assertEqual(metrics["net_budget"], 24000)
            self.assertEqual(metrics["total_budgeted_fees"], 25950)
            self.assertEqual(metrics["gross_projected_fees"], 25950)
            self.assertEqual(metrics["projected_reductions"], 1950)
            self.assertEqual(metrics["projected_final"], 24000)
            self.assertEqual(metrics["projected_remaining"], 10018.75)
            self.assertFalse(metrics["markdown_required"])

    def _insert_engagement(
        self, conn, code: str, max_sow_fees: float, change_order: float, c360_amount: float
    ) -> int:
        return conn.execute(
            """
            INSERT INTO engagements (
              engagement_code, client_name, max_sow_fees, change_order_amt,
              c360_amount, bima_amount, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code, "Client", max_sow_fees, change_order, c360_amount, 0, "Active", now_iso(), now_iso()),
        ).lastrowid

    def _insert_snapshot(self, conn, engagement_id: int) -> int:
        return conn.execute(
            """
            INSERT INTO weekly_snapshots (engagement_id, week_end_date, imported_at, row_count)
            VALUES (?, ?, ?, ?)
            """,
            (engagement_id, "2026-06-19", now_iso(), 1),
        ).lastrowid


if __name__ == "__main__":
    unittest.main()
