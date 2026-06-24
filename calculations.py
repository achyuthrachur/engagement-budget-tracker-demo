from __future__ import annotations

import sqlite3
from typing import Any

from db import row_to_dict, rows_to_dicts


def as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def money(value: Any) -> float:
    return round(as_float(value), 2)


REDUCTION_ADJUSTMENT_TYPES = {"bima", "markdown"}
ADDITION_ADJUSTMENT_TYPES = {"change_order", "c360"}


def calculate_status(utilization_pct: float, projected_final: float, net_budget: float) -> str:
    if net_budget <= 0:
        return "Over Budget" if projected_final > 0 else "On Track"
    if utilization_pct >= 0.95 or projected_final > net_budget:
        return "Over Budget"
    if utilization_pct >= 0.80:
        return "Watch"
    return "On Track"


def engagement_metrics(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    engagement = conn.execute(
        "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
    ).fetchone()
    if engagement is None:
        return {}

    totals = conn.execute(
        """
        SELECT
          COALESCE(SUM(hours), 0) AS hours_to_date,
          COALESCE(SUM(fees_contract_rate), 0) AS fees_to_date_contract,
          COALESCE(SUM(fees_std_rate), 0) AS fees_to_date_std
        FROM time_entries
        WHERE engagement_id = ?
        """,
        (engagement_id,),
    ).fetchone()
    budget = conn.execute(
        """
        SELECT
          COALESCE(SUM(budgeted_hours), 0) AS total_hours,
          COALESCE(SUM(budgeted_hours * engagement_rate), 0) AS total_fees
        FROM team_members
        WHERE engagement_id = ?
        """,
        (engagement_id,),
    ).fetchone()
    adjustment_rows = conn.execute(
        """
        SELECT adjustment_type, amount
        FROM budget_adjustments
        WHERE engagement_id = ?
        """,
        (engagement_id,),
    ).fetchall()
    adjustment_total = 0.0
    projected_additions = 0.0
    projected_reductions = 0.0
    for adjustment in adjustment_rows:
        amount = as_float(adjustment["amount"])
        adjustment_type = str(adjustment["adjustment_type"] or "").lower()
        adjustment_total += amount
        if adjustment_type in REDUCTION_ADJUSTMENT_TYPES:
            projected_reductions += abs(amount)
        elif adjustment_type in ADDITION_ADJUSTMENT_TYPES:
            projected_additions += amount
        else:
            projected_additions += amount

    hours_to_date = as_float(totals["hours_to_date"])
    fees_contract = as_float(totals["fees_to_date_contract"])
    fees_std = as_float(totals["fees_to_date_std"])
    budgeted_hours = as_float(budget["total_hours"])
    total_budgeted_fees = as_float(budget["total_fees"])
    max_sow_fees = as_float(engagement["max_sow_fees"])
    change_order_amt = as_float(engagement["change_order_amt"])
    c360_amount = as_float(engagement["c360_amount"])
    bima_amount = abs(as_float(engagement["bima_amount"]))
    projected_additions += change_order_amt + c360_amount
    projected_reductions += bima_amount
    net_budget = max_sow_fees + change_order_amt + c360_amount
    hours_remaining = budgeted_hours - hours_to_date

    if total_budgeted_fees > 0:
        projected_fees = max(fees_contract, total_budgeted_fees)
    else:
        projected_remaining_before_adjustments = 0.0
        if hours_to_date:
            projected_remaining_before_adjustments = (fees_contract / hours_to_date) * hours_remaining
        projected_fees = fees_contract + projected_remaining_before_adjustments

    projected_adjustments = projected_additions - projected_reductions
    projected_final = max(fees_contract, projected_fees + projected_adjustments)
    projected_remaining = max(0.0, projected_final - fees_contract)

    utilization_pct = fees_contract / net_budget if net_budget else 0.0
    status = calculate_status(utilization_pct, projected_final, net_budget)
    markdown_needed = max(0.0, projected_final - net_budget)

    return {
        "total_budgeted_hours": budgeted_hours,
        "total_budgeted_fees": money(total_budgeted_fees),
        "hours_to_date": hours_to_date,
        "fees_to_date_contract": money(fees_contract),
        "fees_to_date_std": money(fees_std),
        "net_budget": money(net_budget),
        "hours_remaining": hours_remaining,
        "hours_remaining_pct": (hours_remaining / budgeted_hours) if budgeted_hours else 0,
        "projected_remaining": money(projected_remaining),
        "gross_projected_fees": money(projected_fees),
        "projected_additions": money(projected_additions),
        "projected_reductions": money(projected_reductions),
        "projected_adjustments": money(projected_adjustments),
        "projected_final": money(projected_final),
        "markdown_required": projected_final > net_budget,
        "markdown_needed": money(markdown_needed),
        "utilization_pct": utilization_pct,
        "budget_remaining": money(net_budget - fees_contract),
        "adjustment_total": money(adjustment_total),
        "status": status,
    }


def team_summary(conn: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tm.*,
          COALESCE(SUM(te.hours), 0) AS hours_to_date,
          COALESCE(SUM(te.fees_contract_rate), 0) AS fees_to_date
        FROM team_members tm
        LEFT JOIN time_entries te
          ON te.engagement_id = tm.engagement_id
         AND te.worker_name = tm.name
        WHERE tm.engagement_id = ?
        GROUP BY tm.id
        ORDER BY tm.id
        """,
        (engagement_id,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row) or {}
        budgeted_hours = as_float(item["budgeted_hours"])
        hours_to_date = as_float(item["hours_to_date"])
        hours_remaining = budgeted_hours - hours_to_date
        item["hours_remaining"] = hours_remaining
        item["remaining_pct"] = hours_remaining / budgeted_hours if budgeted_hours else 0
        item["fees_to_date"] = money(item["fees_to_date"])
        item["rate_diff_total"] = money(
            (as_float(item["engagement_rate"]) - as_float(item["internal_rate"])) * hours_to_date
        )
        result.append(item)
    return result


def phase_summary(conn: sqlite3.Connection, engagement_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.*,
          COALESCE(SUM(te.hours), 0) AS hours_to_date,
          COALESCE(SUM(te.fees_contract_rate), 0) AS fees_to_date
        FROM phases p
        LEFT JOIN time_entries te
          ON te.engagement_id = p.engagement_id
         AND te.phase_desc = p.phase_name
        WHERE p.engagement_id = ?
        GROUP BY p.id
        ORDER BY p.sort_order, p.id
        """,
        (engagement_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def dashboard(conn: sqlite3.Connection) -> dict[str, Any]:
    active_count = conn.execute(
        "SELECT COUNT(*) AS count FROM engagements WHERE status != 'Closed'"
    ).fetchone()["count"]
    mtd = conn.execute(
        """
        SELECT
          COALESCE(SUM(hours), 0) AS hours,
          COALESCE(SUM(fees_contract_rate), 0) AS fees
        FROM time_entries
        WHERE entry_date >= date('now', 'start of month')
        """
    ).fetchone()

    rows = conn.execute(
        """
        SELECT e.*,
          (SELECT MAX(week_end_date) FROM weekly_snapshots ws WHERE ws.engagement_id = e.id)
            AS last_import_date
        FROM engagements e
        ORDER BY updated_at DESC, created_at DESC, id DESC
        """
    ).fetchall()
    cards = []
    risk_count = 0
    for row in rows:
        item = row_to_dict(row) or {}
        metrics = engagement_metrics(conn, int(item["id"]))
        item["metrics"] = metrics
        item["last_import_date"] = row["last_import_date"]
        if item.get("status") != "Closed" and metrics.get("status") in {"Watch", "Over Budget"}:
            risk_count += 1
        cards.append(item)

    return {
        "metrics": {
            "total_active_engagements": active_count,
            "total_hours_mtd": as_float(mtd["hours"]),
            "total_fees_mtd": money(mtd["fees"]),
            "watch_or_over_budget": risk_count,
        },
        "engagements": cards,
    }
