from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from db import connect, init_db


class MigrationTests(unittest.TestCase):
    def test_v1_database_is_backed_up_and_migrated_without_losing_imports(self):
        source = Path(__file__).resolve().parents[1] / "demo_seed.db"
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "legacy.db"
            shutil.copyfile(source, target)
            init_db(target)
            backup = target.with_name("legacy.pre-v2.bak.db")
            self.assertTrue(backup.exists())
            with connect(target) as db:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(engagements)")}
                self.assertIn("complexity_mode", columns)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM engagements").fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM time_entries").fetchone()[0], 22)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM phase_person_weeks").fetchone()[0], 27)
                self.assertEqual(db.execute("SELECT version FROM schema_migrations").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
