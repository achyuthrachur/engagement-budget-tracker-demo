from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db import SCHEMA_VERSION, connect, init_db
from migrations import migrate_to_v5, migrate_to_v6, migrate_to_v7, migrate_to_v8, migrate_to_v9, migrate_to_v10


class MigrationTests(unittest.TestCase):
    def test_v1_database_is_backed_up_and_migrated_without_losing_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "legacy.db"
            self._create_v1_fixture(target)
            init_db(target)
            backup = target.with_name("legacy.pre-v4.bak.db")
            self.assertTrue(backup.exists())
            with connect(target) as db:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(engagements)")}
                self.assertIn("complexity_mode", columns)
                self.assertIn("rate_mode", columns)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM engagements").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM time_entries").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM phase_person_weeks").fetchone()[0], 1)
                versions = {row["version"] for row in db.execute("SELECT version FROM schema_migrations")}
                self.assertIn(2, versions)
                self.assertIn(4, versions)
                self.assertIn(SCHEMA_VERSION, versions)

    def test_v4_proposal_pricing_is_backfilled_for_schema_five(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v4.db"
            with connect(target) as db:
                db.executescript(
                    """
                    CREATE TABLE proposals (
                      id INTEGER PRIMARY KEY, proposal_code TEXT, client_name TEXT,
                      first_monday TEXT, duration_weeks INTEGER
                    );
                    CREATE TABLE proposal_people (
                      id INTEGER PRIMARY KEY, proposal_id INTEGER, name TEXT,
                      role TEXT, rough_rate REAL
                    );
                    INSERT INTO proposals VALUES (1, 'P-1', 'Client', '2026-08-17', 2);
                    INSERT INTO proposal_people VALUES (1, 1, 'Smith, Jane', 'Manager FY26', 315);
                    """
                )
                migrate_to_v5(db)
                proposal = db.execute("SELECT * FROM proposals WHERE id=1").fetchone()
                person = db.execute("SELECT * FROM proposal_people WHERE id=1").fetchone()
                self.assertEqual(proposal["rate_basis"], "standard")
                self.assertEqual(proposal["discount_rate"], 0)
                self.assertEqual(person["base_rate"], 315)
                self.assertEqual(person["discount_rate"], 0)

    def test_migrate_to_v6_dedupes_rate_card_rates(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v5.db"
            with connect(target) as db:
                db.executescript(
                    """
                    CREATE TABLE rate_cards (
                      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                      is_active INTEGER DEFAULT 1, created_at TEXT
                    );
                    CREATE TABLE rate_card_rates (
                      id INTEGER PRIMARY KEY, rate_card_id INTEGER NOT NULL,
                      role_name TEXT NOT NULL, standard_rate REAL DEFAULT 0,
                      engagement_rate REAL DEFAULT 0, contract_rate REAL DEFAULT 0,
                      dte_rate REAL DEFAULT 0
                    );
                    CREATE TABLE team_members (
                      id INTEGER PRIMARY KEY, engagement_id INTEGER, name TEXT,
                      role TEXT, created_at TEXT
                    );
                    CREATE TABLE proposals (
                      id INTEGER PRIMARY KEY, proposal_code TEXT, client_name TEXT,
                      first_monday TEXT, duration_weeks INTEGER
                    );
                    CREATE TABLE proposal_people (
                      id INTEGER PRIMARY KEY, proposal_id INTEGER, name TEXT NOT NULL,
                      role TEXT, rough_rate REAL
                    );
                    INSERT INTO rate_cards VALUES (1, 'Current governed rates', 1, '2026-01-01');
                    INSERT INTO rate_card_rates (rate_card_id, role_name, standard_rate, engagement_rate,
                        contract_rate, dte_rate) VALUES
                        (1, 'Manager FY26', 350, 350, 350, 350),
                        (1, 'Manager', 350, 350, 350, 350),
                        (1, 'Partner', 900, 900, 900, 900);
                    INSERT INTO team_members (engagement_id, name, role, created_at) VALUES
                        (1, 'Rao, Anika', 'Manager FY24', '2026-02-01');
                    """
                )
                migrate_to_v6(db)
                rows = db.execute(
                    "SELECT role_name, standard_rate, locked_at FROM rate_card_rates ORDER BY role_name"
                ).fetchall()
                self.assertEqual([r["role_name"] for r in rows], ["Manager", "Partner"])
                manager_row = rows[0]
                self.assertEqual(manager_row["standard_rate"], 350)
                self.assertIsNotNone(manager_row["locked_at"])
                partner_row = rows[1]
                self.assertIsNone(partner_row["locked_at"])
                card = db.execute("SELECT name FROM rate_cards WHERE id=1").fetchone()
                self.assertEqual(card["name"], "FY26 Governed Rates")
                info = db.execute("PRAGMA table_info(proposal_people)").fetchall()
                name_col = next(c for c in info if c["name"] == "name")
                self.assertEqual(name_col["notnull"], 0)

                # idempotency: running again must not change anything or raise
                migrate_to_v6(db)
                rows_again = db.execute(
                    "SELECT role_name, standard_rate, locked_at FROM rate_card_rates ORDER BY role_name"
                ).fetchall()
                self.assertEqual(len(rows_again), 2)
                self.assertEqual(rows_again[0]["locked_at"], manager_row["locked_at"])

    def test_migrate_to_v7_dedupes_bill_rates(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v6.db"
            with connect(target) as db:
                db.executescript(
                    """
                    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
                    CREATE TABLE rate_cards (
                      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                      is_active INTEGER DEFAULT 1, created_at TEXT
                    );
                    CREATE TABLE rate_card_rates (
                      id INTEGER PRIMARY KEY, rate_card_id INTEGER NOT NULL,
                      role_name TEXT NOT NULL, standard_rate REAL DEFAULT 0,
                      engagement_rate REAL DEFAULT 0, contract_rate REAL DEFAULT 0,
                      dte_rate REAL DEFAULT 0
                    );
                    """
                )
                db.execute(
                    "INSERT INTO settings VALUES ('bill_rates', ?)",
                    (json.dumps({
                        "Partner": 850, "Partner FY26": 900,
                        "Offshore Manager FY26": 225, "Staff": 225,
                    }),),
                )
                migrate_to_v7(db)
                rates = json.loads(db.execute(
                    "SELECT value FROM settings WHERE key='bill_rates'"
                ).fetchone()["value"])
                self.assertEqual(rates, {"Partner": 900, "Offshore Manager": 225, "Staff": 225})

                # idempotency: running again must not change anything or raise
                migrate_to_v7(db)
                rates_again = json.loads(db.execute(
                    "SELECT value FROM settings WHERE key='bill_rates'"
                ).fetchone()["value"])
                self.assertEqual(rates_again, rates)

    def test_migrate_to_v8_creates_engagement_drafts_table(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v7.db"
            with connect(target) as db:
                migrate_to_v8(db)
                columns = {row["name"] for row in db.execute("PRAGMA table_info(engagement_drafts)")}
                self.assertEqual(
                    columns,
                    {"id", "engagement_code", "client_name", "step", "wizard_json", "created_at", "updated_at"},
                )
                db.execute(
                    "INSERT INTO engagement_drafts(engagement_code,client_name,step,wizard_json,created_at,updated_at) "
                    "VALUES ('GLC-01','Glacier Bank',4,'{}','2026-08-24T10:00:00','2026-08-24T10:00:00')"
                )
                self.assertEqual(db.execute("SELECT COUNT(*) FROM engagement_drafts").fetchone()[0], 1)

                # idempotency: running again must not raise or duplicate the table
                migrate_to_v8(db)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM engagement_drafts").fetchone()[0], 1)

    def test_migrate_to_v9_adds_allocation_method_and_backfills_direct_match(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v8.db"
            with connect(target) as db:
                db.executescript(
                    """
                    CREATE TABLE engagements (id INTEGER PRIMARY KEY);
                    CREATE TABLE team_members (id INTEGER PRIMARY KEY, engagement_id INTEGER);
                    CREATE TABLE phases (id INTEGER PRIMARY KEY, engagement_id INTEGER);
                    CREATE TABLE import_exceptions (id INTEGER PRIMARY KEY);
                    CREATE TABLE time_entries (
                      id INTEGER PRIMARY KEY, engagement_id INTEGER, matched_phase_id INTEGER
                    );
                    INSERT INTO time_entries (id, engagement_id, matched_phase_id) VALUES
                        (1, 1, 10), (2, 1, NULL);
                    """
                )
                migrate_to_v9(db)
                columns = {row["name"] for row in db.execute("PRAGMA table_info(time_entries)")}
                self.assertIn("allocation_method", columns)
                rows = {row["id"]: row["allocation_method"]
                        for row in db.execute("SELECT id,allocation_method FROM time_entries")}
                self.assertEqual(rows[1], "direct_match")
                self.assertIsNone(rows[2])
                rules_columns = {row["name"] for row in db.execute("PRAGMA table_info(allocation_rules)")}
                self.assertEqual(
                    rules_columns,
                    {"id", "engagement_id", "team_member_id", "phase_id", "created_at",
                     "created_from_exception_id"},
                )

                # idempotency: running again must not raise or clobber a manually-resolved row
                db.execute("UPDATE time_entries SET allocation_method='manual_assist' WHERE id=1")
                migrate_to_v9(db)
                self.assertEqual(
                    db.execute("SELECT allocation_method FROM time_entries WHERE id=1").fetchone()[0],
                    "manual_assist",
                )

    def test_migrate_to_v10_backfills_single_phase_budget_and_sticky_rule_unmatched_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "v9.db"
            with connect(target) as db:
                db.executescript(
                    """
                    CREATE TABLE engagements (id INTEGER PRIMARY KEY);
                    CREATE TABLE team_members (id INTEGER PRIMARY KEY, engagement_id INTEGER);
                    CREATE TABLE phases (id INTEGER PRIMARY KEY, engagement_id INTEGER);
                    CREATE TABLE phase_person_weeks (
                      id INTEGER PRIMARY KEY, phase_id INTEGER, team_member_id INTEGER,
                      week_start_date TEXT, budgeted_hours REAL DEFAULT 0, forecasted_hours REAL DEFAULT 0
                    );
                    CREATE TABLE allocation_rules (
                      id INTEGER PRIMARY KEY, engagement_id INTEGER, team_member_id INTEGER, phase_id INTEGER
                    );
                    CREATE TABLE import_exceptions (
                      id INTEGER PRIMARY KEY, time_entry_id INTEGER, exception_code TEXT,
                      status TEXT, resolution_note TEXT, updated_at TEXT
                    );
                    CREATE TABLE time_entries (
                      id INTEGER PRIMARY KEY, engagement_id INTEGER, matched_team_member_id INTEGER,
                      matched_phase_id INTEGER, allocation_method TEXT
                    );
                    -- Corey: budgeted for exactly one phase (10) anywhere in the engagement.
                    INSERT INTO phase_person_weeks (phase_id, team_member_id, week_start_date, budgeted_hours)
                        VALUES (10, 1, '2026-01-05', 10);
                    -- Jacqueline: budgeted across two phases -- genuinely ambiguous, must stay untouched.
                    INSERT INTO phase_person_weeks (phase_id, team_member_id, week_start_date, budgeted_hours)
                        VALUES (20, 2, '2026-01-05', 10), (21, 2, '2026-01-05', 5);
                    -- Dana: has an explicit sticky rule to phase 30, which should win.
                    INSERT INTO allocation_rules (engagement_id, team_member_id, phase_id) VALUES (1, 3, 30);
                    INSERT INTO time_entries (id, engagement_id, matched_team_member_id, matched_phase_id)
                        VALUES (100, 1, 1, NULL), (200, 1, 2, NULL), (300, 1, 3, NULL);
                    INSERT INTO import_exceptions (id, time_entry_id, exception_code, status)
                        VALUES (1, 100, 'unmatched_phase', 'pending'),
                               (2, 200, 'unmatched_phase', 'pending'),
                               (3, 300, 'unmatched_phase', 'pending');
                    """
                )
                migrate_to_v10(db)
                entries = {row["id"]: (row["matched_phase_id"], row["allocation_method"])
                           for row in db.execute("SELECT id,matched_phase_id,allocation_method FROM time_entries")}
                self.assertEqual(entries[100], (10, "single_phase_budget"))
                self.assertEqual(entries[200], (None, None))
                self.assertEqual(entries[300], (30, "sticky_rule"))
                statuses = {row["id"]: row["status"]
                            for row in db.execute("SELECT id,status FROM import_exceptions")}
                self.assertEqual(statuses[1], "resolved")
                self.assertEqual(statuses[2], "pending")
                self.assertEqual(statuses[3], "resolved")

                # idempotency: running again must not raise or clobber a manually-resolved row
                db.execute("UPDATE time_entries SET matched_phase_id=99,allocation_method='manual_assist' "
                           "WHERE id=200")
                migrate_to_v10(db)
                row = db.execute("SELECT matched_phase_id,allocation_method FROM time_entries WHERE id=200").fetchone()
                self.assertEqual((row["matched_phase_id"], row["allocation_method"]), (99, "manual_assist"))

    def _create_v1_fixture(self, path: Path) -> None:
        db = sqlite3.connect(path)
        try:
            db.executescript(
                """
                CREATE TABLE engagements (
                  id INTEGER PRIMARY KEY,
                  engagement_code TEXT NOT NULL,
                  client_name TEXT NOT NULL,
                  model_type TEXT,
                  model_vendor TEXT,
                  engagement_lead TEXT,
                  first_week_with_entry TEXT,
                  status TEXT,
                  c360_used INTEGER,
                  c360_amount REAL,
                  bima_amount REAL,
                  max_sow_fees REAL,
                  change_order_amt REAL,
                  created_at TEXT,
                  updated_at TEXT
                );
                CREATE TABLE team_members (
                  id INTEGER PRIMARY KEY,
                  engagement_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  role TEXT,
                  internal_rate REAL,
                  engagement_rate REAL,
                  budgeted_hours REAL
                );
                CREATE TABLE phases (
                  id INTEGER PRIMARY KEY,
                  engagement_id INTEGER NOT NULL,
                  phase_name TEXT,
                  sort_order INTEGER,
                  budgeted_hours REAL,
                  budgeted_eng_fees REAL
                );
                CREATE TABLE weekly_snapshots (
                  id INTEGER PRIMARY KEY,
                  engagement_id INTEGER NOT NULL,
                  week_end_date TEXT,
                  imported_at TEXT,
                  row_count INTEGER,
                  notes TEXT
                );
                CREATE TABLE time_entries (
                  id INTEGER PRIMARY KEY,
                  snapshot_id INTEGER NOT NULL,
                  engagement_id INTEGER NOT NULL,
                  transaction_id TEXT,
                  worker_name TEXT,
                  worker_id TEXT,
                  title TEXT,
                  entry_date TEXT,
                  week_end_date TEXT,
                  financial_period TEXT,
                  phase_desc TEXT,
                  task_desc TEXT,
                  work_location TEXT,
                  billing_status TEXT,
                  hours REAL,
                  fees_std_rate REAL,
                  fees_contract_rate REAL,
                  memo TEXT
                );
                CREATE TABLE budget_adjustments (
                  id INTEGER PRIMARY KEY,
                  engagement_id INTEGER NOT NULL,
                  adjustment_type TEXT,
                  effective_date TEXT,
                  amount REAL,
                  description TEXT,
                  created_at TEXT
                );
                CREATE TABLE settings (
                  key TEXT PRIMARY KEY,
                  value TEXT
                );
                """
            )
            db.execute(
                """INSERT INTO engagements
                (id, engagement_code, client_name, model_type, model_vendor, engagement_lead,
                 first_week_with_entry, status, c360_used, c360_amount, bima_amount,
                 max_sow_fees, change_order_amt, created_at, updated_at)
                VALUES (1, 'LEG-1', 'Legacy Client', 'TM', 'Vendor', 'Lead, Alex',
                        '2026-07-06', 'open', 0, 0, 0, 10000, 0, '2026-07-01T09:00:00', '2026-07-01T09:00:00')"""
            )
            db.execute(
                """INSERT INTO team_members
                (id, engagement_id, name, role, internal_rate, engagement_rate, budgeted_hours)
                VALUES (1, 1, 'Smith, Jane', 'Manager', 300, 280, 40)"""
            )
            db.execute(
                """INSERT INTO weekly_snapshots
                (id, engagement_id, week_end_date, imported_at, row_count, notes)
                VALUES (1, 1, '2026-07-12', '2026-07-13T09:00:00', 2, 'Legacy import')"""
            )
            db.execute(
                """INSERT INTO time_entries
                (id, snapshot_id, engagement_id, transaction_id, worker_name, worker_id, title,
                 entry_date, week_end_date, financial_period, phase_desc, task_desc, work_location,
                 billing_status, hours, fees_std_rate, fees_contract_rate, memo)
                VALUES
                (1, 1, 1, 'T1', 'Smith, Jane', 'W1', 'Manager', '2026-07-06', '2026-07-12',
                 '2026-07', '', 'Task', 'Remote', 'Billable', 8, 2400, 2240, 'One'),
                (2, 1, 1, 'T2', 'Smith, Jane', 'W1', 'Manager', '2026-07-07', '2026-07-12',
                 '2026-07', '', 'Task', 'Remote', 'Billable', 6, 1800, 1680, 'Two')"""
            )
            db.execute("INSERT INTO settings(key, value) VALUES ('variance_threshold_hours', '6')")
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
