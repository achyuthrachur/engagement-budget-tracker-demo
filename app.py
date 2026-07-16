from __future__ import annotations

import os
import sqlite3
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file

from calculations import (apply_grid_variance, as_float, dashboard, engagement_metrics,
                          phase_summary, phase_weekly_grid, team_summary)
from db import (connect, db_path, get_app_settings, init_db, load_seed_database,
                now_iso, row_to_dict, rows_to_dicts, set_rates, set_setting)
from exports import build_excel, build_html_report
from importers import parse_text_export, parse_xlsx_export, preview_rows, validate_columns

IMPORT_PREVIEWS: dict[int, list[dict[str, Any]]] = {}
ADJUSTMENT_TYPES = {"markdown", "c360", "bima", "change_order"}
RATE_FIELDS = {"internal_rate", "engagement_rate", "contract_rate", "dte_rate"}


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["DATABASE_PATH"] = database_path or str(db_path())
    app.config["DB_ERROR"] = None
    try:
        init_db(Path(app.config["DATABASE_PATH"]))
    except Exception as exc:  # pragma: no cover
        app.config["DB_ERROR"] = str(exc)

    def conn():
        return connect(Path(app.config["DATABASE_PATH"]))

    @app.errorhandler(Exception)
    def uncaught(exc):
        if isinstance(exc, sqlite3.IntegrityError):
            return fail("A record with this value already exists", 409, "conflict")
        return fail("Unexpected server error", 500, "server_error")

    @app.get("/")
    @app.get("/dashboard")
    @app.get("/engagements/new")
    @app.get("/engagements/<path:_path>")
    @app.get("/settings")
    def index(_path=None):
        return render_template("index.html", db_error=app.config["DB_ERROR"])

    @app.get("/api/health")
    def health():
        return ok({"status": "ok", "db_path": app.config["DATABASE_PATH"], "schema_version": 2})

    @app.post("/api/demo/load-seed")
    def load_demo_seed():
        load_seed_database(Path(app.config["DATABASE_PATH"]))
        with conn() as db:
            return ok(dashboard(db))

    @app.get("/api/engagements")
    def list_engagements():
        with conn() as db:
            return ok(dashboard(db))

    @app.get("/api/engagements/check-code")
    def check_code():
        code = request.args.get("code", "").strip()
        exclude = request.args.get("exclude_id", type=int)
        with conn() as db:
            row = db.execute("SELECT id FROM engagements WHERE engagement_code=?", (code,)).fetchone()
        return ok({"available": bool(code) and (row is None or int(row["id"]) == exclude)})

    @app.post("/api/engagements")
    def create_engagement():
        payload = request.get_json(silent=True) or {}
        info = payload.get("engagement") or payload
        missing = required(info, ["engagement_code", "client_name"])
        if missing:
            return fail("Missing required field", 400, "validation_error", missing)
        mode = str(info.get("complexity_mode") or "simple").lower()
        phases = payload.get("phases") or []
        if mode == "complex" and (not phases or not info.get("first_monday")):
            fields = [name for name, valid in (("phases", phases), ("first_monday", info.get("first_monday"))) if not valid]
            return fail("Complex engagements require phases and a first Monday", 400, "validation_error", fields)
        if mode == "complex":
            try:
                if date.fromisoformat(str(info["first_monday"])[:10]).weekday() != 0:
                    return fail("first_monday must be a Monday", 400, "validation_error", ["first_monday"])
            except ValueError:
                return fail("first_monday must be an ISO date", 400, "validation_error", ["first_monday"])
        for member in payload.get("team", []):
            member_error = validate_member(member)
            if member_error:
                return member_error
        try:
            with conn() as db:
                eid = insert_engagement_bundle(db, info, payload)
                data = full_engagement(db, eid)
            return ok(data, 201)
        except sqlite3.IntegrityError as exc:
            if "engagement_code" in str(exc):
                return fail("Engagement code already exists", 409, "duplicate_engagement_code")
            return fail("A team member or phase already exists", 409, "conflict")

    @app.get("/api/engagements/<int:eid>")
    def get_engagement(eid):
        with conn() as db:
            data = full_engagement(db, eid)
            return ok(data) if data else fail("Not found", 404, "not_found")

    @app.put("/api/engagements/<int:eid>")
    def update_engagement(eid):
        payload = request.get_json(silent=True) or {}
        allowed = {"engagement_code", "client_name", "engagement_type", "model_type",
                   "model_vendor", "engagement_lead", "first_monday", "duration_weeks",
                   "status", "c360_used"}
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            reopening = set(payload) == {"status"} and str(payload.get("status")).lower() == "active"
            if engagement["status"] == "closed" and not reopening:
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            if engagement["complexity_mode"] == "complex" and payload.get("complexity_mode") == "simple":
                return fail("Complexity mode cannot be downgraded once phases exist", 400, "mode_downgrade")
            updates = {key: payload[key] for key in allowed if key in payload}
            if not updates:
                return fail("No fields to update", 400, "validation_error")
            if updates.get("status"):
                updates["status"] = str(updates["status"]).lower()
                if updates["status"] not in {"planning", "active", "closed"}:
                    return fail("Invalid engagement status", 400, "validation_error", ["status"])
            updates["updated_at"] = now_iso()
            assignments = ", ".join(f"{key}=:{key}" for key in updates)
            updates["id"] = eid
            db.execute(f"UPDATE engagements SET {assignments} WHERE id=:id", updates)
            return ok(full_engagement(db, eid))

    @app.delete("/api/engagements/<int:eid>")
    def delete_engagement(eid):
        with conn() as db:
            cursor = db.execute("DELETE FROM engagements WHERE id=?", (eid,))
            if not cursor.rowcount:
                return fail("Not found", 404, "not_found")
        IMPORT_PREVIEWS.pop(eid, None)
        return ok({"deleted": True})

    @app.get("/api/engagements/<int:eid>/team")
    def get_team(eid):
        with conn() as db:
            return ok(team_summary(db, eid)) if get_engagement_row(db, eid) else fail("Not found", 404, "not_found")

    @app.post("/api/engagements/<int:eid>/team")
    def create_member(eid):
        payload = request.get_json(silent=True) or {}
        members = payload.get("members") if isinstance(payload.get("members"), list) else [payload]
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] != "planning":
                return fail("Team members can only be added while planning", 409, "budget_locked")
            try:
                for member in members:
                    error = validate_member(member)
                    if error:
                        return error
                    member_id = insert_team_member(db, eid, member)
                    if engagement["complexity_mode"] == "simple":
                        phase = db.execute("SELECT id FROM phases WHERE engagement_id=? AND is_default=1", (eid,)).fetchone()
                        db.execute("INSERT INTO phase_person_weeks (phase_id,team_member_id,budgeted_hours) VALUES (?,?,?)",
                                   (phase["id"], member_id, as_float(member.get("budgeted_hours"))))
                touch(db, eid)
                return ok(team_summary(db, eid), 201)
            except sqlite3.IntegrityError:
                return fail("A team member with this name already exists on this engagement", 409, "duplicate_team_member")

    @app.put("/api/engagements/<int:eid>/team/<int:member_id>")
    def update_member(eid, member_id):
        payload = request.get_json(silent=True) or {}
        allowed = {"name", "role", "is_offshore", *RATE_FIELDS}
        updates = {key: payload[key] for key in allowed if key in payload}
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            locked = RATE_FIELDS.intersection(updates) and engagement["status"] != "planning"
            if locked:
                return budget_locked(eid, "team_member", member_id)
            if "name" in updates and not valid_worker_name(str(updates["name"])):
                return fail("Name must use Last, First format", 400, "validation_error", ["name"])
            for key in RATE_FIELDS:
                if key in updates:
                    updates[key] = as_float(updates[key])
            if "is_offshore" in updates:
                updates["is_offshore"] = int(bool(updates["is_offshore"]))
            if not updates:
                return fail("No fields to update", 400, "validation_error")
            updates.update({"id": member_id, "eid": eid})
            assignments = ", ".join(f"{key}=:{key}" for key in updates if key not in {"id", "eid"})
            cursor = db.execute(f"UPDATE team_members SET {assignments} WHERE id=:id AND engagement_id=:eid", updates)
            if not cursor.rowcount:
                return fail("Not found", 404, "not_found")
            touch(db, eid)
            return ok(team_summary(db, eid))

    @app.delete("/api/engagements/<int:eid>/team/<int:member_id>")
    def delete_member(eid, member_id):
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            name = db.execute("SELECT name FROM team_members WHERE id=? AND engagement_id=?", (member_id, eid)).fetchone()
            if not name:
                return fail("Not found", 404, "not_found")
            used = db.execute("SELECT 1 FROM time_entries WHERE engagement_id=? AND worker_name=? LIMIT 1", (eid, name["name"])).fetchone()
            if used:
                return fail("Team members with imported time cannot be deleted", 409, "member_in_use")
            db.execute("DELETE FROM team_members WHERE id=?", (member_id,))
            return ok({"deleted": True})

    @app.get("/api/engagements/<int:eid>/phases")
    def get_phases(eid):
        with conn() as db:
            return ok(phase_summary(db, eid)) if get_engagement_row(db, eid) else fail("Not found", 404, "not_found")

    @app.post("/api/engagements/<int:eid>/phases")
    def create_phase(eid):
        payload = request.get_json(silent=True) or {}
        phases = payload.get("phases") if isinstance(payload.get("phases"), list) else [payload]
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] != "planning":
                return fail("Phases cannot be added after activation", 409, "budget_locked")
            order = db.execute("SELECT COALESCE(MAX(sort_order),-1) value FROM phases WHERE engagement_id=?", (eid,)).fetchone()["value"]
            for offset, phase in enumerate(phases, 1):
                if not str(phase.get("phase_name", "")).strip():
                    return fail("Phase name is required", 400, "validation_error", ["phase_name"])
                insert_phase(db, eid, phase, int(order)+offset)
            touch(db, eid)
            return ok(phase_summary(db, eid), 201)

    @app.put("/api/engagements/<int:eid>/phases/<int:phase_id>")
    def update_phase(eid, phase_id):
        payload = request.get_json(silent=True) or {}
        updates = {key: payload[key] for key in {"phase_name", "phase_code", "sow_fees", "sort_order"} if key in payload}
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            if "sow_fees" in updates and engagement["status"] != "planning":
                return budget_locked(eid, "phase", phase_id)
            if "sow_fees" in updates:
                updates["sow_fees"] = as_float(updates["sow_fees"])
            updates.update({"id": phase_id, "eid": eid})
            assignments = ", ".join(f"{key}=:{key}" for key in updates if key not in {"id", "eid"})
            if not assignments:
                return fail("No fields to update", 400, "validation_error")
            cursor = db.execute(f"UPDATE phases SET {assignments} WHERE id=:id AND engagement_id=:eid", updates)
            if not cursor.rowcount:
                return fail("Not found", 404, "not_found")
            touch(db, eid)
            return ok(phase_summary(db, eid))

    @app.delete("/api/engagements/<int:eid>/phases/<int:phase_id>")
    def delete_phase(eid, phase_id):
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] != "planning":
                return fail("Phases cannot be deleted after activation", 409, "budget_locked")
            cursor = db.execute("DELETE FROM phases WHERE id=? AND engagement_id=? AND is_default=0", (phase_id, eid))
            return ok({"deleted": True}) if cursor.rowcount else fail("Not found", 404, "not_found")

    @app.patch("/api/engagements/<int:eid>/phases/reorder")
    def reorder_phases(eid):
        payload = request.get_json(silent=True) or []
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            for item in payload:
                db.execute("UPDATE phases SET sort_order=? WHERE id=? AND engagement_id=?",
                           (int(item.get("sort_order", 0)), int(item.get("id", 0)), eid))
            return ok(phase_summary(db, eid))

    @app.get("/api/engagements/<int:eid>/phases/<int:phase_id>")
    def phase_detail(eid, phase_id):
        with conn() as db:
            phase = next((item for item in phase_summary(db, eid) if int(item["id"]) == phase_id), None)
            if not phase:
                return fail("Not found", 404, "not_found")
            grid = apply_grid_variance(db, phase_weekly_grid(db, eid, phase_id))
            return ok({"phase": phase, "grid": grid})

    @app.put("/api/engagements/<int:eid>/phase-weeks")
    def save_phase_weeks(eid):
        payload = request.get_json(silent=True) or {}
        rows = payload.get("rows") or []
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            for item in rows:
                phase_id = int(item.get("phase_id") or 0)
                member_id = int(item.get("team_member_id") or 0)
                owned = db.execute("""SELECT 1 FROM phases p JOIN team_members tm
                    ON tm.engagement_id=p.engagement_id WHERE p.id=? AND tm.id=? AND p.engagement_id=?""",
                    (phase_id, member_id, eid)).fetchone()
                if not owned:
                    return fail("Phase and team member must belong to the engagement", 400, "scope_mismatch")
                existing = find_phase_week(db, phase_id, member_id, item.get("week_start_date"))
                budget_changed = "budgeted_hours" in item and (
                    not existing or as_float(existing["budgeted_hours"]) != as_float(item["budgeted_hours"])
                )
                if budget_changed and engagement["status"] != "planning":
                    return budget_locked(eid, "phase_person_week", existing["id"] if existing else 0)
                upsert_phase_week(db, phase_id, member_id, item)
            touch(db, eid)
            phase_id = int(rows[0]["phase_id"]) if rows else 0
            return ok(apply_grid_variance(db, phase_weekly_grid(db, eid, phase_id)) if phase_id else {})

    @app.post("/api/engagements/<int:eid>/convert-complex")
    def convert_complex(eid):
        payload = request.get_json(silent=True) or {}
        weeks = int(payload.get("duration_weeks") or 1)
        first = payload.get("first_monday")
        if not first or weeks < 1:
            return fail("First Monday and duration are required", 400, "validation_error")
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] != "planning":
                return fail("Mode conversion is only available while planning", 409, "budget_locked")
            if engagement["complexity_mode"] == "complex":
                return ok(full_engagement(db, eid))
            db.execute("UPDATE engagements SET complexity_mode='complex', first_monday=?, duration_weeks=? WHERE id=?",
                       (first, weeks, eid))
            distribute_flat_rows(db, eid, first, weeks)
            return ok(full_engagement(db, eid))

    @app.get("/api/engagements/<int:eid>/adjustments")
    def get_adjustments(eid):
        with conn() as db:
            return ok(list_adjustments(db, eid))

    @app.post("/api/engagements/<int:eid>/adjustments")
    def create_adjustment(eid):
        payload = request.get_json(silent=True) or {}
        error = validate_adjustment(payload)
        if error:
            return error
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            if payload["adjustment_type"] == "change_order" and not phase_owned(db, eid, payload.get("phase_id")):
                return fail("change_order requires phase_id", 400, "validation_error")
            db.execute("""INSERT INTO budget_adjustments
                (engagement_id,phase_id,adjustment_type,effective_date,amount,description,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (eid, payload.get("phase_id"), payload["adjustment_type"],
                 payload.get("effective_date"), signed_adjustment(payload["adjustment_type"], payload.get("amount")),
                 payload.get("description", ""), now_iso()))
            sync_adjustment_columns(db, eid)
            touch(db, eid)
            return ok(list_adjustments(db, eid), 201)

    @app.put("/api/engagements/<int:eid>/adjustments/<int:adj_id>")
    def update_adjustment(eid, adj_id):
        payload = request.get_json(silent=True) or {}
        current = None
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            current = db.execute("SELECT * FROM budget_adjustments WHERE id=? AND engagement_id=?", (adj_id, eid)).fetchone()
            if not current:
                return fail("Not found", 404, "not_found")
            merged = {**row_to_dict(current), **payload}
            error = validate_adjustment(merged)
            if error:
                return error
            if merged["adjustment_type"] == "change_order" and not phase_owned(db, eid, merged.get("phase_id")):
                return fail("change_order requires phase_id", 400, "validation_error")
            db.execute("""UPDATE budget_adjustments SET phase_id=?, adjustment_type=?, effective_date=?,
                amount=?, description=? WHERE id=? AND engagement_id=?""",
                (merged.get("phase_id"), merged["adjustment_type"], merged.get("effective_date"),
                 signed_adjustment(merged["adjustment_type"], merged.get("amount")),
                 merged.get("description", ""), adj_id, eid))
            sync_adjustment_columns(db, eid)
            return ok(list_adjustments(db, eid))

    @app.delete("/api/engagements/<int:eid>/adjustments/<int:adj_id>")
    def delete_adjustment(eid, adj_id):
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            cursor = db.execute("DELETE FROM budget_adjustments WHERE id=? AND engagement_id=?", (adj_id, eid))
            sync_adjustment_columns(db, eid)
            return ok({"deleted": True}) if cursor.rowcount else fail("Not found", 404, "not_found")

    @app.get("/api/engagements/<int:eid>/revisions")
    def get_revisions(eid):
        with conn() as db:
            return ok(list_revisions(db, eid))

    @app.post("/api/engagements/<int:eid>/revisions")
    def create_revision(eid):
        payload = request.get_json(silent=True) or {}
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            return fail("reason is required", 400, "validation_error", ["reason"])
        target_type = payload.get("target_type")
        target_id = int(payload.get("target_id") or 0)
        field = payload.get("field_name")
        allowed = {"phase": {"sow_fees"}, "phase_person_week": {"budgeted_hours"},
                   "team_member": RATE_FIELDS}
        if field not in allowed.get(target_type, set()):
            return fail("Invalid revision target", 400, "validation_error")
        table, scope = {"phase": ("phases", "phase_id"),
                        "phase_person_week": ("phase_person_weeks", "phase_person_week_id"),
                        "team_member": ("team_members", "team_member_id")}[target_type]
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            if engagement["status"] == "planning":
                return fail("Planning budgets can be edited directly", 409, "budget_not_locked")
            row = revision_target(db, eid, target_type, target_id)
            if not row:
                return fail("Revision target not found", 404, "not_found")
            old = as_float(row[field])
            new = as_float(payload.get("new_value"))
            phase_id = target_id if target_type == "phase" else row["phase_id"] if "phase_id" in row.keys() else None
            values = {"engagement_id": eid, "phase_id": phase_id, "team_member_id": None,
                      "phase_person_week_id": None, "field_name": field, "old_value": old,
                      "new_value": new, "reason": reason, "revised_at": now_iso()}
            values[scope] = target_id
            db.execute("""INSERT INTO budget_revisions
                (engagement_id,phase_id,team_member_id,phase_person_week_id,field_name,
                 old_value,new_value,reason,revised_at)
                VALUES (:engagement_id,:phase_id,:team_member_id,:phase_person_week_id,:field_name,
                        :old_value,:new_value,:reason,:revised_at)""", values)
            db.execute(f"UPDATE {table} SET {field}=? WHERE id=?", (new, target_id))
            touch(db, eid)
            return ok(list_revisions(db, eid), 201)

    @app.get("/api/engagements/<int:eid>/expenses")
    def get_expenses(eid):
        with conn() as db:
            return ok(list_expenses(db, eid))

    @app.post("/api/engagements/<int:eid>/expenses")
    def create_expense(eid):
        payload = request.get_json(silent=True) or {}
        if payload.get("expense_type") not in {"crowe_paid", "client_paid"}:
            return fail("Invalid expense type", 400, "validation_error", ["expense_type"])
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            if payload.get("phase_id") and not phase_owned(db, eid, payload.get("phase_id")):
                return fail("Phase does not belong to engagement", 400, "scope_mismatch")
            db.execute("""INSERT INTO expenses
                (engagement_id,phase_id,expense_type,description,amount,incurred_date,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (eid, payload.get("phase_id"), payload["expense_type"], payload.get("description", ""),
                 as_float(payload.get("amount")), payload.get("incurred_date"), now_iso()))
            return ok(list_expenses(db, eid), 201)

    @app.delete("/api/engagements/<int:eid>/expenses/<int:expense_id>")
    def delete_expense(eid, expense_id):
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            cursor = db.execute("DELETE FROM expenses WHERE id=? AND engagement_id=?", (expense_id, eid))
            return ok({"deleted": True}) if cursor.rowcount else fail("Not found", 404, "not_found")

    @app.post("/api/engagements/<int:eid>/import/preview")
    def import_preview(eid):
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements do not accept imports", 409, "engagement_closed")
            try:
                parsed = read_import_payload()
            except ValueError as exc:
                return fail(str(exc), 400, "validation_error")
            missing = validate_columns(parsed)
            if missing:
                return fail("Import is missing expected columns", 400, "validation_error", missing)
            preview = preview_rows(db, eid, parsed)
            IMPORT_PREVIEWS[eid] = preview["rows"]
            return ok(preview)

    @app.post("/api/engagements/<int:eid>/import/commit")
    def import_commit(eid):
        payload = request.get_json(silent=True) or {}
        rows = IMPORT_PREVIEWS.get(eid)
        if rows is None:
            return fail("No import preview available", 400, "missing_preview")
        assignments = payload.get("phase_assignments") or {}
        included_ids = set(payload.get("included_transaction_ids") or [])
        explicit = "included_transaction_ids" in payload
        selected = []
        preview_duplicates = 0
        for row in rows:
            if row.get("flag") == "duplicate":
                preview_duplicates += 1
            include = row["transaction_id"] in included_ids if explicit else bool(row.get("included"))
            if row.get("flag") == "duplicate" or row["transaction_id"] in set(payload.get("excluded_transaction_ids") or []):
                include = False
            if row.get("phase_desc") in assignments:
                row["matched_phase_id"] = int(assignments[row["phase_desc"]])
            if include:
                selected.append(row)
        if not selected:
            IMPORT_PREVIEWS.pop(eid, None)
            return ok({"snapshot_id": None, "imported": 0, "skipped": len(rows),
                       "duplicates": preview_duplicates, "row_count": 0})
        with conn() as db:
            for phase_id in {row.get("matched_phase_id") for row in selected if row.get("matched_phase_id")}:
                if not phase_owned(db, eid, phase_id):
                    return fail("Phase assignment does not belong to engagement", 400, "scope_mismatch")
            existing = {row["transaction_id"] for row in db.execute(
                "SELECT transaction_id FROM time_entries WHERE transaction_id IS NOT NULL")}
            week_end = max((row["week_end_date"] for row in selected if row.get("week_end_date")), default=now_iso()[:10])
            cursor = db.execute("""INSERT INTO weekly_snapshots
                (engagement_id,week_end_date,imported_at,row_count,notes) VALUES (?,?,?,?,?)""",
                (eid, week_end, now_iso(), 0, payload.get("notes", "")))
            snapshot_id = int(cursor.lastrowid)
            imported = 0
            commit_duplicates = 0
            for row in selected:
                if row["transaction_id"] in existing:
                    commit_duplicates += 1
                    continue
                insert_time_entry(db, snapshot_id, eid, row)
                existing.add(row["transaction_id"])
                imported += 1
            if imported:
                db.execute("UPDATE weekly_snapshots SET row_count=? WHERE id=?", (imported, snapshot_id))
                db.execute("UPDATE engagements SET status='active', updated_at=? WHERE id=? AND status='planning'",
                           (now_iso(), eid))
            else:
                db.execute("DELETE FROM weekly_snapshots WHERE id=?", (snapshot_id,))
                snapshot_id = None
        IMPORT_PREVIEWS.pop(eid, None)
        return ok({"snapshot_id": snapshot_id, "imported": imported, "skipped": len(rows)-imported,
                   "duplicates": preview_duplicates+commit_duplicates, "row_count": imported}, 201 if imported else 200)

    @app.get("/api/engagements/<int:eid>/unmatched-phases")
    def unmatched_phases(eid):
        with conn() as db:
            rows = db.execute("""SELECT phase_desc, COUNT(*) row_count, SUM(hours) hours,
                COUNT(DISTINCT worker_name) workers FROM time_entries
                WHERE engagement_id=? AND matched_phase_id IS NULL GROUP BY phase_desc""", (eid,)).fetchall()
            return ok(rows_to_dicts(rows))

    @app.patch("/api/engagements/<int:eid>/unmatched-phases")
    def assign_unmatched(eid):
        payload = request.get_json(silent=True) or {}
        phase_id = int(payload.get("phase_id") or 0)
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            if not phase_owned(db, eid, phase_id):
                return fail("Phase does not belong to engagement", 400, "scope_mismatch")
            if payload.get("entry_ids"):
                placeholders = ",".join("?" for _ in payload["entry_ids"])
                params = [phase_id, eid, *[int(value) for value in payload["entry_ids"]]]
                cursor = db.execute(f"UPDATE time_entries SET matched_phase_id=? WHERE engagement_id=? AND id IN ({placeholders})", params)
            else:
                cursor = db.execute("""UPDATE time_entries SET matched_phase_id=?
                    WHERE engagement_id=? AND matched_phase_id IS NULL AND COALESCE(phase_desc,'')=?""",
                    (phase_id, eid, str(payload.get("phase_desc") or "")))
            return ok({"updated": cursor.rowcount})

    @app.get("/api/engagements/<int:eid>/snapshots")
    def get_snapshots(eid):
        with conn() as db:
            return ok(snapshot_history(db, eid))

    @app.get("/api/engagements/<int:eid>/snapshots/<int:snapshot_id>")
    def get_snapshot(eid, snapshot_id):
        with conn() as db:
            snap = db.execute("SELECT * FROM weekly_snapshots WHERE id=? AND engagement_id=?", (snapshot_id, eid)).fetchone()
            if not snap:
                return fail("Not found", 404, "not_found")
            entries = db.execute("SELECT * FROM time_entries WHERE snapshot_id=? ORDER BY entry_date,id", (snapshot_id,)).fetchall()
            return ok({"snapshot": row_to_dict(snap), "entries": rows_to_dicts(entries)})

    @app.delete("/api/engagements/<int:eid>/snapshots/<int:snapshot_id>")
    def delete_snapshot(eid, snapshot_id):
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            cursor = db.execute("DELETE FROM weekly_snapshots WHERE id=? AND engagement_id=?", (snapshot_id, eid))
            if not cursor.rowcount:
                return fail("Not found", 404, "not_found")
            remaining = db.execute("SELECT 1 FROM weekly_snapshots WHERE engagement_id=?", (eid,)).fetchone()
            if not remaining:
                db.execute("UPDATE engagements SET status='planning' WHERE id=? AND status='active'", (eid,))
            return ok({"deleted": True})

    @app.get("/api/engagements/<int:eid>/export/excel")
    def export_excel(eid):
        with conn() as db:
            try:
                filename, content = build_excel(db, eid)
            except ValueError:
                return fail("Not found", 404, "not_found")
        return Response(content, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/engagements/<int:eid>/export/html")
    def export_html(eid):
        with conn() as db:
            try:
                report = build_html_report(db, eid, request.args.get("narrative", ""))
            except ValueError:
                return fail("Not found", 404, "not_found")
        return Response(report, mimetype="text/html")

    @app.get("/api/settings/rates")
    def get_settings():
        with conn() as db:
            data = get_app_settings(db)
            path = Path(app.config["DATABASE_PATH"])
            data.update({"db_path": str(path), "db_modified": path.stat().st_mtime if path.exists() else None})
            return ok(data)

    @app.put("/api/settings/rates")
    def update_settings():
        payload = request.get_json(silent=True) or {}
        with conn() as db:
            if isinstance(payload.get("rates"), dict):
                set_rates(db, payload["rates"])
            for key in ("engagement_discount_rate", "contract_discount_rate",
                        "variance_threshold_hours", "variance_threshold_pct"):
                if key in payload:
                    set_setting(db, key, as_float(payload[key]))
            return ok(get_app_settings(db))

    @app.get("/api/settings/backup")
    def backup():
        path = Path(app.config["DATABASE_PATH"])
        if not path.exists():
            return fail("Database not found", 404, "not_found")
        return send_file(path, as_attachment=True, download_name=f"budget_tracker_backup_{now_iso()[:10]}.db")

    return app


def ok(data: Any, status: int = 200):
    return jsonify({"data": data, "error": None}), status


def fail(message: str, status: int, code: str, fields=None, extra=None):
    error = {"message": message, "code": code}
    if fields:
        error["fields"] = fields
    if extra:
        error.update(extra)
    return jsonify({"data": None, "error": error}), status


def required(payload, fields):
    return [field for field in fields if payload.get(field) in (None, "")]


def get_engagement_row(db, eid):
    return db.execute("SELECT * FROM engagements WHERE id=?", (eid,)).fetchone()


def touch(db, eid):
    db.execute("UPDATE engagements SET updated_at=? WHERE id=?", (now_iso(), eid))


def valid_worker_name(name: str) -> bool:
    parts = [part.strip() for part in name.split(",")]
    return len(parts) == 2 and all(parts)


def validate_member(member):
    name = str(member.get("name") or "").strip()
    if not name:
        return fail("Missing required field", 400, "validation_error", ["name"])
    if not valid_worker_name(name):
        return fail("Name must use Last, First format", 400, "validation_error", ["name"])
    return None


def insert_team_member(db, eid, member):
    settings = get_app_settings(db)
    internal = as_float(member.get("internal_rate"))
    engagement_rate = member.get("engagement_rate")
    contract_rate = member.get("contract_rate")
    if engagement_rate in (None, ""):
        engagement_rate = internal * (1-settings["engagement_discount_rate"])
    if contract_rate in (None, ""):
        contract_rate = internal * (1-settings["contract_discount_rate"])
    cursor = db.execute("""INSERT INTO team_members
        (engagement_id,name,role,is_offshore,internal_rate,engagement_rate,contract_rate,dte_rate,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (eid, str(member.get("name") or "").strip(), member.get("role"),
         int(bool(member.get("is_offshore"))), internal, as_float(engagement_rate),
         as_float(contract_rate), as_float(member.get("dte_rate")), now_iso()))
    return int(cursor.lastrowid)


def insert_phase(db, eid, phase, order):
    cursor = db.execute("""INSERT INTO phases
        (engagement_id,phase_name,phase_code,sow_fees,sort_order,is_default,created_at)
        VALUES (?,?,?,?,?,?,?)""",
        (eid, str(phase.get("phase_name") or "").strip(), phase.get("phase_code") or None,
         as_float(phase.get("sow_fees")), order, int(bool(phase.get("is_default"))), now_iso()))
    return int(cursor.lastrowid)


def insert_engagement_bundle(db, info, payload):
    mode = str(info.get("complexity_mode") or "simple").lower()
    now = now_iso()
    cursor = db.execute("""INSERT INTO engagements
        (engagement_code,client_name,engagement_type,complexity_mode,model_type,model_vendor,
         engagement_lead,first_monday,duration_weeks,status,c360_used,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,'planning',?,?,?)""",
        (str(info["engagement_code"]).strip(), str(info["client_name"]).strip(),
         info.get("engagement_type"), mode, info.get("model_type"), info.get("model_vendor"),
         info.get("engagement_lead"), info.get("first_monday") or info.get("first_week_with_entry"),
         int(info.get("duration_weeks") or 1), int(bool(info.get("c360_used"))), now, now))
    eid = int(cursor.lastrowid)
    member_ids = []
    for member in payload.get("team", []):
        member_ids.append(insert_team_member(db, eid, member))
    phase_ids = []
    if mode == "simple":
        phase_ids.append(insert_phase(db, eid, {"phase_name": "General", "is_default": 1,
                                                "sow_fees": info.get("max_sow_fees", info.get("sow_fees", 0))}, 0))
    else:
        for order, phase in enumerate(payload.get("phases") or []):
            phase_ids.append(insert_phase(db, eid, phase, order))
    if mode == "simple":
        for member_id, member in zip(member_ids, payload.get("team", [])):
            db.execute("INSERT INTO phase_person_weeks (phase_id,team_member_id,budgeted_hours) VALUES (?,?,?)",
                       (phase_ids[0], member_id, as_float(member.get("budgeted_hours"))))
    else:
        save_initial_complex_budget(db, info, payload, phase_ids, member_ids)
    initial = [("c360", info.get("c360_amount")), ("bima", info.get("bima_amount"))]
    for kind, amount in initial:
        if as_float(amount):
            db.execute("""INSERT INTO budget_adjustments
                (engagement_id,adjustment_type,amount,description,created_at) VALUES (?,?,?,?,?)""",
                (eid, kind, signed_adjustment(kind, amount), "Initial engagement setup", now))
    sync_adjustment_columns(db, eid)
    return eid


def save_initial_complex_budget(db, info, payload, phase_ids, member_ids):
    rows = payload.get("weekly_budgets") or []
    if rows:
        for item in rows:
            phase_id = phase_ids[int(item.get("phase_index", 0))]
            member_id = member_ids[int(item.get("team_index", 0))]
            upsert_phase_week(db, phase_id, member_id, item)
        return
    start = date.fromisoformat(str(info["first_monday"])[:10])
    weeks = int(info.get("duration_weeks") or 1)
    for member_id, member in zip(member_ids, payload.get("team", [])):
        total = as_float(member.get("budgeted_hours"))
        for index in range(weeks):
            db.execute("""INSERT INTO phase_person_weeks
                (phase_id,team_member_id,week_start_date,budgeted_hours,forecasted_hours)
                VALUES (?,?,?,?,0)""", (phase_ids[0], member_id,
                (start+timedelta(days=7*index)).isoformat(), total/weeks if weeks else 0))


def full_engagement(db, eid):
    engagement = get_engagement_row(db, eid)
    if not engagement:
        return None
    return {
        "engagement": row_to_dict(engagement),
        "metrics": engagement_metrics(db, eid),
        "team": team_summary(db, eid),
        "phases": phase_summary(db, eid),
        "adjustments": list_adjustments(db, eid),
        "revisions": list_revisions(db, eid),
        "expenses": list_expenses(db, eid),
        "recent_imports": snapshot_history(db, eid)[:3],
        "weekly_summary": weekly_summary(db, eid),
    }


def list_adjustments(db, eid):
    return rows_to_dicts(db.execute("""SELECT a.*,p.phase_name FROM budget_adjustments a
        LEFT JOIN phases p ON p.id=a.phase_id WHERE a.engagement_id=?
        ORDER BY COALESCE(a.effective_date,a.created_at) DESC,a.id DESC""", (eid,)).fetchall())


def list_revisions(db, eid):
    return rows_to_dicts(db.execute("""SELECT r.*,p.phase_name,tm.name team_member_name
        FROM budget_revisions r LEFT JOIN phases p ON p.id=r.phase_id
        LEFT JOIN team_members tm ON tm.id=r.team_member_id
        WHERE r.engagement_id=? ORDER BY r.revised_at DESC,r.id DESC""", (eid,)).fetchall())


def list_expenses(db, eid):
    return rows_to_dicts(db.execute("""SELECT x.*,p.phase_name FROM expenses x
        LEFT JOIN phases p ON p.id=x.phase_id WHERE x.engagement_id=?
        ORDER BY x.incurred_date DESC,x.id DESC""", (eid,)).fetchall())


def weekly_summary(db, eid):
    return rows_to_dicts(db.execute("""SELECT week_end_date,SUM(hours) hours,
        SUM(fees_contract_rate) fees,COUNT(*) entries FROM time_entries
        WHERE engagement_id=? GROUP BY week_end_date ORDER BY week_end_date""", (eid,)).fetchall())


def snapshot_history(db, eid):
    rows = db.execute("""SELECT s.*,COALESCE(SUM(t.hours),0) hours,
        COALESCE(SUM(t.fees_contract_rate),0) fees FROM weekly_snapshots s
        LEFT JOIN time_entries t ON t.snapshot_id=s.id WHERE s.engagement_id=?
        GROUP BY s.id ORDER BY s.week_end_date,s.id""", (eid,)).fetchall()
    result = []
    cumulative_hours = cumulative_fees = 0.0
    for row in rows:
        item = row_to_dict(row) or {}
        cumulative_hours += as_float(item["hours"])
        cumulative_fees += as_float(item["fees"])
        item["cumulative_hours"] = cumulative_hours
        item["cumulative_fees"] = round(cumulative_fees, 2)
        result.append(item)
    return list(reversed(result))


def find_phase_week(db, phase_id, member_id, week):
    if week:
        return db.execute("""SELECT * FROM phase_person_weeks
            WHERE phase_id=? AND team_member_id=? AND week_start_date=?""",
            (phase_id, member_id, week)).fetchone()
    return db.execute("""SELECT * FROM phase_person_weeks
        WHERE phase_id=? AND team_member_id=? AND week_start_date IS NULL""",
        (phase_id, member_id)).fetchone()


def upsert_phase_week(db, phase_id, member_id, item):
    week = item.get("week_start_date") or None
    existing = find_phase_week(db, phase_id, member_id, week)
    budget = as_float(item.get("budgeted_hours", existing["budgeted_hours"] if existing else 0))
    forecast = as_float(item.get("forecasted_hours", existing["forecasted_hours"] if existing else 0))
    if existing:
        db.execute("UPDATE phase_person_weeks SET budgeted_hours=?,forecasted_hours=? WHERE id=?",
                   (budget, forecast, existing["id"]))
        return int(existing["id"])
    cursor = db.execute("""INSERT INTO phase_person_weeks
        (phase_id,team_member_id,week_start_date,budgeted_hours,forecasted_hours)
        VALUES (?,?,?,?,?)""", (phase_id, member_id, week, budget, forecast))
    return int(cursor.lastrowid)


def distribute_flat_rows(db, eid, first, weeks):
    start = date.fromisoformat(str(first)[:10])
    rows = db.execute("""SELECT ppw.* FROM phase_person_weeks ppw JOIN phases p ON p.id=ppw.phase_id
        WHERE p.engagement_id=? AND ppw.week_start_date IS NULL""", (eid,)).fetchall()
    for row in rows:
        for index in range(weeks):
            db.execute("""INSERT INTO phase_person_weeks
                (phase_id,team_member_id,week_start_date,budgeted_hours,forecasted_hours)
                VALUES (?,?,?,?,?)""", (row["phase_id"], row["team_member_id"],
                (start+timedelta(days=7*index)).isoformat(), as_float(row["budgeted_hours"])/weeks,
                as_float(row["forecasted_hours"])/weeks))
        db.execute("DELETE FROM phase_person_weeks WHERE id=?", (row["id"],))


def phase_owned(db, eid, phase_id):
    if not phase_id:
        return False
    return db.execute("SELECT 1 FROM phases WHERE id=? AND engagement_id=?", (int(phase_id), eid)).fetchone() is not None


def revision_target(db, eid, target_type, target_id):
    if target_type == "phase":
        return db.execute("SELECT * FROM phases WHERE id=? AND engagement_id=?", (target_id, eid)).fetchone()
    if target_type == "team_member":
        return db.execute("SELECT * FROM team_members WHERE id=? AND engagement_id=?", (target_id, eid)).fetchone()
    return db.execute("""SELECT ppw.*,p.engagement_id FROM phase_person_weeks ppw
        JOIN phases p ON p.id=ppw.phase_id WHERE ppw.id=? AND p.engagement_id=?""", (target_id, eid)).fetchone()


def budget_locked(eid, target_type, target_id):
    endpoint = f"/api/engagements/{eid}/revisions"
    return fail("Budget is locked. Record a reasoned revision.", 409, "budget_locked",
                extra={"revision_endpoint": endpoint, "target_type": target_type, "target_id": target_id})


def validate_adjustment(payload):
    kind = str(payload.get("adjustment_type") or "").lower()
    if kind not in ADJUSTMENT_TYPES:
        return fail("Invalid adjustment type", 400, "validation_error", ["adjustment_type"])
    if kind == "change_order" and not payload.get("phase_id"):
        return fail("change_order requires phase_id", 400, "validation_error", ["phase_id"])
    if kind == "bima" and not str(payload.get("description") or "").strip():
        return fail("Description is required for BIMA", 400, "validation_error", ["description"])
    return None


def signed_adjustment(kind, value):
    amount = as_float(value)
    return -abs(amount) if kind in {"markdown", "bima"} else amount


def sync_adjustment_columns(db, eid):
    values = {row["adjustment_type"]: as_float(row["amount"]) for row in db.execute(
        """SELECT adjustment_type,SUM(amount) amount FROM budget_adjustments
        WHERE engagement_id=? GROUP BY adjustment_type""", (eid,)).fetchall()}
    db.execute("UPDATE engagements SET c360_amount=?,bima_amount=? WHERE id=?",
               (values.get("c360", 0), values.get("bima", 0), eid))


def read_import_payload():
    uploaded = request.files.get("file")
    if uploaded:
        content = uploaded.read()
        if uploaded.filename and uploaded.filename.lower().endswith(".xlsx"):
            return parse_xlsx_export(content)
        return parse_text_export(content.decode("utf-8-sig"))
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if not text:
        raise ValueError("Paste text or upload a CSV/XLSX file")
    return parse_text_export(text)


def insert_time_entry(db, snapshot_id, eid, row):
    db.execute("""INSERT INTO time_entries
        (snapshot_id,engagement_id,transaction_id,worker_name,worker_id,title,
         worker_bu_du_cc,competency_center,entry_date,week_end_date,financial_period,
         project_id,project_name,xref,phase_desc,task_desc,work_location,billing_status,
         hours,fees_std_rate,fees_contract_rate,memo,matched_phase_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (snapshot_id, eid, row["transaction_id"], row["worker_name"], row["worker_id"],
         row["title"], row.get("worker_bu_du_cc"), row.get("competency_center"),
         row["entry_date"], row["week_end_date"], row["financial_period"],
         row.get("project_id"), row.get("project"), row.get("xref"), row["phase_desc"],
         row["task_desc"], row["work_location"], row["billing_status"], row["hours"],
         row["fees_std_rate"], row["fees_contract_rate"], row["memo"], row.get("matched_phase_id")))


if __name__ == "__main__":
    port = int(os.environ.get("BUDGET_TRACKER_PORT", "5000"))
    create_app().run(host="127.0.0.1", port=port, debug=False)
