from __future__ import annotations

import os
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file

from calculations import as_float, dashboard, engagement_metrics, phase_summary, team_summary
from db import connect, db_path, get_rates, init_db, load_seed_database, now_iso, row_to_dict, rows_to_dicts, set_rates
from exports import build_excel, build_html_report
from importers import parse_text_export, parse_xlsx_export, preview_rows, validate_columns


IMPORT_PREVIEWS: dict[int, list[dict[str, Any]]] = {}

ENGAGEMENT_FIELDS = [
    "engagement_code",
    "client_name",
    "model_type",
    "model_vendor",
    "engagement_lead",
    "first_week_with_entry",
    "max_sow_fees",
    "change_order_amt",
    "c360_used",
    "c360_amount",
    "bima_amount",
    "status",
]

TEAM_FIELDS = ["name", "role", "internal_rate", "engagement_rate", "budgeted_hours"]
PHASE_FIELDS = ["phase_name", "budgeted_hours", "budgeted_eng_fees", "sort_order"]
ADJUSTMENT_TYPES = {"markdown", "c360", "bima", "change_order"}


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["DATABASE_PATH"] = database_path or str(db_path())
    app.config["DB_ERROR"] = None
    try:
        init_db(Path(app.config["DATABASE_PATH"]))
    except Exception as exc:  # pragma: no cover - exercised manually on corrupt DB.
        app.config["DB_ERROR"] = str(exc)

    def conn() -> sqlite3.Connection:
        return connect(Path(app.config["DATABASE_PATH"]))

    @app.errorhandler(Exception)
    def handle_uncaught(exc: Exception):
        if isinstance(exc, sqlite3.IntegrityError):
            return fail("A record with this unique value already exists", 409, "conflict")
        return fail("Unexpected server error", 500, "server_error")

    @app.get("/")
    @app.get("/dashboard")
    @app.get("/engagements/new")
    @app.get("/engagements/<path:_path>")
    @app.get("/settings")
    def index(_path: str | None = None):
        return render_template("index.html", db_error=app.config["DB_ERROR"])

    @app.get("/api/health")
    def health():
        return ok({"status": "ok", "db_path": app.config["DATABASE_PATH"]})

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
    def check_engagement_code():
        code = request.args.get("code", "").strip()
        exclude_id = request.args.get("exclude_id", type=int)
        if not code:
            return ok({"available": False})
        sql = "SELECT id FROM engagements WHERE engagement_code = ?"
        params: list[Any] = [code]
        if exclude_id:
            sql += " AND id != ?"
            params.append(exclude_id)
        with conn() as db:
            row = db.execute(sql, params).fetchone()
        return ok({"available": row is None})

    @app.post("/api/engagements")
    def create_engagement():
        payload = request.get_json(silent=True) or {}
        engagement_data = payload.get("engagement") or payload
        missing = required(engagement_data, ["engagement_code", "client_name", "max_sow_fees"])
        if missing:
            return fail("Missing required field", 400, "validation_error", missing)

        try:
            with conn() as db:
                now = now_iso()
                values = clean_engagement(engagement_data, now, now)
                cursor = db.execute(
                    """
                    INSERT INTO engagements (
                      engagement_code, client_name, model_type, model_vendor, engagement_lead,
                      first_week_with_entry, max_sow_fees, change_order_amt, c360_used,
                      c360_amount, bima_amount, status, created_at, updated_at
                    ) VALUES (
                      :engagement_code, :client_name, :model_type, :model_vendor, :engagement_lead,
                      :first_week_with_entry, :max_sow_fees, :change_order_amt, :c360_used,
                      :c360_amount, :bima_amount, :status, :created_at, :updated_at
                    )
                    """,
                    values,
                )
                engagement_id = int(cursor.lastrowid)
                for member in payload.get("team", []):
                    insert_team_member(db, engagement_id, member)
                for order, phase in enumerate(payload.get("phases", [])):
                    insert_phase(db, engagement_id, phase, order)
                data = full_engagement(db, engagement_id)
            return ok(data, 201)
        except sqlite3.IntegrityError:
            return fail("Engagement code already exists", 409, "duplicate_engagement_code")

    @app.get("/api/engagements/<int:engagement_id>")
    def get_engagement(engagement_id: int):
        with conn() as db:
            data = full_engagement(db, engagement_id)
            if data is None:
                return fail("Not found", 404, "not_found")
            return ok(data)

    @app.put("/api/engagements/<int:engagement_id>")
    def update_engagement(engagement_id: int):
        payload = request.get_json(silent=True) or {}
        updates = {key: payload[key] for key in ENGAGEMENT_FIELDS if key in payload}
        if not updates:
            return fail("No fields to update", 400, "validation_error")
        updates["updated_at"] = now_iso()
        normalize_engagement_updates(updates)
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        updates["id"] = engagement_id
        try:
            with conn() as db:
                cursor = db.execute(f"UPDATE engagements SET {assignments} WHERE id = :id", updates)
                if cursor.rowcount == 0:
                    return fail("Not found", 404, "not_found")
                return ok(full_engagement(db, engagement_id))
        except sqlite3.IntegrityError:
            return fail("Engagement code already exists", 409, "duplicate_engagement_code")

    @app.delete("/api/engagements/<int:engagement_id>")
    def delete_engagement(engagement_id: int):
        with conn() as db:
            cursor = db.execute("DELETE FROM engagements WHERE id = ?", (engagement_id,))
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
        IMPORT_PREVIEWS.pop(engagement_id, None)
        return ok({"deleted": True})

    @app.get("/api/engagements/<int:engagement_id>/team")
    def get_team(engagement_id: int):
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            return ok(team_summary(db, engagement_id))

    @app.post("/api/engagements/<int:engagement_id>/team")
    def create_team_member(engagement_id: int):
        payload = request.get_json(silent=True) or {}
        members = payload.get("members") if isinstance(payload.get("members"), list) else [payload]
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            for member in members:
                if not str(member.get("name", "")).strip():
                    return fail("Missing required field", 400, "validation_error", ["name"])
                insert_team_member(db, engagement_id, member)
            touch_engagement(db, engagement_id)
            return ok(team_summary(db, engagement_id), 201)

    @app.put("/api/engagements/<int:engagement_id>/team/<int:member_id>")
    def update_team_member(engagement_id: int, member_id: int):
        payload = request.get_json(silent=True) or {}
        updates = {key: payload[key] for key in TEAM_FIELDS if key in payload}
        if not updates:
            return fail("No fields to update", 400, "validation_error")
        normalize_team_updates(updates)
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        updates.update({"id": member_id, "engagement_id": engagement_id})
        with conn() as db:
            cursor = db.execute(
                f"UPDATE team_members SET {assignments} WHERE id = :id AND engagement_id = :engagement_id",
                updates,
            )
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            touch_engagement(db, engagement_id)
            return ok(team_summary(db, engagement_id))

    @app.delete("/api/engagements/<int:engagement_id>/team/<int:member_id>")
    def delete_team_member(engagement_id: int, member_id: int):
        with conn() as db:
            cursor = db.execute(
                "DELETE FROM team_members WHERE id = ? AND engagement_id = ?",
                (member_id, engagement_id),
            )
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            touch_engagement(db, engagement_id)
            return ok({"deleted": True})

    @app.get("/api/engagements/<int:engagement_id>/phases")
    def get_phases(engagement_id: int):
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            return ok(phase_summary(db, engagement_id))

    @app.post("/api/engagements/<int:engagement_id>/phases")
    def create_phase(engagement_id: int):
        payload = request.get_json(silent=True) or {}
        phases = payload.get("phases") if isinstance(payload.get("phases"), list) else [payload]
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            current_max = db.execute(
                "SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM phases WHERE engagement_id = ?",
                (engagement_id,),
            ).fetchone()["max_sort"]
            for offset, phase in enumerate(phases, 1):
                if not str(phase.get("phase_name", "")).strip():
                    return fail("Missing required field", 400, "validation_error", ["phase_name"])
                insert_phase(db, engagement_id, phase, int(current_max) + offset)
            touch_engagement(db, engagement_id)
            return ok(phase_summary(db, engagement_id), 201)

    @app.put("/api/engagements/<int:engagement_id>/phases/<int:phase_id>")
    def update_phase(engagement_id: int, phase_id: int):
        payload = request.get_json(silent=True) or {}
        updates = {key: payload[key] for key in PHASE_FIELDS if key in payload}
        if not updates:
            return fail("No fields to update", 400, "validation_error")
        normalize_phase_updates(updates)
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        updates.update({"id": phase_id, "engagement_id": engagement_id})
        with conn() as db:
            cursor = db.execute(
                f"UPDATE phases SET {assignments} WHERE id = :id AND engagement_id = :engagement_id",
                updates,
            )
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            touch_engagement(db, engagement_id)
            return ok(phase_summary(db, engagement_id))

    @app.delete("/api/engagements/<int:engagement_id>/phases/<int:phase_id>")
    def delete_phase(engagement_id: int, phase_id: int):
        with conn() as db:
            cursor = db.execute(
                "DELETE FROM phases WHERE id = ? AND engagement_id = ?",
                (phase_id, engagement_id),
            )
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            touch_engagement(db, engagement_id)
            return ok({"deleted": True})

    @app.patch("/api/engagements/<int:engagement_id>/phases/reorder")
    def reorder_phases(engagement_id: int):
        payload = request.get_json(silent=True) or []
        if not isinstance(payload, list):
            return fail("Expected a list of phases", 400, "validation_error")
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            for item in payload:
                db.execute(
                    "UPDATE phases SET sort_order = ? WHERE id = ? AND engagement_id = ?",
                    (int(item.get("sort_order", 0)), int(item.get("id", 0)), engagement_id),
                )
            touch_engagement(db, engagement_id)
            return ok(phase_summary(db, engagement_id))

    @app.get("/api/engagements/<int:engagement_id>/adjustments")
    def get_adjustments(engagement_id: int):
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            return ok(list_adjustments(db, engagement_id))

    @app.post("/api/engagements/<int:engagement_id>/adjustments")
    def create_adjustment(engagement_id: int):
        payload = request.get_json(silent=True) or {}
        error = validate_adjustment(payload)
        if error:
            return error
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            db.execute(
                """
                INSERT INTO budget_adjustments (
                  engagement_id, effective_date, adjustment_type, amount, description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    engagement_id,
                    payload.get("effective_date"),
                    payload.get("adjustment_type"),
                    as_float(payload.get("amount")),
                    payload.get("description", ""),
                    now_iso(),
                ),
            )
            touch_engagement(db, engagement_id)
            return ok(list_adjustments(db, engagement_id), 201)

    @app.put("/api/engagements/<int:engagement_id>/adjustments/<int:adj_id>")
    def update_adjustment(engagement_id: int, adj_id: int):
        payload = request.get_json(silent=True) or {}
        error = validate_adjustment(payload, partial=True)
        if error:
            return error
        updates = {
            key: payload[key]
            for key in ["effective_date", "adjustment_type", "amount", "description"]
            if key in payload
        }
        if "amount" in updates:
            updates["amount"] = as_float(updates["amount"])
        if not updates:
            return fail("No fields to update", 400, "validation_error")
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        updates.update({"id": adj_id, "engagement_id": engagement_id})
        with conn() as db:
            cursor = db.execute(
                f"""
                UPDATE budget_adjustments SET {assignments}
                WHERE id = :id AND engagement_id = :engagement_id
                """,
                updates,
            )
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            touch_engagement(db, engagement_id)
            return ok(list_adjustments(db, engagement_id))

    @app.delete("/api/engagements/<int:engagement_id>/adjustments/<int:adj_id>")
    def delete_adjustment(engagement_id: int, adj_id: int):
        with conn() as db:
            cursor = db.execute(
                "DELETE FROM budget_adjustments WHERE id = ? AND engagement_id = ?",
                (adj_id, engagement_id),
            )
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            touch_engagement(db, engagement_id)
            return ok({"deleted": True})

    @app.post("/api/engagements/<int:engagement_id>/import/preview")
    def import_preview(engagement_id: int):
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            try:
                parsed = read_import_payload()
            except ValueError as exc:
                return fail(str(exc), 400, "validation_error")
            missing = validate_columns(parsed)
            if missing:
                return fail("Import is missing expected columns", 400, "validation_error", missing)
            preview = preview_rows(db, engagement_id, parsed)
            IMPORT_PREVIEWS[engagement_id] = preview["rows"]
            return ok(preview)

    @app.post("/api/engagements/<int:engagement_id>/import/commit")
    def import_commit(engagement_id: int):
        payload = request.get_json(silent=True) or {}
        rows = IMPORT_PREVIEWS.get(engagement_id)
        if rows is None:
            return fail("No import preview available", 400, "missing_preview")
        included_ids = set(payload.get("included_transaction_ids") or [])
        excluded_ids = set(payload.get("excluded_transaction_ids") or [])
        explicit_inclusions = "included_transaction_ids" in payload
        selected = []
        preview_duplicates = 0
        for row in rows:
            transaction_id = row["transaction_id"]
            if row.get("flag") == "duplicate":
                preview_duplicates += 1
            include = transaction_id in included_ids if explicit_inclusions else bool(row.get("included"))
            if transaction_id in excluded_ids or row.get("flag") == "duplicate":
                include = False
            if include:
                selected.append(row)
        if not selected:
            IMPORT_PREVIEWS.pop(engagement_id, None)
            return ok(
                {
                    "snapshot_id": None,
                    "imported": 0,
                    "skipped": len(rows),
                    "duplicates": preview_duplicates,
                    "row_count": 0,
                }
            )

        week_end_dates = [row["week_end_date"] for row in selected if row.get("week_end_date")]
        week_end_date = max(week_end_dates) if week_end_dates else now_iso()[:10]
        imported = 0
        commit_duplicates = 0
        snapshot_id = None
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            existing_ids = {
                item["transaction_id"]
                for item in db.execute(
                    "SELECT transaction_id FROM time_entries WHERE transaction_id IS NOT NULL"
                ).fetchall()
            }
            cursor = db.execute(
                """
                INSERT INTO weekly_snapshots (engagement_id, week_end_date, imported_at, row_count, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (engagement_id, week_end_date, now_iso(), 0, payload.get("notes", "")),
            )
            snapshot_id = int(cursor.lastrowid)
            for row in selected:
                if row["transaction_id"] in existing_ids:
                    commit_duplicates += 1
                    continue
                try:
                    db.execute(
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
                            row["transaction_id"],
                            row["worker_name"],
                            row["worker_id"],
                            row["title"],
                            row["entry_date"],
                            row["week_end_date"],
                            row["financial_period"],
                            row["phase_desc"],
                            row["task_desc"],
                            row["work_location"],
                            row["billing_status"],
                            row["hours"],
                            row["fees_std_rate"],
                            row["fees_contract_rate"],
                            row["memo"],
                        ),
                    )
                    existing_ids.add(row["transaction_id"])
                    imported += 1
                except sqlite3.IntegrityError:
                    commit_duplicates += 1
            if imported:
                db.execute(
                    "UPDATE weekly_snapshots SET row_count = ? WHERE id = ?",
                    (imported, snapshot_id),
                )
                touch_engagement(db, engagement_id)
            else:
                db.execute("DELETE FROM weekly_snapshots WHERE id = ?", (snapshot_id,))
                snapshot_id = None
        IMPORT_PREVIEWS.pop(engagement_id, None)
        duplicates = preview_duplicates + commit_duplicates
        return ok(
            {
                "snapshot_id": snapshot_id,
                "imported": imported,
                "skipped": len(rows) - imported,
                "duplicates": duplicates,
                "row_count": imported,
            },
            201,
        )

    @app.get("/api/engagements/<int:engagement_id>/snapshots")
    def get_snapshots(engagement_id: int):
        with conn() as db:
            if not engagement_exists(db, engagement_id):
                return fail("Not found", 404, "not_found")
            return ok(snapshot_history(db, engagement_id))

    @app.get("/api/engagements/<int:engagement_id>/snapshots/<int:snapshot_id>")
    def get_snapshot(engagement_id: int, snapshot_id: int):
        with conn() as db:
            snapshot = row_to_dict(
                db.execute(
                    "SELECT * FROM weekly_snapshots WHERE id = ? AND engagement_id = ?",
                    (snapshot_id, engagement_id),
                ).fetchone()
            )
            if snapshot is None:
                return fail("Not found", 404, "not_found")
            entries = rows_to_dicts(
                db.execute(
                    """
                    SELECT * FROM time_entries
                    WHERE snapshot_id = ? AND engagement_id = ?
                    ORDER BY worker_name, entry_date, id
                    """,
                    (snapshot_id, engagement_id),
                ).fetchall()
            )
            snapshot["entries"] = entries
            return ok(snapshot)

    @app.delete("/api/engagements/<int:engagement_id>/snapshots/<int:snapshot_id>")
    def delete_snapshot(engagement_id: int, snapshot_id: int):
        with conn() as db:
            cursor = db.execute(
                "DELETE FROM weekly_snapshots WHERE id = ? AND engagement_id = ?",
                (snapshot_id, engagement_id),
            )
            if cursor.rowcount == 0:
                return fail("Not found", 404, "not_found")
            touch_engagement(db, engagement_id)
            return ok({"deleted": True, "metrics": engagement_metrics(db, engagement_id)})

    @app.get("/api/engagements/<int:engagement_id>/export/excel")
    def export_excel(engagement_id: int):
        with conn() as db:
            try:
                filename, content = build_excel(db, engagement_id)
            except ValueError:
                return fail("Not found", 404, "not_found")
        return send_file(
            __import__("io").BytesIO(content),
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/api/engagements/<int:engagement_id>/export/html")
    def export_html(engagement_id: int):
        narrative = request.args.get("narrative", "")
        with conn() as db:
            try:
                html = build_html_report(db, engagement_id, narrative)
            except ValueError:
                return fail("Not found", 404, "not_found")
        return Response(html, mimetype="text/html")

    @app.get("/api/settings/rates")
    def rates():
        with conn() as db:
            path = Path(app.config["DATABASE_PATH"])
            stat = path.stat() if path.exists() else None
            return ok(
                {
                    "rates": get_rates(db),
                    "database": {
                        "path": str(path),
                        "last_modified": now_from_timestamp(stat.st_mtime) if stat else None,
                    },
                }
            )

    @app.put("/api/settings/rates")
    def update_rates():
        payload = request.get_json(silent=True) or {}
        rates_payload = payload.get("rates", payload)
        if not isinstance(rates_payload, dict):
            return fail("Rates must be an object", 400, "validation_error")
        with conn() as db:
            return ok({"rates": set_rates(db, rates_payload)})

    @app.get("/api/settings/backup")
    def download_backup():
        path = Path(app.config["DATABASE_PATH"])
        if not path.exists():
            return fail("Database not found", 404, "not_found")
        return send_file(
            path,
            as_attachment=True,
            download_name=f"budget_tracker_backup_{now_iso()[:10]}.db",
            mimetype="application/octet-stream",
        )

    return app


def ok(data: Any, status: int = 200):
    return jsonify({"data": data, "error": None}), status


def fail(message: str, status: int, code: str, fields: list[str] | None = None):
    error: dict[str, Any] = {"message": message, "code": code}
    if fields:
        error["fields"] = fields
    return jsonify({"data": None, "error": error}), status


def required(payload: dict[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if payload.get(field) in (None, "")]


def clean_engagement(payload: dict[str, Any], created_at: str, updated_at: str) -> dict[str, Any]:
    values = {field: payload.get(field) for field in ENGAGEMENT_FIELDS}
    normalize_engagement_updates(values)
    values["status"] = values.get("status") or "Active"
    values["created_at"] = created_at
    values["updated_at"] = updated_at
    return values


def normalize_engagement_updates(values: dict[str, Any]) -> None:
    for key in ["max_sow_fees", "change_order_amt", "c360_amount", "bima_amount"]:
        if key in values:
            values[key] = as_float(values.get(key))
    if "c360_used" in values:
        values["c360_used"] = 1 if str(values.get("c360_used")).lower() in {"1", "true", "yes", "on"} else 0
    for key in ["engagement_code", "client_name", "model_type", "model_vendor", "engagement_lead", "status"]:
        if key in values and values.get(key) is not None:
            values[key] = str(values[key]).strip()


def normalize_team_updates(values: dict[str, Any]) -> None:
    for key in ["internal_rate", "engagement_rate", "budgeted_hours"]:
        if key in values:
            values[key] = as_float(values.get(key))
    for key in ["name", "role"]:
        if key in values and values.get(key) is not None:
            values[key] = str(values[key]).strip()


def normalize_phase_updates(values: dict[str, Any]) -> None:
    for key in ["budgeted_hours", "budgeted_eng_fees"]:
        if key in values:
            values[key] = as_float(values.get(key))
    if "sort_order" in values:
        values["sort_order"] = int(as_float(values.get("sort_order")))
    if "phase_name" in values and values.get("phase_name") is not None:
        values["phase_name"] = str(values["phase_name"]).strip()


def insert_team_member(db: sqlite3.Connection, engagement_id: int, member: dict[str, Any]) -> None:
    values = {field: member.get(field) for field in TEAM_FIELDS}
    normalize_team_updates(values)
    if not values.get("engagement_rate"):
        values["engagement_rate"] = values.get("internal_rate", 0)
    db.execute(
        """
        INSERT INTO team_members (engagement_id, name, role, internal_rate, engagement_rate, budgeted_hours)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            engagement_id,
            values.get("name", ""),
            values.get("role", ""),
            values.get("internal_rate", 0),
            values.get("engagement_rate", 0),
            values.get("budgeted_hours", 0),
        ),
    )


def insert_phase(db: sqlite3.Connection, engagement_id: int, phase: dict[str, Any], order: int) -> None:
    values = {field: phase.get(field) for field in PHASE_FIELDS}
    if values.get("sort_order") in (None, ""):
        values["sort_order"] = order
    normalize_phase_updates(values)
    db.execute(
        """
        INSERT INTO phases (engagement_id, phase_name, budgeted_hours, budgeted_eng_fees, sort_order)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            engagement_id,
            values.get("phase_name", ""),
            values.get("budgeted_hours", 0),
            values.get("budgeted_eng_fees", 0),
            values.get("sort_order", order),
        ),
    )


def engagement_exists(db: sqlite3.Connection, engagement_id: int) -> bool:
    return (
        db.execute("SELECT 1 FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
        is not None
    )


def touch_engagement(db: sqlite3.Connection, engagement_id: int) -> None:
    db.execute("UPDATE engagements SET updated_at = ? WHERE id = ?", (now_iso(), engagement_id))


def full_engagement(db: sqlite3.Connection, engagement_id: int) -> dict[str, Any] | None:
    engagement = row_to_dict(
        db.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
    )
    if engagement is None:
        return None
    recent_imports = rows_to_dicts(
        db.execute(
            """
            SELECT ws.*,
              COALESCE(SUM(te.hours), 0) AS hours,
              COALESCE(SUM(te.fees_contract_rate), 0) AS fees
            FROM weekly_snapshots ws
            LEFT JOIN time_entries te ON te.snapshot_id = ws.id
            WHERE ws.engagement_id = ?
            GROUP BY ws.id
            ORDER BY ws.week_end_date DESC, ws.imported_at DESC
            LIMIT 3
            """,
            (engagement_id,),
        ).fetchall()
    )
    return {
        "engagement": engagement,
        "metrics": engagement_metrics(db, engagement_id),
        "team": team_summary(db, engagement_id),
        "phases": phase_summary(db, engagement_id),
        "adjustments": list_adjustments(db, engagement_id),
        "recent_imports": recent_imports,
        "weekly_summary": weekly_summary(db, engagement_id),
    }


def list_adjustments(db: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        db.execute(
            """
            SELECT * FROM budget_adjustments
            WHERE engagement_id = ?
            ORDER BY effective_date DESC, id DESC
            """,
            (engagement_id,),
        ).fetchall()
    )


def validate_adjustment(payload: dict[str, Any], partial: bool = False):
    if not partial:
        missing = required(payload, ["adjustment_type", "effective_date", "amount"])
        if missing:
            return fail("Missing required field", 400, "validation_error", missing)
    adjustment_type = payload.get("adjustment_type")
    if adjustment_type is not None and adjustment_type not in ADJUSTMENT_TYPES:
        return fail("Invalid adjustment type", 400, "validation_error", ["adjustment_type"])
    if adjustment_type == "bima" and not str(payload.get("description", "")).strip():
        return fail("BIMA adjustments require a description", 400, "validation_error", ["description"])
    return None


def read_import_payload() -> list[dict[str, Any]]:
    if "file" in request.files and request.files["file"].filename:
        upload = request.files["file"]
        filename = upload.filename.lower()
        content = upload.read()
        if filename.endswith(".xlsx"):
            return parse_xlsx_export(content)
        return parse_text_export(content.decode("utf-8-sig"))
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    if not text:
        raise ValueError("No import text or file provided")
    return parse_text_export(text)


def weekly_summary(db: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    rows = rows_to_dicts(
        db.execute(
            """
            SELECT
              COALESCE(NULLIF(week_end_date, ''), entry_date) AS week_end_date,
              COALESCE(SUM(hours), 0) AS hours,
              COALESCE(SUM(fees_contract_rate), 0) AS fees,
              COUNT(*) AS entries
            FROM time_entries
            WHERE engagement_id = ?
            GROUP BY COALESCE(NULLIF(week_end_date, ''), entry_date)
            ORDER BY COALESCE(NULLIF(week_end_date, ''), entry_date) ASC
            """,
            (engagement_id,),
        ).fetchall()
    )
    cumulative_hours = 0.0
    cumulative_fees = 0.0
    for row in rows:
        cumulative_hours += as_float(row.get("hours"))
        cumulative_fees += as_float(row.get("fees"))
        row["hours"] = as_float(row.get("hours"))
        row["fees"] = round(as_float(row.get("fees")), 2)
        row["cumulative_hours"] = cumulative_hours
        row["cumulative_fees"] = round(cumulative_fees, 2)
    return rows

def snapshot_history(db: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    rows = rows_to_dicts(
        db.execute(
            """
            SELECT ws.*,
              COALESCE(SUM(te.hours), 0) AS hours,
              COALESCE(SUM(te.fees_contract_rate), 0) AS fees
            FROM weekly_snapshots ws
            LEFT JOIN time_entries te ON te.snapshot_id = ws.id
            WHERE ws.engagement_id = ?
            GROUP BY ws.id
            ORDER BY ws.week_end_date ASC, ws.id ASC
            """,
            (engagement_id,),
        ).fetchall()
    )
    cumulative_hours = 0.0
    cumulative_fees = 0.0
    for row in rows:
        cumulative_hours += as_float(row.get("hours"))
        cumulative_fees += as_float(row.get("fees"))
        row["cumulative_hours"] = cumulative_hours
        row["cumulative_fees"] = round(cumulative_fees, 2)
    return list(reversed(rows))


def now_from_timestamp(timestamp: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(timestamp).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    port = int(os.environ.get("BUDGET_TRACKER_PORT", "5000"))
    create_app().run(host="127.0.0.1", port=port, debug=False)




