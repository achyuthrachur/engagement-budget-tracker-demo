from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db


class FrozenSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.seed = Path(__file__).resolve().parents[1] / "demo_seed.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_frozen_init_copies_seed_when_database_is_missing(self):
        target = self.temp_path / "budget_tracker.db"
        with patch.object(db.sys, "frozen", True, create=True), patch("db.seed_path", return_value=self.seed), patch("db.schema_path", return_value=Path(__file__).resolve().parents[1] / "schema.sql"):
            db.init_db(target)
        conn = sqlite3.connect(target)
        try:
            count = conn.execute("SELECT COUNT(*) FROM engagements").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 5)

    def test_frozen_init_replaces_empty_database_with_seed(self):
        target = self.temp_path / "budget_tracker.db"
        conn = sqlite3.connect(target)
        try:
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.commit()
        finally:
            conn.close()
        with patch.object(db.sys, "frozen", True, create=True), patch("db.seed_path", return_value=self.seed), patch("db.schema_path", return_value=Path(__file__).resolve().parents[1] / "schema.sql"):
            db.init_db(target)
        conn = sqlite3.connect(target)
        try:
            count = conn.execute("SELECT COUNT(*) FROM engagements").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 5)

    def test_republic_seed_preserves_source_weekly_values(self):
        conn = sqlite3.connect(self.seed)
        try:
            engagement_id = conn.execute(
                "SELECT id FROM engagements WHERE client_name='Republic'"
            ).fetchone()[0]
            budget = conn.execute(
                """SELECT ROUND(SUM(ppw.budgeted_hours),2)
                FROM phase_person_weeks ppw
                JOIN phases p ON p.id=ppw.phase_id
                WHERE p.engagement_id=?""",
                (engagement_id,),
            ).fetchone()[0]
            actual_by_week = [
                row[0] for row in conn.execute(
                    """SELECT ROUND(SUM(hours),2)
                    FROM time_entries WHERE engagement_id=?
                    GROUP BY week_end_date ORDER BY week_end_date""",
                    (engagement_id,),
                )
            ]
            forecast = conn.execute(
                """SELECT ROUND(SUM(ppw.forecasted_hours),2)
                FROM phase_person_weeks ppw
                JOIN phases p ON p.id=ppw.phase_id
                WHERE p.engagement_id=?""",
                (engagement_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(budget, 409)
        self.assertEqual(actual_by_week, [13, 42, 44, 47.5, 48, 36, 20, 25.25])
        self.assertEqual(sum(actual_by_week), 275.75)
        self.assertEqual(forecast, 72)


if __name__ == "__main__":
    unittest.main()
