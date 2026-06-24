from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import connect, init_db, now_iso


def insert_engagement(conn, code, client, sow, status="Active", change_order=0, c360=0, bima=0):
    return conn.execute(
        """
        INSERT INTO engagements (
          engagement_code, client_name, model_type, model_vendor, engagement_lead,
          first_week_with_entry, max_sow_fees, change_order_amt, c360_used,
          c360_amount, bima_amount, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            code,
            client,
            "Credit Risk",
            "Demo Model Platform",
            "Engagement Lead",
            "2026-04-04",
            sow,
            change_order,
            1 if c360 else 0,
            c360,
            bima,
            status,
            now_iso(),
            now_iso(),
        ),
    ).lastrowid


def insert_team(conn, engagement_id, members):
    conn.executemany(
        """
        INSERT INTO team_members (
          engagement_id, name, role, internal_rate, engagement_rate, budgeted_hours
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(engagement_id, *member) for member in members],
    )


def insert_phases(conn, engagement_id):
    phases = [
        (engagement_id, "Planning", 12, 4200, 0),
        (engagement_id, "Fieldwork", 48, 14600, 1),
        (engagement_id, "Reporting", 18, 5200, 2),
    ]
    conn.executemany(
        """
        INSERT INTO phases (engagement_id, phase_name, budgeted_hours, budgeted_eng_fees, sort_order)
        VALUES (?, ?, ?, ?, ?)
        """,
        phases,
    )


def insert_adjustment(conn, engagement_id, date, kind, amount, description):
    conn.execute(
        """
        INSERT INTO budget_adjustments (
          engagement_id, effective_date, adjustment_type, amount, description, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (engagement_id, date, kind, amount, description, now_iso()),
    )


def insert_week(conn, engagement_id, week_end, rows, notes=""):
    snapshot_id = conn.execute(
        """
        INSERT INTO weekly_snapshots (engagement_id, week_end_date, imported_at, row_count, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (engagement_id, week_end, now_iso(), len(rows), notes),
    ).lastrowid
    for index, row in enumerate(rows, start=1):
        worker, title, entry_date, phase, hours, rate, memo = row
        conn.execute(
            """
            INSERT INTO time_entries (
              snapshot_id, engagement_id, transaction_id, worker_name, worker_id, title,
              entry_date, week_end_date, financial_period, phase_desc, task_desc,
              work_location, billing_status, hours, fees_std_rate, fees_contract_rate, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                engagement_id,
                f"DEMO-{engagement_id}-{week_end}-{index}",
                worker,
                f"D{engagement_id:02d}{index:03d}",
                title,
                entry_date,
                week_end,
                week_end[:7],
                phase,
                phase,
                "Remote",
                "Billable",
                hours,
                hours * rate,
                hours * rate,
                memo,
            ),
        )


def seed():
    db_file = ROOT / "demo_seed.db"
    if db_file.exists():
        db_file.unlink()
    init_db(db_file)
    with connect(db_file) as conn:
        alpha = insert_engagement(conn, "DEMO-ALPHA-001", "Demo Client Alpha", 24000)
        insert_team(conn, alpha, [("Analyst One", "Staff", 225, 225, 55), ("Manager Two", "Senior Manager", 500, 500, 15), ("Partner Three", "Partner", 900, 900, 5), ("Project Services", "Project Services", 175, 175, 5)])
        insert_phases(conn, alpha)
        insert_adjustment(conn, alpha, "2026-05-20", "bima", 1950, "Synthetic BIMA reduction")
        for week, rows in [
            ("2026-04-04", [("Partner Three", "Partner", "2026-03-31", "Planning", 0.75, 900, "Kickoff planning"), ("Manager Two", "Senior Manager", "2026-04-01", "Planning", 1.25, 500, "Initial workplan")]),
            ("2026-04-11", [("Analyst One", "Staff", "2026-04-07", "Fieldwork", 5.0, 225, "Data intake"), ("Manager Two", "Senior Manager", "2026-04-08", "Fieldwork", 2.0, 500, "Review and coaching")]),
            ("2026-04-18", [("Analyst One", "Staff", "2026-04-14", "Fieldwork", 9.5, 225, "Model analysis"), ("Project Services", "Project Services", "2026-04-15", "Fieldwork", 1.5, 175, "Formatting support")]),
            ("2026-04-25", [("Analyst One", "Staff", "2026-04-21", "Fieldwork", 12.0, 225, "Testing"), ("Manager Two", "Senior Manager", "2026-04-22", "Fieldwork", 3.25, 500, "Issue review")]),
            ("2026-05-02", [("Analyst One", "Staff", "2026-04-28", "Reporting", 8.0, 225, "Draft reporting"), ("Manager Two", "Senior Manager", "2026-04-29", "Reporting", 2.5, 500, "Draft review")]),
            ("2026-05-09", [("Analyst One", "Staff", "2026-05-05", "Reporting", 6.0, 225, "Final updates"), ("Partner Three", "Partner", "2026-05-06", "Reporting", 1.0, 900, "Final review")]),
        ]:
            insert_week(conn, alpha, week, rows)

        beta = insert_engagement(conn, "DEMO-BETA-002", "Demo Client Beta", 25000, change_order=2500, c360=750)
        insert_team(conn, beta, [("Consultant Four", "Manager", 350, 350, 30), ("Analyst Five", "Staff", 225, 225, 45), ("Reviewer Six", "Senior Manager", 500, 500, 8)])
        insert_phases(conn, beta)
        for week, rows in [
            ("2026-04-11", [("Consultant Four", "Manager", "2026-04-08", "Planning", 4.0, 350, "Planning"), ("Analyst Five", "Staff", "2026-04-09", "Fieldwork", 6.0, 225, "Data prep")]),
            ("2026-04-18", [("Consultant Four", "Manager", "2026-04-15", "Fieldwork", 7.0, 350, "Analysis"), ("Analyst Five", "Staff", "2026-04-16", "Fieldwork", 11.0, 225, "Testing")]),
            ("2026-04-25", [("Reviewer Six", "Senior Manager", "2026-04-22", "Reporting", 2.5, 500, "Quality review"), ("Analyst Five", "Staff", "2026-04-23", "Reporting", 8.0, 225, "Report drafting")]),
        ]:
            insert_week(conn, beta, week, rows)

        gamma = insert_engagement(conn, "DEMO-GAMMA-003", "Demo Client Gamma", 15000, status="Closed")
        insert_team(conn, gamma, [("Advisor Seven", "Manager", 350, 350, 20), ("Analyst Eight", "Senior Staff", 300, 300, 24)])
        insert_phases(conn, gamma)
        insert_adjustment(conn, gamma, "2026-03-22", "markdown", 500, "Synthetic final discount")
        for week, rows in [
            ("2026-03-14", [("Advisor Seven", "Manager", "2026-03-11", "Planning", 5.0, 350, "Planning"), ("Analyst Eight", "Senior Staff", "2026-03-12", "Fieldwork", 8.0, 300, "Fieldwork")]),
            ("2026-03-21", [("Advisor Seven", "Manager", "2026-03-18", "Reporting", 4.0, 350, "Review"), ("Analyst Eight", "Senior Staff", "2026-03-19", "Reporting", 9.0, 300, "Reporting")]),
        ]:
            insert_week(conn, gamma, week, rows)
    print(db_file)


if __name__ == "__main__":
    seed()
