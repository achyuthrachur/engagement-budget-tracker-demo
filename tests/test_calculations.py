from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from calculations import (apply_grid_variance, budget_overage_weeks, budget_variance_flag,
                          calculate_status, engagement_metrics,
                          phase_summary, phase_weekly_grid, team_summary)
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
        self.assertAlmostEqual(phase["realization"], 70356/85800, places=10)
        self.assertAlmostEqual(phase["realization"], 0.82, places=10)

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
        self.assertEqual(phase["realization"],0.8)
        self.assertEqual(metrics["realization"],0.7)

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

    def test_team_summary_has_no_per_person_status_field(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 100, 300)
            for item in team_summary(db, eid):
                self.assertNotIn("status", item)
                self.assertNotIn("variance_flagged", item)
                self.assertNotIn("budget_variance_flag", item)

    def test_budget_variance_flag_thresholds(self):
        self.assertIsNone(budget_variance_flag(0, 0))
        self.assertIsNone(budget_variance_flag(0, 50))
        self.assertIsNone(budget_variance_flag(100, 100))
        self.assertEqual(budget_variance_flag(100, 101), "mild")
        self.assertEqual(budget_variance_flag(100, 110), "mild")
        self.assertEqual(budget_variance_flag(100, 111), "severe")

    def test_budget_variance_flag_never_set_when_budgeted_hours_zero(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 0, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,week_end_date,hours,
                 fees_std_rate,fees_contract_rate,matched_phase_id)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (snapshot, eid, "T1", "Smith, Jane", "2026-07-12", 42, 100, 90, pid))
            grid = apply_grid_variance(db, phase_weekly_grid(db, eid, pid))
            cell = grid["rows"][0]["cells"][0]
            self.assertEqual(cell["budgeted_hours"], 0)
            self.assertEqual(cell["actual_hours"], 42)
            self.assertIsNone(cell["budget_variance_flag"])

    def test_budget_variance_flag_is_independent_of_variance_flag(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 100, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,week_end_date,hours,
                 fees_std_rate,fees_contract_rate,matched_phase_id)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (snapshot, eid, "T1", "Smith, Jane", "2026-07-12", 120, 100, 90, pid))
            grid = apply_grid_variance(db, phase_weekly_grid(db, eid, pid))
            cell = grid["rows"][0]["cells"][0]
            self.assertEqual(cell["budget_variance_flag"], "severe")
            self.assertIn("variance_flagged", cell)

    def test_allocation_confidence_is_none_when_phase_has_no_resolved_hours(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 40, 300)
            phase = phase_summary(db, eid)[0]
        self.assertIsNone(phase["allocation_confidence_pct"])

    def test_allocation_confidence_phase_and_engagement_rollup(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 100, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,hours,matched_phase_id,allocation_method)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T1", "Smith, Jane", 10, pid, "direct_match"))
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,hours,matched_phase_id,allocation_method)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T2", "Smith, Jane", 5, pid, "manual_assist"))
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,hours,matched_phase_id,allocation_method)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T3", "Smith, Jane", 3, None, None))
            phase = phase_summary(db, eid)[0]
            metrics = engagement_metrics(db, eid)
        self.assertEqual(phase["allocation_confident_hours"], 10)
        self.assertEqual(phase["allocation_assisted_hours"], 5)
        self.assertAlmostEqual(phase["allocation_confidence_pct"], 10/15)
        self.assertEqual(metrics["allocation_confident_hours"], 10)
        self.assertEqual(metrics["allocation_assisted_hours"], 5)
        self.assertEqual(metrics["allocation_unresolved_hours"], 3)
        # Engagement-level rollup counts confident+assisted as resolved (sticky_rule/staffing_match/
        # single_phase_budget/manual_assist are deterministic resolutions, not guesses) - only the
        # still-unmatched 3 hours should count against it. Phase-level allocation_confidence_pct
        # above answers a different, narrower question (direct/task text-match purity) and is unchanged.
        self.assertAlmostEqual(metrics["allocation_resolved_pct"], 15/18)

    def test_staffing_match_hours_count_as_assisted_not_confident(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 100, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,hours,matched_phase_id,allocation_method)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T1", "Smith, Jane", 4, pid, "staffing_match"))
            phase = phase_summary(db, eid)[0]
        self.assertEqual(phase["allocation_confident_hours"], 0)
        self.assertEqual(phase["allocation_assisted_hours"], 4)
        self.assertEqual(phase["allocation_confidence_pct"], 0)

    def test_phase_can_read_fully_confident_while_engagement_confidence_is_still_flagged(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 100, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,hours,matched_phase_id,allocation_method)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T1", "Smith, Jane", 10, pid, "direct_match"))
            # Unresolved hours belong to no phase, so they can't dilute this phase's own confidence,
            # but they do drag down the engagement-level rollup.
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,hours,matched_phase_id,allocation_method)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T2", "Smith, Jane", 5, None, None))
            phase = phase_summary(db, eid)[0]
            metrics = engagement_metrics(db, eid)
        self.assertEqual(phase["allocation_confidence_pct"], 1.0)
        self.assertAlmostEqual(metrics["allocation_resolved_pct"], 10/15)
        self.assertLess(metrics["allocation_resolved_pct"], metrics["confidence_threshold_pct"])

    def test_calculate_status_distinguishes_actual_overage_from_projected(self):
        self.assertEqual(calculate_status(0.5, 90, 100), "On Track")
        self.assertEqual(calculate_status(0.85, 90, 100), "Watch")
        # Projected (linear-extrapolated) final exceeds the budget, but actual spend to
        # date has not - a forecast, not yet a fact, so it must not read as "Over Budget".
        self.assertEqual(calculate_status(0.5, 120, 100), "Trending Over")
        # Actual spend to date has reached/exceeded the budget - now it's a fact.
        self.assertEqual(calculate_status(1.0, 100, 100), "Over Budget")
        self.assertEqual(calculate_status(1.2, 130, 100), "Over Budget")
        self.assertEqual(calculate_status(0, 0, 0), "On Track")
        self.assertEqual(calculate_status(0, 50, 0), "Over Budget")

    def test_budget_overage_weeks_flags_person_week_exceeding_budget(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 10, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,week_end_date,hours,matched_phase_id)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T1", "Smith, Jane", "2026-07-12", 12, pid))
            overages = budget_overage_weeks(db, eid)
            metrics = engagement_metrics(db, eid)
        self.assertEqual(len(overages), 1)
        overage = overages[0]
        self.assertEqual(overage["team_member_name"], "Smith, Jane")
        self.assertEqual(overage["phase_id"], pid)
        self.assertEqual(overage["week_start_date"], "2026-07-06")
        self.assertEqual(overage["budgeted_hours"], 10)
        self.assertEqual(overage["actual_hours"], 12)
        self.assertEqual(overage["overage_hours"], 2)
        self.assertEqual(overage["severity"], "severe")
        self.assertEqual(metrics["budget_overage_weeks_count"], 1)

    def test_budget_overage_weeks_empty_when_within_budget(self):
        with connect(self.path) as db:
            eid, pid, member, snapshot = self.seed(db, 10000, 10, 300)
            db.execute("""INSERT INTO time_entries
                (snapshot_id,engagement_id,transaction_id,worker_name,week_end_date,hours,matched_phase_id)
                VALUES (?,?,?,?,?,?,?)""", (snapshot, eid, "T1", "Smith, Jane", "2026-07-12", 8, pid))
            overages = budget_overage_weeks(db, eid)
            metrics = engagement_metrics(db, eid)
        self.assertEqual(overages, [])
        self.assertEqual(metrics["budget_overage_weeks_count"], 0)

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
