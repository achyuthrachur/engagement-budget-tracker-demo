from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory

from calculations import (apply_grid_variance, as_float, budget_overage_weeks, dashboard,
                          engagement_metrics, money,
                          phase_summary, phase_weekly_grid, team_summary, week_monday)
from db import (SCHEMA_VERSION, automatic_backup, connect, db_path, frontend_dist_dir,
                get_app_settings, init_db, latest_backup, load_seed_database, now_iso,
                row_to_dict, rows_to_dicts, set_rates, set_setting)
from exports import build_excel, build_html_report, build_scheduling_csv
from importers import (covered_period_from_text, covered_period_from_xlsx, parse_text_export,
                       parse_xlsx_export, preview_rows, suggest_from_memo, validate_columns)
from migrations import normalize_role_key
from version import APP_VERSION

IMPORT_PREVIEWS: dict[int, dict[str, Any]] = {}
ADJUSTMENT_TYPES = {"markdown", "c360", "bima", "change_order"}
RATE_FIELDS = {"engagement_rate"}
PROPOSAL_RATE_BASES = {
    "standard": "standard_rate",
    "engagement": "engagement_rate",
    "contract": "contract_rate",
}
PORT_CANDIDATES = tuple(range(5000, 5005))
_NUMERIC_ID_RE = re.compile(r"^\d+$")
# Grows by one alternative per phase as more engagement sub-pages port to React (see app.js's
# REACT_ENGAGEMENT_SUBROUTES for the matching client-side fix).
_REACT_ENGAGEMENT_SUBROUTE_RE = re.compile(r"^\d+/(import|exceptions|phases|phases/\d+|hours-overages)$")


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

    def legacy_page(db_error=None):
        return render_template(
            "index.html",
            db_error=db_error if db_error is not None else app.config["DB_ERROR"],
            app_version=APP_VERSION,
            schema_version=SCHEMA_VERSION,
        )

    def serve_frontend():
        if app.config["DB_ERROR"]:
            return legacy_page()
        index_path = frontend_dist_dir() / "index.html"
        if not index_path.exists():
            return legacy_page("Frontend build not found. Run `npm run build` in app/frontend.")
        return send_file(index_path)

    @app.get("/")
    @app.get("/dashboard")
    @app.get("/help")
    def frontend_root():
        return serve_frontend()

    @app.get("/proposals")
    @app.get("/proposals/new")
    @app.get("/proposals/<path:_path>")
    @app.get("/engagements/new")
    @app.get("/engagements/<path:_path>")
    @app.get("/settings")
    @app.get("/settings/rate-cards")
    def index(_path=None):
        if _path is not None and (_NUMERIC_ID_RE.match(_path) or _REACT_ENGAGEMENT_SUBROUTE_RE.match(_path)):
            # bare /engagements/<id> (Overview) and every ported sub-route (Weekly import,
            # Exceptions, ...) are React-owned; any other sub-route (e.g. /engagements/<id>/phases/7)
            # falls through below
            return serve_frontend()
        return legacy_page()

    @app.get("/frontend-assets/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(frontend_dist_dir(), filename)

    @app.get("/api/health")
    def health():
        return ok({"status": "ok", "app_version": APP_VERSION,
                   "db_path": app.config["DATABASE_PATH"], "schema_version": SCHEMA_VERSION})

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)

    @app.post("/api/demo/load-seed")
    def load_demo_seed():
        load_seed_database(Path(app.config["DATABASE_PATH"]))
        with conn() as db:
            return ok(dashboard(db))

    @app.get("/api/engagements")
    def list_engagements():
        with conn() as db:
            return ok(dashboard(db))

    @app.get("/api/proposals")
    def list_proposals():
        with conn() as db:
            return ok({"proposals": proposal_list(db)})

    @app.post("/api/proposals")
    def create_proposal():
        payload = request.get_json(silent=True) or {}
        info = payload.get("proposal") or payload
        missing = required(info, ["proposal_code", "client_name", "first_monday", "duration_weeks"])
        if missing:
            return fail("Missing required field", 400, "validation_error", missing)
        try:
            if date.fromisoformat(str(info["first_monday"])[:10]).weekday() != 0:
                return fail("first_monday must be a Monday", 400, "validation_error", ["first_monday"])
        except ValueError:
            return fail("first_monday must be an ISO date", 400, "validation_error", ["first_monday"])
        people = payload.get("people") or []
        weekly_rows = payload.get("weekly_budgets") or []
        try:
            with conn() as db:
                pricing_error = validate_proposal_pricing(db, info, people)
                if pricing_error:
                    return pricing_error
                pid = insert_proposal_bundle(db, info, people, weekly_rows)
                return ok(full_proposal(db, pid), 201)
        except sqlite3.IntegrityError as exc:
            if "proposal_code" in str(exc):
                return fail("Proposal code already exists", 409, "duplicate_proposal_code")
            return fail("A proposal person already exists", 409, "conflict")

    @app.get("/api/proposals/<int:pid>")
    def get_proposal(pid):
        with conn() as db:
            data = full_proposal(db, pid)
            return ok(data) if data else fail("Not found", 404, "not_found")

    @app.put("/api/proposals/<int:pid>")
    def update_proposal(pid):
        payload = request.get_json(silent=True) or {}
        info = payload.get("proposal") or payload
        if "first_monday" in info:
            try:
                if date.fromisoformat(str(info["first_monday"])[:10]).weekday() != 0:
                    return fail("first_monday must be a Monday", 400, "validation_error", ["first_monday"])
            except ValueError:
                return fail("first_monday must be an ISO date", 400, "validation_error", ["first_monday"])
        people = payload.get("people") or []
        weekly_rows = payload.get("weekly_budgets") or []
        with conn() as db:
            current = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
            if not current:
                return fail("Not found", 404, "not_found")
            pricing_error = validate_proposal_pricing(db, info, people, current)
            if pricing_error:
                return pricing_error
            replace_proposal_bundle(db, pid, info, people, weekly_rows)
            return ok(full_proposal(db, pid))

    @app.get("/api/wizard-drafts")
    def list_wizard_drafts():
        with conn() as db:
            rows = db.execute(
                "SELECT id, engagement_code, client_name, step, updated_at "
                "FROM engagement_drafts ORDER BY updated_at DESC"
            ).fetchall()
            return ok({"drafts": [dict(row) for row in rows]})

    @app.get("/api/wizard-drafts/<int:draft_id>")
    def get_wizard_draft(draft_id):
        with conn() as db:
            row = db.execute("SELECT * FROM engagement_drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                return fail("Not found", 404, "not_found")
            draft = dict(row)
            draft["wizard"] = json.loads(draft.pop("wizard_json"))
            return ok(draft)

    @app.post("/api/wizard-drafts")
    def create_wizard_draft():
        payload = request.get_json(silent=True) or {}
        wizard = payload.get("wizard")
        if wizard is None:
            return fail("Missing wizard state", 400, "validation_error", ["wizard"])
        now = now_iso()
        with conn() as db:
            cursor = db.execute(
                "INSERT INTO engagement_drafts(engagement_code,client_name,step,wizard_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (wizard.get("info", {}).get("engagement_code"), wizard.get("info", {}).get("client_name"),
                 int(wizard.get("step") or 1), json.dumps(wizard), now, now),
            )
            return ok({"id": int(cursor.lastrowid)}, 201)

    @app.put("/api/wizard-drafts/<int:draft_id>")
    def update_wizard_draft(draft_id):
        payload = request.get_json(silent=True) or {}
        wizard = payload.get("wizard")
        if wizard is None:
            return fail("Missing wizard state", 400, "validation_error", ["wizard"])
        with conn() as db:
            cursor = db.execute(
                "UPDATE engagement_drafts SET engagement_code=?, client_name=?, step=?, wizard_json=?, updated_at=? "
                "WHERE id=?",
                (wizard.get("info", {}).get("engagement_code"), wizard.get("info", {}).get("client_name"),
                 int(wizard.get("step") or 1), json.dumps(wizard), now_iso(), draft_id),
            )
            if not cursor.rowcount:
                return fail("Not found", 404, "not_found")
            return ok({"id": draft_id})

    @app.delete("/api/wizard-drafts/<int:draft_id>")
    def delete_wizard_draft(draft_id):
        with conn() as db:
            db.execute("DELETE FROM engagement_drafts WHERE id=?", (draft_id,))
            return ok({"deleted": True})

    @app.post("/api/proposals/<int:pid>/convert")
    def convert_proposal(pid):
        payload = request.get_json(silent=True) or {}
        required_fields = ["engagement_code", "client_name", "engagement_lead", "complexity_mode", "first_monday"]
        missing = required(payload, required_fields)
        if missing:
            return fail("Missing required engagement fields", 400, "validation_error", missing)
        engagement_code = str(payload["engagement_code"]).strip()
        mode = str(payload["complexity_mode"]).strip().lower()
        if mode not in {"simple", "complex"}:
            return fail("Invalid complexity mode", 400, "validation_error", ["complexity_mode"])
        try:
            new_first_monday = date.fromisoformat(str(payload["first_monday"])[:10])
        except ValueError:
            return fail("first_monday must be an ISO date", 400, "validation_error", ["first_monday"])
        with conn() as db:
            proposal = full_proposal(db, pid)
            if not proposal:
                return fail("Not found", 404, "not_found")
            if not proposal["people"]:
                return fail("Proposal must include at least one person", 400, "validation_error")
            confirmations = payload.get("people") or []
            if len(confirmations) != len(proposal["people"]):
                return fail("Confirm every proposal person before conversion", 400, "validation_error", ["people"])
            confirmed_by_id = {int(item.get("proposal_person_id") or 0): item for item in confirmations}
            for person in proposal["people"]:
                confirmation = confirmed_by_id.get(int(person["id"]))
                if not confirmation or not valid_worker_name(str(confirmation.get("name") or "")):
                    return fail("Confirmed names must use Last, First format", 400, "validation_error", ["people.name"])
            info = {
                "engagement_code": engagement_code,
                "client_name": str(payload["client_name"]).strip(),
                "engagement_type": proposal["proposal"].get("engagement_type"),
                "engagement_lead": str(payload["engagement_lead"]).strip(),
                "complexity_mode": mode,
                "first_monday": new_first_monday.isoformat(),
                "duration_weeks": proposal["proposal"]["duration_weeks"],
                "max_sow_fees": proposal["metrics"]["estimated_fees"],
            }
            proposal_first = date.fromisoformat(str(proposal["proposal"]["first_monday"])[:10])
            phase_names = ["General"] if mode == "simple" else []
            if mode == "complex":
                for person in proposal["people"]:
                    confirmation = confirmed_by_id[int(person["id"])]
                    phase_name = str(confirmation.get("phase_name") or "Proposal scope").strip()
                    if phase_name not in phase_names:
                        phase_names.append(phase_name)
            phase_fees = {name: 0.0 for name in phase_names}
            team = []
            weekly_budgets = []
            for index, person in enumerate(proposal["people"]):
                confirmation = confirmed_by_id[int(person["id"])]
                total_hours = as_float(person.get("total_hours"))
                phase_name = "General" if mode == "simple" else str(
                    confirmation.get("phase_name") or "Proposal scope").strip()
                phase_index = phase_names.index(phase_name)
                team.append({
                    "name": str(confirmation["name"]).strip(),
                    "role": confirmation.get("role") or person.get("role"),
                    "budgeted_hours": total_hours,
                })
                for week in person["weeks"]:
                    source_week = date.fromisoformat(str(week["week_start_date"])[:10])
                    offset = (source_week-proposal_first).days // 7
                    weekly_budgets.append({
                        "phase_index": phase_index,
                        "team_index": index,
                        "week_start_date": (new_first_monday+timedelta(days=7*offset)).isoformat(),
                        "budgeted_hours": week["budgeted_hours"],
                        "forecasted_hours": week["forecasted_hours"],
                    })
                    planned = week["forecasted_hours"] if week["forecasted_hours"] is not None else week["budgeted_hours"]
                    phase_fees[phase_name] += as_float(planned) * as_float(person.get("rough_rate"))
            engagement_payload = {
                "team": team,
                "phases": [{"phase_name": name, "phase_code": f"P{index+1}",
                            "sow_fees": phase_fees[name]} for index, name in enumerate(phase_names)],
                "weekly_budgets": weekly_budgets,
            }
            eid = insert_engagement_bundle(db, info, engagement_payload)
            db.execute("UPDATE proposals SET status='converted',converted_engagement_id=?,updated_at=? WHERE id=?",
                       (eid, now_iso(), pid))
            return ok({"engagement_id": eid, "engagement": full_engagement(db, eid)}, 201)

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
            weekly_rows = payload.get("weekly_budgets") or []
            if weekly_rows:
                for index, member in enumerate(payload.get("team") or []):
                    target = as_float(member.get("budgeted_hours"))
                    planned = sum(as_float(row.get("budgeted_hours")) for row in weekly_rows
                                  if int(row.get("team_index", -1)) == index)
                    if abs(target-planned) > 0.01:
                        return fail("Weekly budget must reconcile to each team member target",
                                    400, "budget_reconciliation_error",
                                    [f"team[{index}].budgeted_hours"])
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

    @app.get("/api/engagements/<int:eid>/overview")
    def get_overview(eid):
        with conn() as db:
            data = full_engagement(db, eid)
            if not data:
                return fail("Not found", 404, "not_found")
            return ok({"engagement": data["engagement"], "metrics": data["metrics"],
                       "phases": data["phases"]})

    @app.put("/api/engagements/<int:eid>")
    def update_engagement(eid):
        payload = request.get_json(silent=True) or {}
        allowed = {"engagement_code", "client_name", "engagement_type", "model_type",
                   "model_vendor", "engagement_lead", "first_monday", "duration_weeks",
                   "status", "c360_used", "rate_mode"}
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            requested_status = str(payload.get("status") or "").lower()
            reopening = requested_status == "active"
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
                if updates["status"] != engagement["status"]:
                    reason = str(payload.get("reason") or "").strip()
                    if updates["status"] in {"active", "closed"} and not reason:
                        return fail("A reason is required for this status change", 400, "validation_error", ["reason"])
                    automatic_backup(Path(app.config["DATABASE_PATH"]), "status")
                    record_event(db, eid, f"status_{updates['status']}",
                                 reason or f"Status changed from {engagement['status']} to {updates['status']}")
            updates["updated_at"] = now_iso()
            assignments = ", ".join(f"{key}=:{key}" for key in updates)
            updates["id"] = eid
            db.execute(f"UPDATE engagements SET {assignments} WHERE id=:id", updates)
            return ok(full_engagement(db, eid))

    @app.delete("/api/engagements/<int:eid>")
    def delete_engagement(eid):
        backup_path = automatic_backup(Path(app.config["DATABASE_PATH"]), "pre_engagement_delete")
        with conn() as db:
            cursor = db.execute("DELETE FROM engagements WHERE id=?", (eid,))
            if not cursor.rowcount:
                return fail("Not found", 404, "not_found")
        IMPORT_PREVIEWS.pop(eid, None)
        return ok({"deleted": True, "backup_path": str(backup_path) if backup_path else None})

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
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            reason = str(payload.get("reason") or "").strip()
            if engagement["status"] == "active" and not reason:
                return fail("A reason is required when adding a worker after activation",
                            400, "validation_error", ["reason"])
            try:
                if engagement["status"] == "active":
                    automatic_backup(Path(app.config["DATABASE_PATH"]), "team")
                for member in members:
                    error = validate_member(member)
                    if error:
                        return error
                    member_id = insert_team_member(db, eid, member)
                    if engagement["complexity_mode"] == "simple":
                        phase = db.execute("SELECT id FROM phases WHERE engagement_id=? AND is_default=1", (eid,)).fetchone()
                        db.execute("INSERT INTO phase_person_weeks (phase_id,team_member_id,budgeted_hours) VALUES (?,?,?)",
                                   (phase["id"], member_id, as_float(member.get("budgeted_hours"))))
                    if engagement["status"] == "active":
                        db.execute("""INSERT INTO budget_revisions
                            (engagement_id,team_member_id,field_name,old_value,new_value,reason,revised_at)
                            VALUES (?,?,?,?,?,?,?)""",
                            (eid, member_id, "team_member_added", 0, 1, reason, now_iso()))
                        record_event(db, eid, "team_member_added",
                                     f"{member.get('name')} added after activation: {reason}")
                touch(db, eid)
                return ok(team_summary(db, eid), 201)
            except sqlite3.IntegrityError:
                return fail("A team member with this name already exists on this engagement", 409, "duplicate_team_member")

    @app.put("/api/engagements/<int:eid>/team/<int:member_id>")
    def update_member(eid, member_id):
        payload = request.get_json(silent=True) or {}
        allowed = {"name", "role", "is_offshore", "is_active", "rate_tier_id", *RATE_FIELDS}
        updates = {key: payload[key] for key in allowed if key in payload}
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            current = db.execute("SELECT * FROM team_members WHERE id=? AND engagement_id=?",
                                 (member_id, eid)).fetchone()
            if not current:
                return fail("Not found", 404, "not_found")
            if "name" in updates and not valid_worker_name(str(updates["name"])):
                return fail("Name must use Last, First format", 400, "validation_error", ["name"])
            for key in RATE_FIELDS:
                if key in updates:
                    updates[key] = as_float(updates[key])
            locked_fields = [key for key in RATE_FIELDS if key in updates
                             and as_float(current[key]) != as_float(updates[key])]
            custom_override = bool(payload.get("is_custom_rate"))
            custom_reason = str(payload.get("custom_rate_reason") or "").strip()
            if locked_fields and custom_override and not custom_reason:
                return fail("custom_rate_reason is required when is_custom_rate is true", 400,
                            "validation_error", ["custom_rate_reason"])
            if locked_fields and engagement["status"] != "planning" and not custom_override:
                return budget_locked(eid, "team_member", member_id, locked_fields[0])
            if locked_fields and custom_override:
                updates["is_custom_rate"] = 1
                updates["custom_rate_note"] = custom_reason
                for field_name in locked_fields:
                    db.execute("""INSERT INTO budget_revisions
                        (engagement_id,team_member_id,field_name,old_value,new_value,reason,revised_at)
                        VALUES (?,?,?,?,?,?,?)""",
                        (eid, member_id, field_name, as_float(current[field_name]),
                         as_float(updates[field_name]), custom_reason, now_iso()))
            if "is_offshore" in updates:
                updates["is_offshore"] = int(bool(updates["is_offshore"]))
            if "is_active" in updates:
                updates["is_active"] = int(bool(updates["is_active"]))
            if "engagement_rate" in updates:
                # Contract rate is no longer a distinct input: it always mirrors engagement rate.
                updates["contract_rate"] = updates["engagement_rate"]
            if not updates:
                return fail("No fields to update", 400, "validation_error")
            updates.update({"id": member_id, "eid": eid})
            assignments = ", ".join(f"{key}=:{key}" for key in updates if key not in {"id", "eid"})
            cursor = db.execute(f"UPDATE team_members SET {assignments} WHERE id=:id AND engagement_id=:eid", updates)
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
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
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
            if "sow_fees" in updates:
                updates["sow_fees"] = as_float(updates["sow_fees"])
                current = db.execute("SELECT sow_fees FROM phases WHERE id=? AND engagement_id=?",
                                     (phase_id, eid)).fetchone()
                if not current:
                    return fail("Not found", 404, "not_found")
                if phase_has_actuals(db, eid, phase_id) and as_float(current["sow_fees"]) != updates["sow_fees"]:
                    return budget_locked(eid, "phase", phase_id, "sow_fees")
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
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            if phase_has_actuals(db, eid, phase_id):
                return fail("Phases with posted actuals cannot be deleted", 409, "phase_in_use")
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
                if budget_changed and phase_has_actuals(db, eid, phase_id):
                    return budget_locked(eid, "phase_person_week", existing["id"] if existing else 0)
                upsert_phase_week(db, phase_id, member_id, item)
            touch(db, eid)
            phase_id = int(rows[0]["phase_id"]) if rows else 0
            return ok(apply_grid_variance(db, phase_weekly_grid(db, eid, phase_id)) if phase_id else {})

    @app.patch("/api/engagements/<int:eid>/forecasts/bulk")
    def bulk_forecasts(eid):
        payload = request.get_json(silent=True) or {}
        member_ids = [int(value) for value in payload.get("team_member_ids") or []]
        phase_ids = [int(value) for value in payload.get("phase_ids") or []]
        start_week = payload.get("start_week")
        end_week = payload.get("end_week")
        mode = str(payload.get("mode") or "flat")
        value = as_float(payload.get("value"))
        if not member_ids or not phase_ids or not start_week or not end_week or mode not in {"flat", "spread"}:
            return fail("Select people, phases, a week range and an update mode", 400, "validation_error")
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            weeks = [week for week in week_dates(start_week,
                     ((date.fromisoformat(end_week)-date.fromisoformat(start_week)).days // 7)+1)
                     if week <= end_week]
            per_week = value / max(1, len(weeks)) if mode == "spread" else value
            updated = 0
            for phase_id in phase_ids:
                if not phase_owned(db, eid, phase_id):
                    return fail("Phase does not belong to engagement", 400, "scope_mismatch")
                for member_id in member_ids:
                    member = db.execute("SELECT 1 FROM team_members WHERE id=? AND engagement_id=?",
                                        (member_id, eid)).fetchone()
                    if not member:
                        return fail("Team member does not belong to engagement", 400, "scope_mismatch")
                    for week in weeks:
                        upsert_phase_week(db, phase_id, member_id,
                                          {"week_start_date": week, "forecasted_hours": per_week})
                        updated += 1
            touch(db, eid)
            return ok({"updated": updated, "forecasted_hours": per_week})

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
        backup_path = automatic_backup(Path(app.config["DATABASE_PATH"]), "pre_adjustment_delete")
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            cursor = db.execute("DELETE FROM budget_adjustments WHERE id=? AND engagement_id=?", (adj_id, eid))
            sync_adjustment_columns(db, eid)
            if cursor.rowcount:
                record_event(db, eid, "adjustment_deleted", f"Deleted budget adjustment {adj_id}")
                return ok({"deleted": True, "backup_path": str(backup_path) if backup_path else None})
            return fail("Not found", 404, "not_found")

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
            automatic_backup(Path(app.config["DATABASE_PATH"]), "pre_revision")
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
            record_event(db, eid, "budget_revised",
                         f"{field} changed from {old} to {new}: {reason}")
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
        backup_path = automatic_backup(Path(app.config["DATABASE_PATH"]), "pre_expense_delete")
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            cursor = db.execute("DELETE FROM expenses WHERE id=? AND engagement_id=?", (expense_id, eid))
            if cursor.rowcount:
                record_event(db, eid, "expense_deleted", f"Deleted expense {expense_id}")
                return ok({"deleted": True, "backup_path": str(backup_path) if backup_path else None})
            return fail("Not found", 404, "not_found")

    @app.post("/api/engagements/<int:eid>/import/preview")
    def import_preview(eid):
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements do not accept imports", 409, "engagement_closed")
            try:
                parsed, covered_period = read_import_payload()
            except ValueError as exc:
                return fail(str(exc), 400, "validation_error")
            missing = validate_columns(parsed)
            if missing:
                return fail("Import is missing expected columns", 400, "validation_error", missing)
            preview = preview_rows(db, eid, parsed, covered_period)
            IMPORT_PREVIEWS[eid] = preview
            return ok(preview)

    @app.post("/api/engagements/<int:eid>/import/commit")
    def import_commit(eid):
        payload = request.get_json(silent=True) or {}
        preview = IMPORT_PREVIEWS.get(eid)
        if preview is None:
            return fail("No import preview available", 400, "missing_preview")
        rows = preview["rows"]
        removals = preview.get("rows_to_remove") or []
        if removals and not bool(payload.get("confirm_removals")):
            return fail("Removals require explicit confirmation", 409, "removal_confirmation_required",
                        extra={"rows_to_remove": removals})
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
                row["flags"] = [flag for flag in row.get("flags", []) if flag != "unmatched_phase"]
            if include:
                selected.append(row)
        if not selected and not removals:
            IMPORT_PREVIEWS.pop(eid, None)
            return ok({"snapshot_id": None, "imported": 0, "skipped": len(rows),
                       "duplicates": preview_duplicates, "row_count": 0})
        backup_path = automatic_backup(Path(app.config["DATABASE_PATH"]), "pre_import")
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            was_planning = bool(engagement and engagement["status"] == "planning")
            for phase_id in {row.get("matched_phase_id") for row in selected if row.get("matched_phase_id")}:
                if not phase_owned(db, eid, phase_id):
                    return fail("Phase assignment does not belong to engagement", 400, "scope_mismatch")
            week_end = preview.get("covered_end_date") or max(
                (row["week_end_date"] for row in selected if row.get("week_end_date")), default=now_iso()[:10])
            cursor = db.execute("""INSERT INTO weekly_snapshots
                (engagement_id,week_end_date,imported_at,row_count,notes,covered_start_date,
                 covered_end_date,rows_inserted,rows_updated,rows_removed)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (eid, week_end, now_iso(), len(selected), payload.get("notes", ""),
                 preview.get("covered_start_date"), preview.get("covered_end_date"),
                 preview.get("rows_to_insert", 0), preview.get("rows_to_update", 0), len(removals)))
            snapshot_id = int(cursor.lastrowid)
            inserted = updated = 0
            for row in selected:
                entry_id, action = upsert_time_entry(db, snapshot_id, eid, row)
                inserted += int(action == "insert")
                updated += int(action == "update")
                sync_import_exceptions(db, eid, snapshot_id, entry_id, row)
            removed = 0
            for item in removals:
                db.execute("DELETE FROM import_exceptions WHERE engagement_id=? AND transaction_id=?",
                           (eid, item["transaction_id"]))
                removed += db.execute("DELETE FROM time_entries WHERE id=? AND engagement_id=?",
                                      (int(item["id"]), eid)).rowcount
            if selected or removals:
                db.execute("UPDATE engagements SET status='active', updated_at=? WHERE id=? AND status='planning'",
                           (now_iso(), eid))
                record_event(db, eid, "import_committed",
                             f"Reconciled Cognos period: {inserted} inserted, {updated} updated, {removed} removed")
                if was_planning:
                    record_event(db, eid, "status_active", "Baseline locked by first committed import")
                metrics = engagement_metrics(db, eid)
                prior = db.execute("""SELECT realization_value FROM weekly_snapshots
                    WHERE engagement_id=? AND id<>? AND realization_value IS NOT NULL
                    ORDER BY imported_at DESC,id DESC LIMIT 1""", (eid, snapshot_id)).fetchone()
                realization = metrics.get("realization")
                delta = (realization-as_float(prior["realization_value"])) if realization is not None and prior else None
                db.execute("UPDATE weekly_snapshots SET realization_value=?,realization_delta=? WHERE id=?",
                           (realization, delta, snapshot_id))
        IMPORT_PREVIEWS.pop(eid, None)
        return ok({"snapshot_id": snapshot_id, "imported": inserted, "updated": updated,
                   "removed": removed, "skipped": len(rows)-len(selected),
                   "duplicates": preview_duplicates, "row_count": len(selected),
                   "backup_path": str(backup_path) if backup_path else None}, 201)

    @app.get("/api/engagements/<int:eid>/exceptions")
    def get_exceptions(eid):
        with conn() as db:
            if not get_engagement_row(db, eid):
                return fail("Not found", 404, "not_found")
            rows = db.execute("""SELECT ie.*,te.fees_std_rate,te.matched_phase_id,
                te.matched_team_member_id,te.memo,te.task_desc,te.week_end_date FROM import_exceptions ie
                LEFT JOIN time_entries te ON te.id=ie.time_entry_id
                WHERE ie.engagement_id=? ORDER BY CASE ie.status WHEN 'pending' THEN 0 ELSE 1 END,ie.id DESC""",
                (eid,)).fetchall()
            exceptions = rows_to_dicts(rows)
            phase_rows = db.execute(
                "SELECT id,phase_name,phase_code FROM phases WHERE engagement_id=?", (eid,)).fetchall()
            phases = rows_to_dicts(phase_rows)
            for exception in exceptions:
                exception["phase_candidates"] = []
                exception["memo_suggestion"] = None
                if exception["exception_code"] != "unmatched_phase" or exception["status"] != "pending":
                    continue
                exception["memo_suggestion"] = suggest_from_memo(exception.get("memo") or "", phases)
                team_member_id = exception.get("matched_team_member_id")
                monday = week_monday(exception.get("week_end_date"))
                if team_member_id and monday:
                    week_minus_1 = (date.fromisoformat(monday) - timedelta(days=7)).isoformat()
                    week_plus_1 = (date.fromisoformat(monday) + timedelta(days=7)).isoformat()
                    candidates = db.execute("""SELECT DISTINCT ppw.phase_id, p.phase_name
                        FROM phase_person_weeks ppw JOIN phases p ON p.id=ppw.phase_id
                        WHERE ppw.team_member_id=? AND ppw.week_start_date BETWEEN ? AND ?
                        AND (ppw.budgeted_hours>0 OR ppw.forecasted_hours>0)""",
                        (team_member_id, week_minus_1, week_plus_1)).fetchall()
                    exception["phase_candidates"] = rows_to_dicts(candidates)
            return ok(exceptions)

    @app.post("/api/engagements/<int:eid>/exceptions/<int:exception_id>/assign-team")
    def resolve_exception_team(eid, exception_id):
        payload = request.get_json(silent=True) or {}
        with conn() as db:
            exception = db.execute("SELECT * FROM import_exceptions WHERE id=? AND engagement_id=?",
                                   (exception_id, eid)).fetchone()
            if not exception:
                return fail("Not found", 404, "not_found")
            member_id = int(payload.get("team_member_id") or 0)
            member = db.execute("SELECT * FROM team_members WHERE id=? AND engagement_id=?", (member_id, eid)).fetchone()
            if not member:
                name = str(payload.get("name") or exception["worker_name"] or "").strip()
                member = db.execute("SELECT * FROM team_members WHERE engagement_id=? AND LOWER(TRIM(name))=?",
                                    (eid, name.casefold())).fetchone()
                if member:
                    member_id = int(member["id"])
                else:
                    error = validate_member({"name": name})
                    if error:
                        return error
                    member_id = insert_team_member(db, eid, {**payload, "name": name})
            db.execute("UPDATE time_entries SET matched_team_member_id=?,normalized_worker_name=? WHERE id=?",
                       (member_id, str(member["name"] if member else name).strip().casefold(), exception["time_entry_id"]))
            resolve_exception(db, exception_id, "resolved", payload.get("note") or "Assigned to team member")
            return ok({"resolved": True, "team_member_id": member_id})

    @app.post("/api/engagements/<int:eid>/exceptions/<int:exception_id>/assign-phase")
    def resolve_exception_phase(eid, exception_id):
        payload = request.get_json(silent=True) or {}
        phase_id = int(payload.get("phase_id") or 0)
        with conn() as db:
            exception = db.execute("SELECT * FROM import_exceptions WHERE id=? AND engagement_id=?",
                                   (exception_id, eid)).fetchone()
            if not exception:
                return fail("Not found", 404, "not_found")
            if not phase_owned(db, eid, phase_id):
                return fail("Phase does not belong to engagement", 400, "scope_mismatch")
            db.execute("UPDATE time_entries SET matched_phase_id=?,allocation_method='manual_assist' WHERE id=?",
                       (phase_id, exception["time_entry_id"]))
            resolve_exception(db, exception_id, "resolved", payload.get("note") or "Assigned to phase")
            entry = db.execute("SELECT matched_team_member_id FROM time_entries WHERE id=?",
                               (exception["time_entry_id"],)).fetchone()
            offer_sticky_rule = None
            team_member_id = entry["matched_team_member_id"] if entry else None
            if team_member_id:
                occurrences = db.execute("""SELECT COUNT(*) count FROM time_entries
                    WHERE matched_team_member_id=? AND matched_phase_id=? AND allocation_method='manual_assist'""",
                    (team_member_id, phase_id)).fetchone()
                if int(occurrences["count"]) >= 2:
                    offer_sticky_rule = {"team_member_id": int(team_member_id), "phase_id": phase_id}
            return ok({"resolved": True, "phase_id": phase_id, "offer_sticky_rule": offer_sticky_rule})

    @app.post("/api/engagements/<int:eid>/exceptions/<int:exception_id>/exclude")
    def exclude_exception(eid, exception_id):
        payload = request.get_json(silent=True) or {}
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            return fail("An exclusion reason is required", 400, "validation_error", ["reason"])
        with conn() as db:
            exception = db.execute("SELECT * FROM import_exceptions WHERE id=? AND engagement_id=?",
                                   (exception_id, eid)).fetchone()
            if not exception:
                return fail("Not found", 404, "not_found")
            db.execute("UPDATE time_entries SET is_excluded=1,exclusion_reason=? WHERE id=?",
                       (reason, exception["time_entry_id"]))
            db.execute("UPDATE import_exceptions SET status='excluded',resolution_note=?,updated_at=? "
                       "WHERE time_entry_id=?", (reason, now_iso(), exception["time_entry_id"]))
            return ok({"excluded": True})

    @app.get("/api/engagements/<int:eid>/allocation-rules")
    def get_allocation_rules(eid):
        with conn() as db:
            rows = db.execute("""SELECT ar.*,tm.name team_member_name,p.phase_name
                FROM allocation_rules ar
                JOIN team_members tm ON tm.id=ar.team_member_id
                JOIN phases p ON p.id=ar.phase_id
                WHERE ar.engagement_id=? ORDER BY ar.id DESC""", (eid,)).fetchall()
            return ok(rows_to_dicts(rows))

    @app.post("/api/engagements/<int:eid>/allocation-rules")
    def create_allocation_rule(eid):
        payload = request.get_json(silent=True) or {}
        team_member_id = int(payload.get("team_member_id") or 0)
        phase_id = int(payload.get("phase_id") or 0)
        with conn() as db:
            if not phase_owned(db, eid, phase_id):
                return fail("Phase does not belong to engagement", 400, "scope_mismatch")
            member = db.execute("SELECT 1 FROM team_members WHERE id=? AND engagement_id=?",
                                (team_member_id, eid)).fetchone()
            if not member:
                return fail("Team member does not belong to engagement", 400, "scope_mismatch")
            db.execute("""INSERT OR IGNORE INTO allocation_rules
                (engagement_id,team_member_id,phase_id,created_at,created_from_exception_id)
                VALUES (?,?,?,?,?)""",
                (eid, team_member_id, phase_id, now_iso(), payload.get("created_from_exception_id")))
            return ok({"created": True}, 201)

    @app.delete("/api/engagements/<int:eid>/allocation-rules/<int:rule_id>")
    def delete_allocation_rule(eid, rule_id):
        with conn() as db:
            cursor = db.execute("DELETE FROM allocation_rules WHERE id=? AND engagement_id=?", (rule_id, eid))
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            return ok({"deleted": True})

    @app.get("/api/engagements/<int:eid>/hours-overages")
    def hours_overages(eid):
        with conn() as db:
            if not get_engagement_row(db, eid):
                return fail("Not found", 404, "not_found")
            return ok(budget_overage_weeks(db, eid))

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
                cursor = db.execute(
                    f"UPDATE time_entries SET matched_phase_id=?,allocation_method='manual_assist' "
                    f"WHERE engagement_id=? AND id IN ({placeholders})", params)
            else:
                cursor = db.execute("""UPDATE time_entries SET matched_phase_id=?,allocation_method='manual_assist'
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
        backup_path = automatic_backup(Path(app.config["DATABASE_PATH"]), "pre_snapshot_delete")
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
            record_event(db, eid, "snapshot_deleted", f"Deleted import snapshot {snapshot_id}")
            return ok({"deleted": True, "backup_path": str(backup_path) if backup_path else None})

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

    @app.get("/api/engagements/<int:eid>/export/scheduling")
    def export_scheduling(eid):
        with conn() as db:
            try:
                filename, content = build_scheduling_csv(db, eid)
            except ValueError:
                return fail("Not found", 404, "not_found")
        return Response(content, mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/engagements/<int:eid>/rate-tiers")
    def get_rate_tiers(eid):
        with conn() as db:
            if not get_engagement_row(db, eid):
                return fail("Not found", 404, "not_found")
            return ok(rows_to_dicts(db.execute(
                "SELECT * FROM engagement_rate_tiers WHERE engagement_id=? ORDER BY tier_order,id",
                (eid,)).fetchall()))

    @app.put("/api/engagements/<int:eid>/rate-tiers")
    def put_rate_tiers(eid):
        payload = request.get_json(silent=True) or {}
        tiers = payload.get("tiers") or []
        with conn() as db:
            engagement = get_engagement_row(db, eid)
            if not engagement:
                return fail("Not found", 404, "not_found")
            if engagement["status"] == "closed":
                return fail("Closed engagements are read-only", 409, "engagement_closed")
            db.execute("DELETE FROM engagement_rate_tiers WHERE engagement_id=?", (eid,))
            for order, tier in enumerate(tiers):
                name = str(tier.get("tier_name") or "").strip()
                if not name:
                    return fail("Tier name is required", 400, "validation_error", ["tier_name"])
                db.execute("""INSERT INTO engagement_rate_tiers
                    (engagement_id,tier_name,tier_amount,tier_order) VALUES (?,?,?,?)""",
                    (eid, name, as_float(tier.get("tier_amount")), order))
            db.execute("UPDATE engagements SET rate_mode='flat_tiered',updated_at=? WHERE id=?", (now_iso(), eid))
            return ok(rows_to_dicts(db.execute(
                "SELECT * FROM engagement_rate_tiers WHERE engagement_id=? ORDER BY tier_order,id",
                (eid,)).fetchall()))

    @app.get("/api/settings/rate-cards")
    def get_rate_cards():
        with conn() as db:
            cards = rows_to_dicts(db.execute("SELECT * FROM rate_cards ORDER BY is_active DESC, id").fetchall())
            for card in cards:
                card["rates"] = rows_to_dicts(db.execute(
                    "SELECT * FROM rate_card_rates WHERE rate_card_id=? ORDER BY role_name", (card["id"],)).fetchall())
            return ok({"rate_cards": cards})

    @app.put("/api/settings/rate-cards")
    def put_rate_cards():
        payload = request.get_json(silent=True) or {}
        rates = payload.get("rates") or []
        with conn() as db:
            card = db.execute("SELECT id FROM rate_cards WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
            if not card:
                card = db.execute("SELECT id FROM rate_cards ORDER BY id LIMIT 1").fetchone()
            if not card:
                card_id = int(db.execute(
                    "INSERT INTO rate_cards(name,is_active,created_at) VALUES (?,?,?)",
                    (str(payload.get("name") or "Current governed rates"), 1, now_iso())).lastrowid)
            else:
                card_id = int(card["id"])
            seen = set()
            for rate in rates:
                role = str(rate.get("role_name") or "").strip()
                if not role:
                    return fail("Role name is required", 400, "validation_error", ["role_name"])
                seen.add(role.casefold())
                existing = db.execute(
                    "SELECT * FROM rate_card_rates WHERE rate_card_id=? AND role_name=? COLLATE NOCASE",
                    (card_id, role)).fetchone()
                new_standard = as_float(rate.get("standard_rate"))
                if existing and existing["locked_at"] is not None and as_float(existing["standard_rate"]) != new_standard:
                    return fail("This rate is in use. Create a new rate card vintage to change it.",
                                409, "rate_locked", extra={"rate_id": existing["id"], "role_name": role})
                standard_to_write = as_float(existing["standard_rate"]) if existing and existing["locked_at"] is not None else new_standard
                db.execute("""INSERT INTO rate_card_rates
                    (rate_card_id,role_name,standard_rate,engagement_rate,contract_rate,dte_rate)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(rate_card_id,role_name) DO UPDATE SET
                    standard_rate=excluded.standard_rate,engagement_rate=excluded.engagement_rate,
                    contract_rate=excluded.contract_rate,dte_rate=excluded.dte_rate""",
                    (card_id, role, standard_to_write,
                     as_float(rate.get("engagement_rate")), as_float(rate.get("contract_rate")),
                     as_float(rate.get("dte_rate"))))
            if seen:
                existing_rows = db.execute(
                    "SELECT id,role_name,locked_at FROM rate_card_rates WHERE rate_card_id=?", (card_id,)).fetchall()
                for row in existing_rows:
                    if str(row["role_name"]).casefold() not in seen:
                        if row["locked_at"] is not None:
                            return fail("This rate is in use. Create a new rate card vintage to change it.",
                                        409, "rate_locked", extra={"rate_id": row["id"], "role_name": row["role_name"]})
                        db.execute("DELETE FROM rate_card_rates WHERE id=?", (row["id"],))
            rows = rows_to_dicts(db.execute(
                "SELECT * FROM rate_card_rates WHERE rate_card_id=? ORDER BY role_name", (card_id,)).fetchall())
            return ok({"rate_cards": [{"id": card_id,
                       "name": str(payload.get("name") or "Current governed rates"), "rates": rows}]})

    @app.post("/api/settings/rate-cards")
    def create_rate_card():
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            return fail("Name is required", 400, "validation_error", ["name"])
        rates = payload.get("rates") or []
        with conn() as db:
            try:
                card_id = int(db.execute(
                    "INSERT INTO rate_cards(name,is_active,created_at) VALUES (?,0,?)",
                    (name, now_iso())).lastrowid)
            except sqlite3.IntegrityError:
                return fail("A rate card with this name already exists", 409, "duplicate_rate_card_name")
            for rate in rates:
                role = str(rate.get("role_name") or "").strip()
                if not role:
                    return fail("Role name is required", 400, "validation_error", ["role_name"])
                db.execute("""INSERT INTO rate_card_rates
                    (rate_card_id,role_name,standard_rate,engagement_rate,contract_rate,dte_rate)
                    VALUES (?,?,?,?,?,?)""",
                    (card_id, role, as_float(rate.get("standard_rate")),
                     as_float(rate.get("engagement_rate")), as_float(rate.get("contract_rate")),
                     as_float(rate.get("dte_rate"))))
            rows = rows_to_dicts(db.execute(
                "SELECT * FROM rate_card_rates WHERE rate_card_id=? ORDER BY role_name", (card_id,)).fetchall())
            return ok({"rate_card": {"id": card_id, "name": name, "is_active": 0, "rates": rows}}, 201)

    @app.post("/api/settings/rate-cards/<int:card_id>/activate")
    def activate_rate_card(card_id):
        with conn() as db:
            card = db.execute("SELECT id FROM rate_cards WHERE id=?", (card_id,)).fetchone()
            if not card:
                return fail("Not found", 404, "not_found")
            db.execute("UPDATE rate_cards SET is_active=0")
            db.execute("UPDATE rate_cards SET is_active=1 WHERE id=?", (card_id,))
            cards = rows_to_dicts(db.execute("SELECT * FROM rate_cards ORDER BY is_active DESC, id").fetchall())
            for item in cards:
                item["rates"] = rows_to_dicts(db.execute(
                    "SELECT * FROM rate_card_rates WHERE rate_card_id=? ORDER BY role_name", (item["id"],)).fetchall())
            return ok({"rate_cards": cards})

    @app.get("/api/settings/rates")
    def get_settings():
        with conn() as db:
            data = get_app_settings(db)
            path = Path(app.config["DATABASE_PATH"])
            recent = latest_backup(path)
            data.update({"db_path": str(path), "db_modified": path.stat().st_mtime if path.exists() else None,
                         "latest_backup_path": str(recent) if recent else None,
                         "latest_backup_modified": recent.stat().st_mtime if recent else None,
                         "schema_version": SCHEMA_VERSION, "app_version": APP_VERSION})
            return ok(data)

    @app.put("/api/settings/rates")
    def update_settings():
        payload = request.get_json(silent=True) or {}
        with conn() as db:
            if isinstance(payload.get("rates"), dict):
                set_rates(db, payload["rates"])
            for key in ("engagement_discount_rate", "contract_discount_rate",
                        "variance_threshold_hours", "variance_threshold_pct", "confidence_threshold_pct"):
                if key in payload:
                    set_setting(db, key, as_float(payload[key]))
            return ok(get_app_settings(db))

    @app.get("/api/settings/backup")
    def backup():
        path = Path(app.config["DATABASE_PATH"])
        if not path.exists():
            return fail("Database not found", 404, "not_found")
        return send_file(path, as_attachment=True, download_name=f"budget_tracker_backup_{now_iso()[:10]}.db")

    @app.post("/api/settings/backup")
    def create_backup():
        path = Path(app.config["DATABASE_PATH"])
        backup_path = automatic_backup(path, "manual")
        return ok({"path": str(backup_path) if backup_path else None,
                   "created_at": now_iso()})

    @app.post("/api/settings/restore")
    def restore_backup():
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return fail("Choose a database backup to restore", 400, "validation_error", ["file"])
        path = Path(app.config["DATABASE_PATH"])
        temp = path.with_name(f"{path.name}.restore")
        try:
            uploaded.save(temp)
            candidate = sqlite3.connect(temp)
            try:
                integrity = candidate.execute("PRAGMA integrity_check").fetchone()[0]
                tables = {row[0] for row in candidate.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            finally:
                candidate.close()
            if integrity != "ok" or not {"engagements", "settings", "schema_migrations"}.issubset(tables):
                return fail("The selected file is not a valid tracker backup", 400, "invalid_backup")
            preserved = automatic_backup(path, "pre_restore")
            os.replace(temp, path)
            init_db(path)
            IMPORT_PREVIEWS.clear()
            return ok({"restored": True, "preserved_backup": str(preserved) if preserved else None})
        finally:
            temp.unlink(missing_ok=True)

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


def week_dates(first_monday, duration_weeks):
    if not first_monday:
        return []
    start = date.fromisoformat(str(first_monday)[:10])
    return [(start + timedelta(days=7 * index)).isoformat() for index in range(int(duration_weeks or 1))]


def get_engagement_row(db, eid):
    return db.execute("SELECT * FROM engagements WHERE id=?", (eid,)).fetchone()


def touch(db, eid):
    db.execute("UPDATE engagements SET updated_at=? WHERE id=?", (now_iso(), eid))


def valid_worker_name(name: str) -> bool:
    parts = [part.strip() for part in name.split(",")]
    return len(parts) == 2 and all(parts)


def validate_proposal_pricing(db, info, people, current=None):
    basis = str(info.get("rate_basis") or (current["rate_basis"] if current else "standard"))
    if basis not in PROPOSAL_RATE_BASES:
        return fail("Choose a valid proposal rate source", 400, "validation_error", ["rate_basis"])
    try:
        proposal_discount = float(
            info.get("discount_rate")
            if info.get("discount_rate") not in (None, "")
            else (current["discount_rate"] if current else 0)
        )
    except (TypeError, ValueError):
        return fail("Discount must be a number from 0 through 100 percent", 400, "validation_error", ["discount_rate"])
    if not 0 <= proposal_discount <= 1:
        return fail("Discount must be from 0 through 100 percent", 400, "validation_error", ["discount_rate"])
    governed_roles = {
        normalize_role_key(row["role_name"])
        for row in db.execute(
            """SELECT r.role_name FROM rate_card_rates r
            JOIN rate_cards c ON c.id=r.rate_card_id WHERE c.is_active=1"""
        ).fetchall()
    }
    for index, person in enumerate(people):
        role = str(person.get("role") or "").strip()
        if not role or normalize_role_key(role) not in governed_roles:
            return fail(
                "Choose a role from the governed rate card",
                400,
                "validation_error",
                [f"people.{index}.role"],
            )
        raw_discount = person.get("discount_rate")
        if raw_discount in (None, ""):
            raw_discount = proposal_discount
        try:
            person_discount = float(raw_discount)
        except (TypeError, ValueError):
            return fail("Person discount must be a number", 400, "validation_error", [f"people.{index}.discount_rate"])
        if not 0 <= person_discount <= 1:
            return fail("Person discount must be from 0 through 100 percent", 400, "validation_error", [f"people.{index}.discount_rate"])
    return None


def validate_member(member):
    name = str(member.get("name") or "").strip()
    if not name:
        return fail("Missing required field", 400, "validation_error", ["name"])
    if not valid_worker_name(name):
        return fail("Name must use Last, First format", 400, "validation_error", ["name"])
    return None


def find_governed_rate(db, role):
    role_key = normalize_role_key(role)
    if not role_key:
        return None
    for candidate in db.execute(
        """SELECT r.* FROM rate_card_rates r JOIN rate_cards c ON c.id=r.rate_card_id
        WHERE c.is_active=1 ORDER BY c.id"""
    ).fetchall():
        if normalize_role_key(candidate["role_name"]) == role_key:
            return candidate
    return None


def insert_team_member(db, eid, member):
    settings = get_app_settings(db)
    role = str(member.get("role") or "").strip()
    governed = find_governed_rate(db, role)
    if governed:
        db.execute("UPDATE rate_card_rates SET locked_at=COALESCE(locked_at, ?) WHERE id=?",
                   (now_iso(), int(governed["id"])))
    # Standard rate is never client-editable: it always follows the role's governed rate.
    internal = as_float(governed["standard_rate"]) if governed else as_float(member.get("internal_rate", 0))
    engagement_rate = member.get("engagement_rate")
    engagement = get_engagement_row(db, eid)
    tier_id = int(member.get("rate_tier_id") or 0)
    if engagement and engagement["rate_mode"] == "flat_tiered" and tier_id:
        tier = db.execute("SELECT * FROM engagement_rate_tiers WHERE id=? AND engagement_id=?",
                          (tier_id, eid)).fetchone()
        if not tier:
            raise ValueError("Rate tier does not belong to engagement")
        engagement_rate = tier["tier_amount"]
    elif governed and engagement_rate in (None, ""):
        engagement_rate = governed["engagement_rate"]
    if engagement_rate in (None, ""):
        engagement_rate = internal * (1-settings["engagement_discount_rate"])
    # Contract rate and advance billing rate are no longer distinct inputs: contract rate
    # always mirrors engagement rate, and advance billing rate is retired (always 0).
    contract_rate = engagement_rate
    dte_rate = 0
    cursor = db.execute("""INSERT INTO team_members
        (engagement_id,name,role,is_offshore,internal_rate,engagement_rate,contract_rate,dte_rate,
         rate_tier_id,is_custom_rate,custom_rate_note,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (eid, str(member.get("name") or "").strip(), role,
         int(bool(member.get("is_offshore"))), internal, as_float(engagement_rate),
         as_float(contract_rate), as_float(dte_rate), tier_id or None,
         int(bool(member.get("is_custom_rate"))), member.get("custom_rate_reason"), now_iso()))
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
    record_event(db, eid, "engagement_created", "Engagement created in Planning status")
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


def insert_proposal_bundle(db, info, people, weekly_rows):
    now = now_iso()
    cursor = db.execute(
        """INSERT INTO proposals
        (proposal_code,client_name,engagement_type,first_monday,duration_weeks,rate_basis,
         discount_rate,notes,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            str(info["proposal_code"]).strip(),
            str(info["client_name"]).strip(),
            info.get("engagement_type"),
            info.get("first_monday"),
            int(info.get("duration_weeks") or 1),
            str(info.get("rate_basis") or "standard"),
            as_float(info.get("discount_rate")),
            info.get("notes"),
            now,
            now,
        ),
    )
    pid = int(cursor.lastrowid)
    replace_proposal_bundle(db, pid, {}, people, weekly_rows, update_header=False)
    return pid


def replace_proposal_bundle(db, pid, info, people, weekly_rows, update_header=True):
    if update_header and info:
        updates = {key: info[key] for key in {"proposal_code", "client_name", "engagement_type", "first_monday", "duration_weeks", "rate_basis", "discount_rate", "notes"} if key in info}
        if updates:
            updates["updated_at"] = now_iso()
            updates["id"] = pid
            assignments = ", ".join(f"{key}=:{key}" for key in updates if key != "id")
            db.execute(f"UPDATE proposals SET {assignments} WHERE id=:id", updates)
    existing_ids = {
        int(row["id"]): row
        for row in db.execute("SELECT * FROM proposal_people WHERE proposal_id=?", (pid,)).fetchall()
    }
    keep_ids: list[int] = []
    proposal = db.execute("SELECT rate_basis,discount_rate FROM proposals WHERE id=?", (pid,)).fetchone()
    basis = str(proposal["rate_basis"] or "standard")
    rate_field = PROPOSAL_RATE_BASES[basis]
    for person in people:
        person_id = int(person["id"]) if person.get("id") else 0
        existing = existing_ids.get(person_id)
        role = str(person.get("role") or (existing["role"] if existing else "")).strip()
        governed = find_governed_rate(db, role)
        base_rate = as_float(governed[rate_field] if governed else person.get("base_rate"))
        raw_discount = person.get("discount_rate")
        if raw_discount in (None, ""):
            raw_discount = existing["discount_rate"] if existing else proposal["discount_rate"]
        discount_rate = as_float(raw_discount)
        rough_rate = money(base_rate * (1 - discount_rate))
        if person_id and person_id in existing_ids:
            db.execute(
                """UPDATE proposal_people
                SET name=?, role=?, base_rate=?, discount_rate=?, rough_rate=?
                WHERE id=? AND proposal_id=?""",
                (str(person.get("name") or "").strip(), role, base_rate, discount_rate,
                 rough_rate, person_id, pid),
            )
            keep_ids.append(person_id)
        else:
            created = db.execute(
                """INSERT INTO proposal_people
                (proposal_id,name,role,base_rate,discount_rate,rough_rate,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (pid, str(person.get("name") or "").strip(), role, base_rate,
                 discount_rate, rough_rate, now_iso()),
            )
            keep_ids.append(int(created.lastrowid))
    for stale_id in existing_ids:
        if stale_id not in keep_ids:
            db.execute("DELETE FROM proposal_people WHERE id=?", (stale_id,))
    db.execute(
        """
        DELETE FROM proposal_person_weeks
        WHERE proposal_person_id IN (SELECT id FROM proposal_people WHERE proposal_id=?)
        """,
        (pid,),
    )
    if weekly_rows:
        for row in weekly_rows:
            person_ref = int(row.get("proposal_person_id") or 0)
            if not person_ref and row.get("person_index") is not None:
                person_ref = keep_ids[int(row["person_index"])]
            db.execute(
                """INSERT INTO proposal_person_weeks
                (proposal_person_id,week_start_date,budgeted_hours,forecasted_hours)
                VALUES (?,?,?,?)""",
                (
                    person_ref,
                    row.get("week_start_date"),
                    as_float(row.get("budgeted_hours")),
                    None if row.get("forecasted_hours") in (None, "") else as_float(row.get("forecasted_hours")),
                ),
            )
    else:
        proposal = db.execute("SELECT first_monday,duration_weeks FROM proposals WHERE id=?", (pid,)).fetchone()
        weeks = week_dates(str(proposal["first_monday"] or ""), int(proposal["duration_weeks"] or 1))
        for index, person in enumerate(people):
            total_hours = as_float(person.get("budgeted_hours"))
            per_week = total_hours / max(1, len(weeks)) if weeks else total_hours
            for week in weeks:
                db.execute(
                    """INSERT INTO proposal_person_weeks
                    (proposal_person_id,week_start_date,budgeted_hours,forecasted_hours)
                    VALUES (?,?,?,NULL)""",
                    (keep_ids[index], week, per_week),
                )
    db.execute("UPDATE proposals SET updated_at=? WHERE id=?", (now_iso(), pid))


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
                VALUES (?,?,?,?,NULL)""", (phase_ids[0], member_id,
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
        "events": list_events(db, eid),
    }


def proposal_list(db):
    proposals = db.execute("SELECT * FROM proposals ORDER BY updated_at DESC, id DESC").fetchall()
    return [proposal_summary(db, int(row["id"])) for row in proposals]


def proposal_summary(db, pid):
    proposal = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
    if not proposal:
        return None
    metrics = proposal_metrics(db, pid)
    item = row_to_dict(proposal) or {}
    item["metrics"] = metrics
    return item


def proposal_metrics(db, pid):
    row = db.execute(
        """
        SELECT COUNT(DISTINCT pp.id) people_count,
               COALESCE(SUM(ppw.budgeted_hours), 0) budgeted_hours,
               COALESCE(SUM(COALESCE(ppw.forecasted_hours, ppw.budgeted_hours)), 0) forecast_hours,
               COALESCE(SUM(COALESCE(ppw.forecasted_hours, ppw.budgeted_hours) * COALESCE(pp.base_rate, pp.rough_rate, 0)), 0) estimated_base_fees,
               COALESCE(SUM(ppw.budgeted_hours * COALESCE(pp.rough_rate, 0)), 0) estimated_budget_fees,
               COALESCE(SUM(COALESCE(ppw.forecasted_hours, ppw.budgeted_hours) * COALESCE(pp.rough_rate, 0)), 0) estimated_fees
        FROM proposal_people pp
        LEFT JOIN proposal_person_weeks ppw ON ppw.proposal_person_id = pp.id
        WHERE pp.proposal_id=?
        """,
        (pid,),
    ).fetchone()
    return {
        "people_count": int(row["people_count"] or 0),
        "budgeted_hours": as_float(row["budgeted_hours"]),
        "forecast_hours": as_float(row["forecast_hours"]),
        "estimated_base_fees": money(row["estimated_base_fees"]),
        "estimated_discount_amount": money(row["estimated_base_fees"] - row["estimated_fees"]),
        "estimated_budget_fees": money(row["estimated_budget_fees"]),
        "estimated_fees": money(row["estimated_fees"]),
    }


def full_proposal(db, pid):
    proposal = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
    if not proposal:
        return None
    people_rows = db.execute(
        "SELECT * FROM proposal_people WHERE proposal_id=? ORDER BY id", (pid,)
    ).fetchall()
    people = []
    for person in people_rows:
        weeks = rows_to_dicts(
            db.execute(
                """
                SELECT * FROM proposal_person_weeks
                WHERE proposal_person_id=?
                ORDER BY week_start_date, id
                """,
                (person["id"],),
            ).fetchall()
        )
        info = row_to_dict(person) or {}
        info["weeks"] = weeks
        info["total_hours"] = round(sum(as_float(week["budgeted_hours"]) for week in weeks), 2)
        info["forecast_hours"] = round(
            sum(as_float(week["forecasted_hours"]) if week["forecasted_hours"] is not None else as_float(week["budgeted_hours"]) for week in weeks),
            2,
        )
        info["estimated_fees"] = money(info["forecast_hours"] * as_float(info.get("rough_rate")))
        info["estimated_base_fees"] = money(
            info["forecast_hours"] * as_float(info.get("base_rate") or info.get("rough_rate"))
        )
        info["estimated_discount_amount"] = money(
            info["estimated_base_fees"] - info["estimated_fees"]
        )
        people.append(info)
    return {
        "proposal": row_to_dict(proposal),
        "metrics": proposal_metrics(db, pid),
        "people": people,
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


def list_events(db, eid):
    return rows_to_dicts(db.execute("""SELECT * FROM engagement_events
        WHERE engagement_id=? ORDER BY created_at DESC,id DESC""", (eid,)).fetchall())


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
    if "forecasted_hours" in item:
        raw_forecast = item.get("forecasted_hours")
        forecast = None if raw_forecast in (None, "") else as_float(raw_forecast)
    else:
        forecast = existing["forecasted_hours"] if existing else None
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


def phase_has_actuals(db, eid, phase_id):
    return db.execute("""SELECT 1 FROM time_entries WHERE engagement_id=? AND matched_phase_id=?
        AND COALESCE(is_excluded,0)=0 LIMIT 1""", (eid, phase_id)).fetchone() is not None


def revision_target(db, eid, target_type, target_id):
    if target_type == "phase":
        return db.execute("SELECT * FROM phases WHERE id=? AND engagement_id=?", (target_id, eid)).fetchone()
    if target_type == "team_member":
        return db.execute("SELECT * FROM team_members WHERE id=? AND engagement_id=?", (target_id, eid)).fetchone()
    return db.execute("""SELECT ppw.*,p.engagement_id FROM phase_person_weeks ppw
        JOIN phases p ON p.id=ppw.phase_id WHERE ppw.id=? AND p.engagement_id=?""", (target_id, eid)).fetchone()


def budget_locked(eid, target_type, target_id, field_name=None):
    endpoint = f"/api/engagements/{eid}/revisions"
    extra = {"revision_endpoint": endpoint, "target_type": target_type, "target_id": target_id}
    if field_name:
        extra["field_name"] = field_name
    return fail("Budget is locked. Record a reasoned revision.", 409, "budget_locked",
                extra=extra)


def record_event(db, eid, event_type, description):
    db.execute("""INSERT INTO engagement_events
        (engagement_id,event_type,description,created_at) VALUES (?,?,?,?)""",
        (eid, event_type, str(description).strip(), now_iso()))


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
            return parse_xlsx_export(content), covered_period_from_xlsx(content)
        text = content.decode("utf-8-sig")
        return parse_text_export(text), covered_period_from_text(text)
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if not text:
        raise ValueError("Paste text or upload a CSV/XLSX file")
    return parse_text_export(text), covered_period_from_text(text)


def insert_time_entry(db, snapshot_id, eid, row):
    cursor = db.execute("""INSERT INTO time_entries
        (snapshot_id,engagement_id,transaction_id,worker_name,worker_id,title,
         worker_bu_du_cc,competency_center,entry_date,week_end_date,financial_period,
         project_id,project_name,xref,phase_desc,task_desc,work_location,billing_status,
         hours,fees_std_rate,fees_contract_rate,memo,normalized_worker_name,
         matched_team_member_id,matched_phase_id,allocation_method)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (snapshot_id, eid, row["transaction_id"], row["worker_name"], row["worker_id"],
         row["title"], row.get("worker_bu_du_cc"), row.get("competency_center"),
         row["entry_date"], row["week_end_date"], row["financial_period"],
         row.get("project_id"), row.get("project"), row.get("xref"), row["phase_desc"],
         row["task_desc"], row["work_location"], row["billing_status"], row["hours"],
         row["fees_std_rate"], row["fees_contract_rate"], row["memo"],
         str(row.get("normalized_worker_name") or row.get("worker_name") or "").strip().casefold(),
         row.get("matched_team_member_id"), row.get("matched_phase_id"), row.get("allocation_method")))
    return int(cursor.lastrowid)


def upsert_time_entry(db, snapshot_id, eid, row):
    existing = db.execute("SELECT id FROM time_entries WHERE engagement_id=? AND transaction_id=?",
                          (eid, row["transaction_id"])).fetchone()
    if not existing:
        return insert_time_entry(db, snapshot_id, eid, row), "insert"
    fields = ["worker_name", "worker_id", "title", "worker_bu_du_cc", "competency_center",
              "entry_date", "week_end_date", "financial_period", "project_id", "project_name",
              "xref", "phase_desc", "task_desc", "work_location", "billing_status", "hours",
              "fees_std_rate", "fees_contract_rate", "memo", "normalized_worker_name",
              "matched_team_member_id", "matched_phase_id", "allocation_method"]
    values = {
        "project_name": row.get("project"),
        **{field: row.get(field) for field in fields if field != "project_name"},
        "snapshot_id": snapshot_id, "id": int(existing["id"]),
    }
    assignments = ",".join(f"{field}=:{field}" for field in ["snapshot_id", *fields])
    db.execute(f"UPDATE time_entries SET {assignments},is_excluded=0,exclusion_reason=NULL WHERE id=:id", values)
    return int(existing["id"]), "update" if row.get("reconciliation_action") == "update" else "unchanged"


def sync_import_exceptions(db, eid, snapshot_id, entry_id, row):
    exception_codes = [flag for flag in row.get("flags", [])
                       if flag in {"worker_unknown", "worker_unauthorized", "project_mismatch", "unmatched_phase"}]
    if exception_codes:
        placeholders = ",".join("?" for _ in exception_codes)
        db.execute(f"DELETE FROM import_exceptions WHERE time_entry_id=? AND exception_code NOT IN ({placeholders})",
                   (entry_id, *exception_codes))
    else:
        db.execute("DELETE FROM import_exceptions WHERE time_entry_id=?", (entry_id,))
    for code in exception_codes:
        db.execute("""INSERT INTO import_exceptions
            (engagement_id,transaction_id,worker_name,normalized_worker_name,phase_desc,
             exception_code,status,hours,fees_contract_rate,snapshot_id,time_entry_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,'pending',?,?,?,?,?,?)
            ON CONFLICT(time_entry_id,exception_code) WHERE time_entry_id IS NOT NULL
            DO UPDATE SET status='pending',hours=excluded.hours,
            fees_contract_rate=excluded.fees_contract_rate,snapshot_id=excluded.snapshot_id,
            resolution_note=NULL,updated_at=excluded.updated_at""",
            (eid, row["transaction_id"], row["worker_name"], row.get("normalized_worker_name"),
             row.get("phase_desc"), code, row.get("hours"), row.get("fees_contract_rate"),
             snapshot_id, entry_id, now_iso(), now_iso()))


def resolve_exception(db, exception_id, status, note):
    db.execute("UPDATE import_exceptions SET status=?,resolution_note=?,updated_at=? WHERE id=?",
               (status, str(note or "").strip(), now_iso(), exception_id))


def find_running_tracker(ports=PORT_CANDIDATES):
    for port in ports:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health", timeout=0.35) as response:
                data = json.loads(response.read().decode("utf-8")).get("data") or {}
                if (data.get("status") == "ok" and data.get("app_version")
                        and data.get("schema_version")):
                    return f"http://127.0.0.1:{port}/"
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return None


def find_available_port(ports=PORT_CANDIDATES):
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


def open_browser_when_ready(url, port):
    for _ in range(40):
        if find_running_tracker((port,)):
            webbrowser.open(url)
            return
        time.sleep(0.25)


def show_startup_error(message):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "B2A Budget Tracker", 0x10)
    else:
        print(message)


def run_local_app():
    explicit_port = os.environ.get("BUDGET_TRACKER_PORT")
    open_browser = (bool(getattr(sys, "frozen", False))
                    and os.environ.get("BUDGET_TRACKER_NO_BROWSER") != "1")
    if explicit_port:
        try:
            port = int(explicit_port)
        except ValueError:
            show_startup_error("The configured application port is invalid. Contact support.")
            return
    else:
        existing = find_running_tracker()
        if existing:
            if open_browser:
                webbrowser.open(existing)
            return
        port = find_available_port()
        if port is None:
            show_startup_error(
                "Ports 5000 through 5004 are already in use. "
                "Close another local application and try again.")
            return

    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        threading.Thread(
            target=open_browser_when_ready, args=(url, port), daemon=True).start()
    create_app().run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    run_local_app()
