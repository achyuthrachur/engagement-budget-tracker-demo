from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path


def _has_column(db: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in db.execute(f"PRAGMA table_info({table})").fetchall())


def normalize_role_key(role) -> str:
    text = re.sub(r"\s+FY\d{2}\s*$", "", str(role or "").strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip().casefold()


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


def migrate_to_v4(db: sqlite3.Connection) -> None:
    if not _has_column(db, "engagements", "rate_mode"):
        db.execute(
            "ALTER TABLE engagements ADD COLUMN rate_mode TEXT DEFAULT 'governed' "
            "CHECK (rate_mode IN ('governed', 'custom', 'flat_tiered'))"
        )
    if not _has_column(db, "engagements", "flat_tier_notes"):
        db.execute("ALTER TABLE engagements ADD COLUMN flat_tier_notes TEXT")
    if not _has_column(db, "team_members", "custom_rate_note"):
        db.execute("ALTER TABLE team_members ADD COLUMN custom_rate_note TEXT")
    if not _has_column(db, "team_members", "rate_tier_id"):
        db.execute("ALTER TABLE team_members ADD COLUMN rate_tier_id INTEGER REFERENCES engagement_rate_tiers(id) ON DELETE SET NULL")
    if not _has_column(db, "team_members", "is_custom_rate"):
        db.execute("ALTER TABLE team_members ADD COLUMN is_custom_rate INTEGER DEFAULT 0 CHECK (is_custom_rate IN (0,1))")
    if not _has_column(db, "time_entries", "normalized_worker_name"):
        db.execute("ALTER TABLE time_entries ADD COLUMN normalized_worker_name TEXT")
    if not _has_column(db, "time_entries", "is_excluded"):
        db.execute("ALTER TABLE time_entries ADD COLUMN is_excluded INTEGER DEFAULT 0 CHECK (is_excluded IN (0,1))")
    if not _has_column(db, "time_entries", "exclusion_reason"):
        db.execute("ALTER TABLE time_entries ADD COLUMN exclusion_reason TEXT")
    if not _has_column(db, "time_entries", "matched_team_member_id"):
        db.execute("ALTER TABLE time_entries ADD COLUMN matched_team_member_id INTEGER REFERENCES team_members(id) ON DELETE SET NULL")
    if not _has_column(db, "weekly_snapshots", "covered_start_date"):
        db.execute("ALTER TABLE weekly_snapshots ADD COLUMN covered_start_date TEXT")
    if not _has_column(db, "weekly_snapshots", "covered_end_date"):
        db.execute("ALTER TABLE weekly_snapshots ADD COLUMN covered_end_date TEXT")
    if not _has_column(db, "weekly_snapshots", "realization_value"):
        db.execute("ALTER TABLE weekly_snapshots ADD COLUMN realization_value REAL")
    if not _has_column(db, "weekly_snapshots", "realization_delta"):
        db.execute("ALTER TABLE weekly_snapshots ADD COLUMN realization_delta REAL")
    for column in ("rows_inserted", "rows_updated", "rows_removed"):
        if not _has_column(db, "weekly_snapshots", column):
            db.execute(f"ALTER TABLE weekly_snapshots ADD COLUMN {column} INTEGER DEFAULT 0")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS proposals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          proposal_code TEXT NOT NULL UNIQUE,
          client_name TEXT NOT NULL,
          engagement_type TEXT,
          first_monday TEXT,
          duration_weeks INTEGER DEFAULT 1 CHECK (duration_weeks IS NULL OR duration_weeks > 0),
          notes TEXT,
          created_at TEXT,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS proposal_people (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          role TEXT,
          rough_rate REAL,
          created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS proposal_person_weeks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          proposal_person_id INTEGER NOT NULL REFERENCES proposal_people(id) ON DELETE CASCADE,
          week_start_date TEXT,
          budgeted_hours REAL DEFAULT 0,
          forecasted_hours REAL
        );
        CREATE TABLE IF NOT EXISTS rate_cards (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          is_active INTEGER DEFAULT 1 CHECK (is_active IN (0,1)),
          created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS rate_card_rates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          rate_card_id INTEGER NOT NULL REFERENCES rate_cards(id) ON DELETE CASCADE,
          role_name TEXT NOT NULL,
          standard_rate REAL DEFAULT 0,
          engagement_rate REAL DEFAULT 0,
          contract_rate REAL DEFAULT 0,
          dte_rate REAL DEFAULT 0,
          UNIQUE (rate_card_id, role_name COLLATE NOCASE)
        );
        CREATE TABLE IF NOT EXISTS engagement_rate_tiers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          engagement_id INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
          tier_name TEXT NOT NULL,
          tier_amount REAL DEFAULT 0,
          tier_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS import_exceptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          engagement_id INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
          transaction_id TEXT,
          worker_name TEXT,
          normalized_worker_name TEXT,
          phase_desc TEXT,
          exception_code TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'resolved', 'excluded')),
          hours REAL DEFAULT 0,
          fees_contract_rate REAL DEFAULT 0,
          snapshot_id INTEGER REFERENCES weekly_snapshots(id) ON DELETE SET NULL,
          created_at TEXT,
          updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_import_exceptions_engagement
          ON import_exceptions(engagement_id, status);
        """
    )
    if not _has_column(db, "proposals", "status"):
        db.execute("ALTER TABLE proposals ADD COLUMN status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','converted','archived'))")
    if not _has_column(db, "proposals", "converted_engagement_id"):
        db.execute("ALTER TABLE proposals ADD COLUMN converted_engagement_id INTEGER REFERENCES engagements(id) ON DELETE SET NULL")
    if not _has_column(db, "import_exceptions", "time_entry_id"):
        db.execute("ALTER TABLE import_exceptions ADD COLUMN time_entry_id INTEGER REFERENCES time_entries(id) ON DELETE CASCADE")
    if not _has_column(db, "import_exceptions", "resolution_note"):
        db.execute("ALTER TABLE import_exceptions ADD COLUMN resolution_note TEXT")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_import_exceptions_entry_code "
        "ON import_exceptions(time_entry_id, exception_code) WHERE time_entry_id IS NOT NULL"
    )
    db.execute(
        "UPDATE time_entries SET normalized_worker_name=LOWER(TRIM(COALESCE(worker_name,''))) "
        "WHERE normalized_worker_name IS NULL"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_time_entries_normalized_worker "
        "ON time_entries(engagement_id, normalized_worker_name, week_end_date)"
    )
    db.execute(
        "UPDATE time_entries SET matched_team_member_id=(SELECT tm.id FROM team_members tm "
        "WHERE tm.engagement_id=time_entries.engagement_id "
        "AND LOWER(TRIM(tm.name))=time_entries.normalized_worker_name LIMIT 1) "
        "WHERE matched_team_member_id IS NULL"
    )


def migrate_to_v5(db: sqlite3.Connection) -> None:
    if not _has_column(db, "proposals", "rate_basis"):
        db.execute(
            "ALTER TABLE proposals ADD COLUMN rate_basis TEXT NOT NULL DEFAULT 'standard' "
            "CHECK (rate_basis IN ('standard','engagement','contract'))"
        )
    if not _has_column(db, "proposals", "discount_rate"):
        db.execute(
            "ALTER TABLE proposals ADD COLUMN discount_rate REAL NOT NULL DEFAULT 0 "
            "CHECK (discount_rate BETWEEN 0 AND 1)"
        )
    if not _has_column(db, "proposal_people", "base_rate"):
        db.execute("ALTER TABLE proposal_people ADD COLUMN base_rate REAL")
    if not _has_column(db, "proposal_people", "discount_rate"):
        db.execute(
            "ALTER TABLE proposal_people ADD COLUMN discount_rate REAL NOT NULL DEFAULT 0 "
            "CHECK (discount_rate BETWEEN 0 AND 1)"
        )
    db.execute(
        "UPDATE proposal_people SET base_rate=rough_rate "
        "WHERE base_rate IS NULL AND rough_rate IS NOT NULL"
    )


def _as_float(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe_rate_card_rates(db: sqlite3.Connection) -> None:
    cards = db.execute("SELECT id FROM rate_cards").fetchall()
    for card in cards:
        card_id = int(card["id"])
        rows = db.execute(
            "SELECT * FROM rate_card_rates WHERE rate_card_id=? ORDER BY id", (card_id,)
        ).fetchall()
        groups: dict[str, list] = {}
        for row in rows:
            groups.setdefault(normalize_role_key(row["role_name"]), []).append(row)
        for group_rows in groups.values():
            plain_rows = [r for r in group_rows if not re.search(r"FY\d{2}\s*$", r["role_name"], re.IGNORECASE)]
            canonical = plain_rows[0] if plain_rows else group_rows[0]
            plain_name = re.sub(r"\s+FY\d{2}\s*$", "", str(canonical["role_name"]), flags=re.IGNORECASE).strip()
            for row in group_rows:
                if row["id"] == canonical["id"]:
                    continue
                if _as_float(row["standard_rate"]) > _as_float(canonical["standard_rate"]):
                    db.execute(
                        """UPDATE rate_card_rates SET standard_rate=?,engagement_rate=?,
                        contract_rate=?,dte_rate=? WHERE id=?""",
                        (row["standard_rate"], row["engagement_rate"], row["contract_rate"],
                         row["dte_rate"], canonical["id"]),
                    )
                db.execute("DELETE FROM rate_card_rates WHERE id=?", (row["id"],))
            if plain_name != canonical["role_name"]:
                db.execute("UPDATE rate_card_rates SET role_name=? WHERE id=?", (plain_name, canonical["id"]))


def _backfill_rate_lock(db: sqlite3.Connection) -> None:
    earliest_by_role: dict[str, str] = {}
    for row in db.execute("SELECT role, created_at FROM team_members WHERE created_at IS NOT NULL"):
        key = normalize_role_key(row["role"])
        if not key:
            continue
        if key not in earliest_by_role or str(row["created_at"]) < earliest_by_role[key]:
            earliest_by_role[key] = str(row["created_at"])
    unlocked = db.execute(
        "SELECT id, role_name FROM rate_card_rates WHERE locked_at IS NULL"
    ).fetchall()
    for row in unlocked:
        stamp = earliest_by_role.get(normalize_role_key(row["role_name"]))
        if stamp:
            db.execute("UPDATE rate_card_rates SET locked_at=? WHERE id=? AND locked_at IS NULL",
                       (stamp, int(row["id"])))


def _make_proposal_people_name_nullable(db: sqlite3.Connection) -> None:
    info = db.execute("PRAGMA table_info(proposal_people)").fetchall()
    name_col = next((c for c in info if c["name"] == "name"), None)
    if not name_col or not name_col["notnull"]:
        return
    existing_cols = {c["name"] for c in info}
    target_cols = ["id", "proposal_id", "name", "role", "base_rate", "discount_rate", "rough_rate", "created_at"]
    select_exprs = []
    for col in target_cols:
        if col in existing_cols:
            select_exprs.append(col)
        elif col == "discount_rate":
            select_exprs.append("0")
        else:
            select_exprs.append("NULL")
    db.execute(
        """CREATE TABLE proposal_people_new (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          proposal_id       INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
          name              TEXT,
          role              TEXT,
          base_rate         REAL,
          discount_rate     REAL NOT NULL DEFAULT 0 CHECK (discount_rate BETWEEN 0 AND 1),
          rough_rate        REAL,
          created_at        TEXT
        )"""
    )
    db.execute(
        f"INSERT INTO proposal_people_new ({','.join(target_cols)}) "
        f"SELECT {','.join(select_exprs)} FROM proposal_people"
    )
    db.execute("DROP TABLE proposal_people")
    db.execute("ALTER TABLE proposal_people_new RENAME TO proposal_people")


def migrate_to_v6(db: sqlite3.Connection) -> None:
    if not _has_column(db, "rate_card_rates", "locked_at"):
        db.execute("ALTER TABLE rate_card_rates ADD COLUMN locked_at TEXT")
    _dedupe_rate_card_rates(db)
    db.execute("UPDATE rate_cards SET name='FY26 Governed Rates' WHERE name='Current governed rates'")
    _backfill_rate_lock(db)
    _make_proposal_people_name_nullable(db)


def _dedupe_bill_rates(db: sqlite3.Connection) -> None:
    row = db.execute("SELECT value FROM settings WHERE key='bill_rates'").fetchone()
    if not row or not row["value"]:
        return
    try:
        rates = json.loads(row["value"])
    except (TypeError, ValueError):
        return
    if not isinstance(rates, dict) or not rates:
        return
    groups: dict[str, list[str]] = {}
    for role_name in rates:
        groups.setdefault(normalize_role_key(role_name), []).append(role_name)
    cleaned: dict[str, float] = {}
    for names in groups.values():
        fy_names = [n for n in names if re.search(r"FY\d{2}\s*$", n, re.IGNORECASE)]
        winner = fy_names[0] if fy_names else names[0]
        plain_name = re.sub(r"\s+FY\d{2}\s*$", "", winner, flags=re.IGNORECASE).strip()
        try:
            cleaned[plain_name] = float(rates[winner] or 0)
        except (TypeError, ValueError):
            cleaned[plain_name] = 0.0
    if cleaned != rates:
        db.execute(
            "INSERT INTO settings(key, value) VALUES ('bill_rates', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(cleaned),),
        )


def migrate_to_v7(db: sqlite3.Connection) -> None:
    _dedupe_bill_rates(db)
    _dedupe_rate_card_rates(db)


def migrate_to_v8(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS engagement_drafts (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        engagement_code   TEXT,
        client_name       TEXT,
        step              INTEGER NOT NULL DEFAULT 1,
        wizard_json       TEXT NOT NULL,
        created_at        TEXT,
        updated_at        TEXT
    )""")


def migrate_to_v9(db: sqlite3.Connection) -> None:
    if not _has_column(db, "time_entries", "allocation_method"):
        db.execute("ALTER TABLE time_entries ADD COLUMN allocation_method TEXT")
    db.execute("""UPDATE time_entries SET allocation_method='direct_match'
        WHERE matched_phase_id IS NOT NULL AND allocation_method IS NULL""")
    db.execute("""CREATE TABLE IF NOT EXISTS allocation_rules (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
        team_member_id    INTEGER NOT NULL REFERENCES team_members(id) ON DELETE CASCADE,
        phase_id          INTEGER NOT NULL REFERENCES phases(id) ON DELETE CASCADE,
        created_at        TEXT,
        created_from_exception_id INTEGER REFERENCES import_exceptions(id) ON DELETE SET NULL,
        UNIQUE (engagement_id, team_member_id, phase_id)
    )""")


def migrate_to_v10(db: sqlite3.Connection) -> None:
    # Backfill entries stuck unmatched from before the single-phase-budget auto-resolve
    # existed (importers.py): a worker budgeted for exactly one phase anywhere in the
    # engagement has nothing to actually decide, same rule new imports already apply.
    sticky_rules = {int(row["team_member_id"]): int(row["phase_id"]) for row in db.execute(
        "SELECT team_member_id, phase_id FROM allocation_rules"
    ).fetchall()}
    single_phase_members = {
        int(row["member_id"]): int(row["phase_id"])
        for row in db.execute("""SELECT team_member_id AS member_id, MIN(phase_id) AS phase_id
            FROM phase_person_weeks WHERE budgeted_hours>0 OR forecasted_hours>0
            GROUP BY team_member_id HAVING COUNT(DISTINCT phase_id)=1""").fetchall()
    }
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    for member_id in set(sticky_rules) | set(single_phase_members):
        if member_id in sticky_rules:
            phase_id, method = sticky_rules[member_id], "sticky_rule"
        else:
            phase_id, method = single_phase_members[member_id], "single_phase_budget"
        entry_ids = [int(row["id"]) for row in db.execute(
            "SELECT id FROM time_entries WHERE matched_team_member_id=? AND matched_phase_id IS NULL",
            (member_id,)).fetchall()]
        if not entry_ids:
            continue
        placeholders = ",".join("?" for _ in entry_ids)
        db.execute(f"UPDATE time_entries SET matched_phase_id=?,allocation_method=? WHERE id IN ({placeholders})",
                   (phase_id, method, *entry_ids))
        db.execute(f"""UPDATE import_exceptions SET status='resolved',
            resolution_note='Auto-resolved: {method}',updated_at=?
            WHERE exception_code='unmatched_phase' AND status='pending' AND time_entry_id IN ({placeholders})""",
            (timestamp, *entry_ids))
