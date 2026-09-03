from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

from db import get_app_settings, row_to_dict


def as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def money(value: Any) -> float:
    return round(as_float(value), 2)


def calculate_status(utilization_pct: float, projected_final: float, net_budget: float) -> str:
    # "Over Budget" is reserved for fees actually spent to date exceeding the budget
    # (utilization_pct>=1.0 is exactly that, since utilization_pct is actual/net_budget) -
    # a fact, not a forecast. A naive linear projection crossing the budget while actual
    # spend is still well under it is a forecast, not a fact yet, so it gets its own
    # "Trending Over" tier rather than being called "Over Budget" too.
    if net_budget <= 0:
        return "Over Budget" if projected_final > 0 else "On Track"
    if utilization_pct >= 1.0:
        return "Over Budget"
    if projected_final > net_budget:
        return "Trending Over"
    if utilization_pct >= 0.80:
        return "Watch"
    return "On Track"


def week_monday(value: str | None) -> str | None:
    if not value:
        return None
    parsed = date.fromisoformat(str(value)[:10])
    return (parsed - timedelta(days=parsed.weekday())).isoformat()


def _one(conn: sqlite3.Connection, sql: str, params=()):
    return conn.execute(sql, params).fetchone()


def _adjustments(conn, engagement_id, phase_id=None):
    sql = "SELECT adjustment_type, COALESCE(SUM(amount), 0) amount FROM budget_adjustments WHERE engagement_id=?"
    params: list[Any] = [engagement_id]
    if phase_id is not None:
        sql += " AND phase_id=?"
        params.append(phase_id)
    sql += " GROUP BY adjustment_type"
    return {row["adjustment_type"]: as_float(row["amount"]) for row in conn.execute(sql, params)}


def phase_weekly_grid(conn: sqlite3.Connection, engagement_id: int, phase_id: int) -> dict[str, Any]:
    members = [row_to_dict(row) or {} for row in conn.execute(
        "SELECT * FROM team_members WHERE engagement_id=? ORDER BY is_offshore, id", (engagement_id,)
    ).fetchall()]
    planned = conn.execute(
        "SELECT * FROM phase_person_weeks WHERE phase_id=? ORDER BY week_start_date, team_member_id",
        (phase_id,),
    ).fetchall()
    actual_rows = conn.execute(
        """SELECT worker_name, week_end_date, SUM(hours) actual_hours,
        SUM(fees_std_rate) std_fees, SUM(fees_contract_rate) contract_fees
        FROM time_entries WHERE engagement_id=? AND matched_phase_id=? AND COALESCE(is_excluded,0)=0
        GROUP BY worker_name, week_end_date""", (engagement_id, phase_id),
    ).fetchall()
    actual: dict[tuple[str, str], dict[str, float]] = {}
    weeks = {row["week_start_date"] for row in planned if row["week_start_date"]}
    for row in actual_rows:
        monday = week_monday(row["week_end_date"])
        if monday:
            weeks.add(monday)
            actual[(str(row["worker_name"] or "").strip().casefold(), monday)] = {
                "hours": as_float(row["actual_hours"]),
                "std_fees": money(row["std_fees"]),
                "contract_fees": money(row["contract_fees"]),
            }
    budgets = {(int(row["team_member_id"]), row["week_start_date"]): row for row in planned}
    budgeted_member_ids = {int(row["team_member_id"]) for row in planned}
    actual_names = {name for name, _monday in actual}
    members = [
        member for member in members
        if int(member["id"]) in budgeted_member_ids
        or str(member["name"] or "").strip().casefold() in actual_names
    ]
    rows = []
    for member in members:
        cells = []
        prior = None
        for monday in sorted(weeks):
            plan = budgets.get((int(member["id"]), monday))
            found = actual.get((str(member["name"] or "").strip().casefold(), monday), {})
            hours = as_float(found.get("hours"))
            delta = hours - prior if prior is not None else 0
            cells.append({
                "week_start_date": monday,
                "phase_person_week_id": plan["id"] if plan else None,
                "budgeted_hours": as_float(plan["budgeted_hours"]) if plan else 0,
                "forecasted_hours": plan["forecasted_hours"] if plan else None,
                "actual_hours": hours,
                "actual_std_fees": money(found.get("std_fees")),
                "actual_contract_fees": money(found.get("contract_fees")),
                "delta_hours": delta,
            })
            prior = hours
        rows.append({"member": member, "cells": cells})
    return {"weeks": sorted(weeks), "rows": rows}


def phase_summary(conn: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    phases = conn.execute(
        "SELECT * FROM phases WHERE engagement_id=? ORDER BY sort_order, id", (engagement_id,)
    ).fetchall()
    result = []
    for phase in phases:
        pid = int(phase["id"])
        budget = _one(conn, """SELECT COALESCE(SUM(ppw.budgeted_hours),0) hours,
            COALESCE(SUM(ppw.budgeted_hours*tm.internal_rate),0) std_fees,
            COALESCE(SUM(ppw.budgeted_hours*tm.engagement_rate),0) eng_fees,
            COALESCE(SUM(ppw.budgeted_hours*tm.contract_rate),0) contract_fees
            FROM phase_person_weeks ppw JOIN team_members tm ON tm.id=ppw.team_member_id
            WHERE ppw.phase_id=?""", (pid,))
        actual = _one(conn, """SELECT COALESCE(SUM(te.hours),0) hours,
            COALESCE(SUM(te.fees_std_rate),0) std_fees,
            COALESCE(SUM(te.fees_contract_rate),0) contract_fees,
            COALESCE(SUM(te.hours*tm.engagement_rate),0) eng_fees
            FROM time_entries te LEFT JOIN team_members tm
              ON tm.id=te.matched_team_member_id OR
                 (te.matched_team_member_id IS NULL AND tm.engagement_id=te.engagement_id
                  AND LOWER(TRIM(tm.name))=LOWER(TRIM(te.worker_name)))
            WHERE te.engagement_id=? AND te.matched_phase_id=? AND COALESCE(te.is_excluded,0)=0""", (engagement_id, pid))
        confidence = _one(conn, """SELECT
            COALESCE(SUM(CASE WHEN allocation_method IN ('direct_match','task_match') THEN hours END),0) confident_hours,
            COALESCE(SUM(CASE WHEN allocation_method IN ('manual_assist','sticky_rule','staffing_match','single_phase_budget') THEN hours END),0) assisted_hours
            FROM time_entries WHERE engagement_id=? AND matched_phase_id=? AND COALESCE(is_excluded,0)=0""",
            (engagement_id, pid))
        expense = _one(conn, """SELECT COALESCE(SUM(amount),0) value FROM expenses
            WHERE engagement_id=? AND phase_id=? AND expense_type='crowe_paid'""", (engagement_id, pid))
        changes = _adjustments(conn, engagement_id, pid).get("change_order", 0)
        effective_sow = as_float(phase["sow_fees"]) + changes
        actual_hours = as_float(actual["hours"])
        grid = phase_weekly_grid(conn, engagement_id, pid)
        forecast_hours = 0.0
        forecast_eng_fees = 0.0
        for grid_row in grid["rows"]:
            rate = as_float(grid_row["member"].get("engagement_rate"))
            for cell in grid_row["cells"]:
                if not cell["actual_hours"]:
                    planned = cell["forecasted_hours"]
                    if planned is None:
                        planned = cell["budgeted_hours"]
                    forecast_hours += as_float(planned)
                    forecast_eng_fees += as_float(planned) * rate
        remaining = as_float(budget["hours"]) - actual_hours
        projected = as_float(actual["contract_fees"])
        if actual_hours:
            projected += (as_float(actual["contract_fees"]) / actual_hours) * max(0, remaining)
        realization = None
        if as_float(actual["std_fees"]):
            realization = (as_float(actual["contract_fees"]) - as_float(expense["value"])) / as_float(actual["std_fees"])
        confident_hours = as_float(confidence["confident_hours"])
        assisted_hours = as_float(confidence["assisted_hours"])
        item = row_to_dict(phase) or {}
        item.update({
            "allocation_confident_hours": confident_hours,
            "allocation_assisted_hours": assisted_hours,
            "allocation_confidence_pct": (confident_hours/(confident_hours+assisted_hours)
                                          if (confident_hours+assisted_hours) > 0 else None),
            "budgeted_hours": as_float(budget["hours"]),
            "budgeted_std_fees": money(budget["std_fees"]),
            "budgeted_eng_fees": money(budget["eng_fees"]),
            "budgeted_contract_fees": money(budget["contract_fees"]),
            "actual_hours": actual_hours, "hours_to_date": actual_hours,
            "actual_std_fees": money(actual["std_fees"]),
            "actual_contract_fees": money(actual["contract_fees"]),
            "actual_eng_fees": money(actual["eng_fees"]),
            "forecast_hours": forecast_hours,
            "current_plan_hours": actual_hours + forecast_hours,
            "current_plan_eng_fees": money(as_float(actual["eng_fees"]) + forecast_eng_fees),
            "change_orders": money(changes), "effective_sow": money(effective_sow),
            "crowe_expenses": money(expense["value"]), "realization": realization,
            "hours_remaining": remaining, "projected_final_fees": money(projected),
            "markdown_required": projected > effective_sow,
            "fees_to_sow_at_eng": money(effective_sow-as_float(actual["eng_fees"])),
            "fees_to_sow_at_contract": money(effective_sow-as_float(actual["contract_fees"])),
            "status": calculate_status(as_float(actual["contract_fees"])/effective_sow if effective_sow else 0,
                                       projected, effective_sow),
        })
        result.append(item)
    return result


# `is_active` on team_members is intentionally NOT filtered here (or in phase_summary /
# engagement_metrics / phase_weekly_grid): historical hours must remain visible in every
# aggregate even after a person is deactivated. is_active only affects (a) UI
# add/deactivate affordances in static/app.js and (b) import-time matching in
# importers.py (flags new hours logged against an inactive person as worker_unauthorized).
# Confirmed as intentional per Rate_Model_and_Frontend_PRD.md §3.4 — do not "fix" this by
# adding an is_active filter to these aggregates without a product decision.
def team_summary(conn: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT tm.*, COALESCE(b.budgeted_hours,0) budgeted_hours,
        COALESCE(a.actual_hours,0) hours_to_date,
        COALESCE(a.actual_contract_fees,0) fees_to_date
        FROM team_members tm
        LEFT JOIN (SELECT team_member_id, SUM(budgeted_hours) budgeted_hours
          FROM phase_person_weeks GROUP BY team_member_id) b ON b.team_member_id=tm.id
        LEFT JOIN (SELECT matched_team_member_id,worker_name, SUM(hours) actual_hours,
          SUM(fees_contract_rate) actual_contract_fees FROM time_entries
          WHERE engagement_id=? AND COALESCE(is_excluded,0)=0
          GROUP BY matched_team_member_id,worker_name) a
          ON a.matched_team_member_id=tm.id OR
             (a.matched_team_member_id IS NULL AND LOWER(TRIM(a.worker_name))=LOWER(TRIM(tm.name)))
        WHERE tm.engagement_id=? ORDER BY tm.is_offshore, tm.id""",
        (engagement_id, engagement_id),
    ).fetchall()
    result = []
    for row in rows:
        item = row_to_dict(row) or {}
        budgeted = as_float(item["budgeted_hours"])
        actual = as_float(item["hours_to_date"])
        remaining = budgeted - actual
        item.update({
            "hours_remaining": remaining,
            "remaining_pct": remaining / budgeted if budgeted else 0,
            "fees_to_date": money(item["fees_to_date"]),
            "budgeted_eng_fees": money(budgeted * as_float(item["engagement_rate"])),
            "actual_eng_fees": money(actual * as_float(item["engagement_rate"])),
            "rate_diff_total": money((as_float(item["engagement_rate"])-as_float(item["internal_rate"]))*actual),
        })
        result.append(item)
    return result


def engagement_metrics(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    engagement = _one(conn, "SELECT * FROM engagements WHERE id=?", (engagement_id,))
    if not engagement:
        return {}
    phases = phase_summary(conn, engagement_id)
    actual = _one(conn, """SELECT COALESCE(SUM(hours),0) hours,
        COALESCE(SUM(fees_std_rate),0) std_fees,
        COALESCE(SUM(fees_contract_rate),0) contract_fees
        FROM time_entries WHERE engagement_id=? AND COALESCE(is_excluded,0)=0""", (engagement_id,))
    budgeted_hours = sum(as_float(p["budgeted_hours"]) for p in phases)
    budgeted_fees = sum(as_float(p["budgeted_eng_fees"]) for p in phases)
    signed_sow = sum(as_float(p["sow_fees"]) for p in phases)
    adjustments = _adjustments(conn, engagement_id)
    adjustment_total = sum(adjustments.values())
    effective_sow = signed_sow + adjustment_total
    crowe_expenses = as_float(_one(conn, """SELECT COALESCE(SUM(amount),0) value FROM expenses
        WHERE engagement_id=? AND expense_type='crowe_paid'""", (engagement_id,))["value"])
    client_expenses = as_float(_one(conn, """SELECT COALESCE(SUM(amount),0) value FROM expenses
        WHERE engagement_id=? AND expense_type='client_paid'""", (engagement_id,))["value"])
    actual_hours = as_float(actual["hours"])
    contract_fees = as_float(actual["contract_fees"])
    remaining = budgeted_hours - actual_hours
    projected = contract_fees
    if actual_hours:
        projected += (contract_fees / actual_hours) * max(0, remaining)
    realization = None
    if as_float(actual["std_fees"]):
        realization = (contract_fees - crowe_expenses) / as_float(actual["std_fees"])
    unmatched = _one(conn, """SELECT COUNT(*) rows, COALESCE(SUM(hours),0) hours,
        COUNT(DISTINCT worker_name) workers FROM time_entries
        WHERE engagement_id=? AND matched_phase_id IS NULL AND COALESCE(is_excluded,0)=0""", (engagement_id,))
    pending = _one(conn, "SELECT COUNT(*) count FROM import_exceptions WHERE engagement_id=? AND status='pending'",
                   (engagement_id,))
    trend = _one(conn, """SELECT realization_value,realization_delta FROM weekly_snapshots
        WHERE engagement_id=? AND realization_value IS NOT NULL ORDER BY imported_at DESC,id DESC LIMIT 1""",
                 (engagement_id,))
    utilization = contract_fees / effective_sow if effective_sow else 0
    confident_hours = sum(as_float(p["allocation_confident_hours"]) for p in phases)
    assisted_hours = sum(as_float(p["allocation_assisted_hours"]) for p in phases)
    unresolved_hours = as_float(unmatched["hours"])
    allocation_denominator = confident_hours + assisted_hours + unresolved_hours
    overage_weeks = budget_overage_weeks(conn, engagement_id)
    return {
        "total_budgeted_hours": budgeted_hours,
        "total_budgeted_fees": money(budgeted_fees),
        "hours_to_date": actual_hours,
        "fees_to_date_contract": money(contract_fees),
        "fees_to_date_std": money(actual["std_fees"]),
        "signed_sow": money(signed_sow),
        "net_budget": money(effective_sow),
        "effective_sow": money(effective_sow),
        "hours_remaining": remaining,
        "hours_remaining_pct": remaining / budgeted_hours if budgeted_hours else 0,
        "projected_remaining": money(max(0, projected-contract_fees)),
        "gross_projected_fees": money(projected),
        "projected_final": money(projected),
        "projected_additions": money(sum(v for v in adjustments.values() if v > 0)),
        "projected_reductions": money(abs(sum(v for v in adjustments.values() if v < 0))),
        "projected_adjustments": money(adjustment_total),
        "markdown_required": projected > effective_sow,
        "markdown_needed": money(max(0, projected-effective_sow)),
        "utilization_pct": utilization,
        "budget_remaining": money(effective_sow-contract_fees),
        "adjustment_total": money(adjustment_total),
        "crowe_expenses": money(crowe_expenses),
        "client_expenses": money(client_expenses),
        "realization": realization,
        "realization_delta": trend["realization_delta"] if trend else None,
        "pending_exceptions_count": int(pending["count"]),
        "unmatched_phase_rows": int(unmatched["rows"]),
        "unmatched_phase_hours": as_float(unmatched["hours"]),
        "unmatched_phase_workers": int(unmatched["workers"]),
        "allocation_confident_hours": confident_hours,
        "allocation_assisted_hours": assisted_hours,
        "allocation_unresolved_hours": unresolved_hours,
        # Deliberately confident+assisted, not confident alone: sticky_rule/staffing_match/
        # single_phase_budget/manual_assist are all deterministic, verified resolutions, not
        # guesses - only hours still sitting unmatched in the exceptions queue should count
        # against this. (Phase-level allocation_confidence_pct in phase_summary() answers a
        # different question - "what fraction was an exact direct/task text match" - and is
        # intentionally left alone.)
        "allocation_resolved_pct": (confident_hours+assisted_hours)/allocation_denominator
                                    if allocation_denominator > 0 else None,
        "confidence_threshold_pct": as_float(get_app_settings(conn)["confidence_threshold_pct"]),
        "budget_overage_weeks_count": len(overage_weeks),
        "status": calculate_status(utilization, projected, effective_sow),
    }


def dashboard(conn: sqlite3.Connection) -> dict[str, Any]:
    active = _one(conn, "SELECT COUNT(*) count FROM engagements WHERE status!='closed'")["count"]
    mtd = _one(conn, """SELECT COALESCE(SUM(hours),0) hours,
        COALESCE(SUM(fees_contract_rate),0) fees FROM time_entries
        WHERE entry_date >= date('now','start of month') AND COALESCE(is_excluded,0)=0""")
    rows = conn.execute("""SELECT e.*,
        (SELECT MAX(week_end_date) FROM weekly_snapshots s WHERE s.engagement_id=e.id) last_import_date
        FROM engagements e ORDER BY updated_at DESC, id DESC""").fetchall()
    cards = []
    risk = 0
    for row in rows:
        item = row_to_dict(row) or {}
        item["metrics"] = engagement_metrics(conn, int(item["id"]))
        if item["metrics"]["status"] in {"Watch", "Trending Over", "Over Budget"}:
            risk += 1
        cards.append(item)
    return {"metrics": {
        "total_active_engagements": int(active),
        "total_hours_mtd": as_float(mtd["hours"]),
        "total_fees_mtd": money(mtd["fees"]),
        "watch_or_over_budget": risk,
    }, "engagements": cards}


def variance_flag(actual: float, prior: float | None, settings: dict[str, Any]) -> bool:
    if prior is None:
        return False
    delta = abs(actual-prior)
    relative = delta/prior if prior > 0 else 0
    return delta > as_float(settings["variance_threshold_hours"]) or (
        prior > 0 and relative > as_float(settings["variance_threshold_pct"])
    )


def budget_variance_flag(budgeted_hours: float, actual_hours: float) -> str | None:
    budgeted = as_float(budgeted_hours)
    if budgeted <= 0:
        return None
    overage_pct = round(as_float(actual_hours) / budgeted - 1, 6)
    if overage_pct > 0.10:
        return "severe"
    if overage_pct > 0:
        return "mild"
    return None


def budget_overage_weeks(conn: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    """Every person-week, across every phase, where actual hours exceeded that
    week's budgeted hours - the drill-down behind the weekly-hours-overage alert
    (deliberately not called "over budget": that term is reserved for the
    engagement/phase actually exceeding its total fee budget, calculate_status())."""
    phase_rows = conn.execute(
        "SELECT id, phase_name FROM phases WHERE engagement_id=? ORDER BY sort_order, id", (engagement_id,)
    ).fetchall()
    overages = []
    for phase in phase_rows:
        pid = int(phase["id"])
        grid = apply_grid_variance(conn, phase_weekly_grid(conn, engagement_id, pid))
        for row in grid["rows"]:
            member = row["member"]
            for cell in row["cells"]:
                if not cell.get("budget_variance_flag"):
                    continue
                budgeted = as_float(cell["budgeted_hours"])
                actual = as_float(cell["actual_hours"])
                overages.append({
                    "phase_id": pid,
                    "phase_name": phase["phase_name"],
                    "team_member_id": int(member["id"]),
                    "team_member_name": member["name"],
                    "week_start_date": cell["week_start_date"],
                    "budgeted_hours": budgeted,
                    "actual_hours": actual,
                    "overage_hours": money(actual-budgeted),
                    "overage_pct": round(actual/budgeted-1, 4) if budgeted else None,
                    "severity": cell["budget_variance_flag"],
                })
    overages.sort(key=lambda o: (o["week_start_date"] or "", o["severity"] != "severe", o["team_member_name"] or ""))
    return overages


def apply_grid_variance(conn: sqlite3.Connection, grid: dict[str, Any]) -> dict[str, Any]:
    settings = get_app_settings(conn)
    for row in grid["rows"]:
        prior = None
        for cell in row["cells"]:
            cell["variance_flagged"] = variance_flag(cell["actual_hours"], prior, settings)
            cell["budget_variance_flag"] = budget_variance_flag(cell["budgeted_hours"], cell["actual_hours"])
            prior = cell["actual_hours"]
    return grid
