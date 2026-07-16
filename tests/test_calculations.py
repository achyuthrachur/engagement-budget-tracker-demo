from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from calculations import engagement_metrics, phase_summary, team_summary
from db import connect, init_db, now_iso


class CalculationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "calc.db"
        init_db(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_republic_phase_one_realization_matches_workbook(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 85000, 294, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,week_end_date,hours,
                 fees_std_rate,fees_contract_rate,matched_phase_id)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (snapshot,eid,"T1","Smith, Jane","2026-07-12",250.5,85800,70356,pid))
            phase = phase_summary(db,eid)[0]
        self.assertAlmostEqual(phase["realization"], 85000/85800, places=10)
        self.assertAlmostEqual(phase["realization"], 0.9906759906759907, places=10)

    def test_imported_actual_fees_are_not_recomputed(self):
        with connect(self.path) as db:
            eid,pid,member,snapshot=self.seed(db,10000,20,999)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,week_end_date,hours,
                 fees_std_rate,fees_contract_rate,matched_phase_id)
                VALUES (?,?,?,?,?,?,?,?,?)""",(snapshot,eid,"T1","Smith, Jane","2026-07-12",2,226.1201,152.5904,pid))
            phase=phase_summary(db,eid)[0]
        self.assertEqual(phase["actual_std_fees"],226.12)
        self.assertEqual(phase["actual_contract_fees"],152.59)
        self.assertNotEqual(phase["actual_contract_fees"],1998)

    def test_engagement_expense_is_counted_once_and_not_repeated_per_phase(self):
        with connect(self.path) as db:
            eid,pid,member,snapshot=self.seed(db,10000,20,300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,week_end_date,hours,
                 fees_std_rate,fees_contract_rate,matched_phase_id)
                VALUES (?,?,?,?,?,?,?,?,?)""",(snapshot,eid,"T1","Smith, Jane","2026-07-12",10,1000,800,pid))
            db.execute("INSERT INTO expenses (engagement_id,expense_type,amount) VALUES (?,'crowe_paid',100)",(eid,))
            phase=phase_summary(db,eid)[0]
            metrics=engagement_metrics(db,eid)
        self.assertEqual(phase["crowe_expenses"],0)
        self.assertEqual(phase["realization"],10)
        self.assertEqual(metrics["realization"],9.9)

    def test_team_rollup_uses_phase_budget_and_engagement_rate(self):
        with connect(self.path) as db:
            eid,pid,member,snapshot=self.seed(db,10000,40,300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,hours,fees_contract_rate)
                VALUES (?,?,?,?,?,?)""",(snapshot,eid,"T1","Smith, Jane",10,2500))
            team=team_summary(db,eid)[0]
        self.assertEqual(team["budgeted_hours"],40)
        self.assertEqual(team["hours_remaining"],30)
        self.assertEqual(team["actual_eng_fees"],3000)

    def seed(self, db, sow, hours, engagement_rate):
        eid=db.execute("""INSERT INTO engagements
            (engagement_code,client_name,complexity_mode,status,created_at,updated_at)
            VALUES ('P1','Client','complex','active',?,?)""",(now_iso(),now_iso())).lastrowid
        pid=db.execute("""INSERT INTO phases
            (engagement_id,phase_name,phase_code,sow_fees,created_at) VALUES (?,'Phase 1','A',?,?)""",
            (eid,sow,now_iso())).lastrowid
        member=db.execute("""INSERT INTO team_members
            (engagement_id,name,internal_rate,engagement_rate,contract_rate,dte_rate)
            VALUES (?,'Smith, Jane',350,?,280,320)""",(eid,engagement_rate)).lastrowid
        db.execute("""INSERT INTO phase_person_weeks
            (phase_id,team_member_id,week_start_date,budgeted_hours) VALUES (?,?,?,?)""",
            (pid,member,"2026-07-06",hours))
        snapshot=db.execute("""INSERT INTO weekly_snapshots
            (engagement_id,week_end_date,imported_at,row_count) VALUES (?,'2026-07-12',?,1)""",
            (eid,now_iso())).lastrowid
        return eid,pid,member,snapshot


if __name__ == "__main__":
    unittest.main()
