from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path


def _monday(value):
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value)[:10])
        return (parsed - timedelta(days=parsed.weekday())).isoformat()
    except ValueError:
        return str(value)[:10]


def migrate_v1_to_v2(target: Path, schema: Path, timestamp: str) -> None:
    db = sqlite3.connect(target)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = OFF")
    tables = ["engagements", "team_members", "phases", "weekly_snapshots",
              "time_entries", "budget_adjustments", "settings"]
    try:
        for table in tables:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if exists:
                db.execute(f"ALTER TABLE {table} RENAME TO {table}_v1")
        db.executescript(schema.read_text(encoding="utf-8"))

        phase_ids: dict[int, list[int]] = {}
        phase_names: dict[int, dict[str, int]] = {}
        engagements = db.execute("SELECT * FROM engagements_v1 ORDER BY id").fetchall()
        for item in engagements:
            eid = int(item["id"])
            old_phases = db.execute(
                "SELECT * FROM phases_v1 WHERE engagement_id=? ORDER BY sort_order, id", (eid,)
            ).fetchall()
            imported = db.execute(
                "SELECT 1 FROM weekly_snapshots_v1 WHERE engagement_id=? LIMIT 1", (eid,)
            ).fetchone()
            status = "closed" if str(item["status"] or "").lower() == "closed" else (
                "active" if imported else "planning"
            )
            db.execute(
                """INSERT INTO engagements
                (id, engagement_code, client_name, complexity_mode, model_type, model_vendor,
                 engagement_lead, first_monday, duration_weeks, status, c360_used,
                 c360_amount, bima_amount, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 12, ?, ?, ?, ?, ?, ?)""",
                (eid, item["engagement_code"], item["client_name"],
                 "complex" if old_phases else "simple", item["model_type"],
                 item["model_vendor"], item["engagement_lead"],
                 _monday(item["first_week_with_entry"]), status, int(item["c360_used"] or 0),
                 float(item["c360_amount"] or 0), float(item["bima_amount"] or 0),
                 item["created_at"], item["updated_at"]),
            )
            phase_ids[eid] = []
            phase_names[eid] = {}
            _migrate_phases(db, item, old_phases, phase_ids[eid], phase_names[eid], timestamp)

        for member in db.execute("SELECT * FROM team_members_v1 ORDER BY id").fetchall():
            db.execute(
                """INSERT INTO team_members
                (id, engagement_id, name, role, internal_rate, engagement_rate,
                 contract_rate, dte_rate, is_offshore, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                (member["id"], member["engagement_id"], member["name"], member["role"],
                 member["internal_rate"], member["engagement_rate"],
                 member["engagement_rate"], timestamp),
            )
            eid = int(member["engagement_id"])
            weights = _phase_weights(db, phase_ids[eid])
            for pid, weight in zip(phase_ids[eid], weights):
                db.execute(
                    """INSERT INTO phase_person_weeks
                    (phase_id, team_member_id, week_start_date, budgeted_hours, forecasted_hours)
                    VALUES (?, ?, NULL, ?, 0)""",
                    (pid, member["id"], float(member["budgeted_hours"] or 0) * weight),
                )

        db.execute("""INSERT INTO weekly_snapshots
            (id, engagement_id, week_end_date, imported_at, row_count, notes)
            SELECT id, engagement_id, week_end_date, imported_at, row_count, notes
            FROM weekly_snapshots_v1""")
        for entry in db.execute("SELECT * FROM time_entries_v1 ORDER BY id").fetchall():
            matched = phase_names[int(entry["engagement_id"])].get(
                str(entry["phase_desc"] or "").strip().lower()
            )
            db.execute(
                """INSERT INTO time_entries
                (id, snapshot_id, engagement_id, transaction_id, worker_name, worker_id,
                 title, entry_date, week_end_date, financial_period, phase_desc, task_desc,
                 work_location, billing_status, hours, fees_std_rate, fees_contract_rate,
                 memo, matched_phase_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry["id"], entry["snapshot_id"], entry["engagement_id"],
                 entry["transaction_id"], entry["worker_name"], entry["worker_id"],
                 entry["title"], entry["entry_date"], entry["week_end_date"],
                 entry["financial_period"], entry["phase_desc"], entry["task_desc"],
                 entry["work_location"], entry["billing_status"], entry["hours"],
                 entry["fees_std_rate"], entry["fees_contract_rate"], entry["memo"], matched),
            )
        _migrate_adjustments(db, engagements, phase_ids, timestamp)
        db.execute("INSERT OR REPLACE INTO settings SELECT * FROM settings_v1")
        db.execute("INSERT INTO schema_migrations VALUES (2, ?)", (timestamp,))
        for table in reversed(tables):
            db.execute(f"DROP TABLE IF EXISTS {table}_v1")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _migrate_phases(db, engagement, old_phases, ids, names, timestamp):
    eid = int(engagement["id"])
    if not old_phases:
        cursor = db.execute(
            """INSERT INTO phases
            (engagement_id, phase_name, sow_fees, sort_order, is_default, created_at)
            VALUES (?, 'General', ?, 0, 1, ?)""",
            (eid, float(engagement["max_sow_fees"] or 0), timestamp),
        )
        ids.append(int(cursor.lastrowid))
        names["general"] = int(cursor.lastrowid)
        return
    fee_total = sum(float(p["budgeted_eng_fees"] or 0) for p in old_phases)
    hour_total = sum(float(p["budgeted_hours"] or 0) for p in old_phases)
    for index, phase in enumerate(old_phases):
        if fee_total:
            weight = float(phase["budgeted_eng_fees"] or 0) / fee_total
        elif hour_total:
            weight = float(phase["budgeted_hours"] or 0) / hour_total
        else:
            weight = 1 / len(old_phases)
        pid = int(phase["id"])
        db.execute(
            """INSERT INTO phases
            (id, engagement_id, phase_name, phase_code, sow_fees, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pid, eid, phase["phase_name"], phase["phase_name"],
             float(engagement["max_sow_fees"] or 0) * weight,
             int(phase["sort_order"] or index), timestamp),
        )
        ids.append(pid)
        names[str(phase["phase_name"] or "").strip().lower()] = pid


def _phase_weights(db, ids):
    values = []
    for pid in ids:
        row = db.execute("SELECT budgeted_hours FROM phases_v1 WHERE id=?", (pid,)).fetchone()
        values.append(float(row["budgeted_hours"] or 0) if row else 0)
    total = sum(values)
    if total:
        return [value / total for value in values]
    return [1.0] + [0.0] * (len(ids) - 1)


def _migrate_adjustments(db, engagements, phase_ids, timestamp):
    seen: dict[int, set[str]] = {}
    for item in db.execute("SELECT * FROM budget_adjustments_v1 ORDER BY id").fetchall():
        eid = int(item["engagement_id"])
        kind = str(item["adjustment_type"] or "markdown").lower()
        amount = float(item["amount"] or 0)
        if kind in {"markdown", "bima"}:
            amount = -abs(amount)
        phase_id = phase_ids[eid][0] if kind == "change_order" else None
        db.execute(
            """INSERT INTO budget_adjustments
            (id, engagement_id, phase_id, adjustment_type, effective_date,
             amount, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (item["id"], eid, phase_id, kind, item["effective_date"], amount,
             item["description"], item["created_at"]),
        )
        seen.setdefault(eid, set()).add(kind)
    for engagement in engagements:
        eid = int(engagement["id"])
        values = [
            ("change_order", float(engagement["change_order_amt"] or 0)),
            ("c360", float(engagement["c360_amount"] or 0)),
            ("bima", -abs(float(engagement["bima_amount"] or 0))),
        ]
        for kind, amount in values:
            if not amount or kind in seen.get(eid, set()):
                continue
            phase_id = phase_ids[eid][0] if kind == "change_order" else None
            db.execute(
                """INSERT INTO budget_adjustments
                (engagement_id, phase_id, adjustment_type, amount, description, created_at)
                VALUES (?, ?, ?, ?, 'Migrated from v1', ?)""",
                (eid, phase_id, kind, amount, timestamp),
            )
