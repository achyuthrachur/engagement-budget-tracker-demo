from __future__ import annotations

import html
import io
import sqlite3
from datetime import date
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill

from calculations import as_float, engagement_metrics, phase_summary, team_summary
from db import row_to_dict, rows_to_dicts

CURRENCY_FORMAT = '$#,##0.00'
HOURS_FORMAT = '#,##0.00'
PERCENT_FORMAT = '0%'
DATE_FORMAT = 'yyyy-mm-dd'
NAVY = '1B2A4A'
ACCENT = 'D4A853'
PAGE_BG = 'F4F5F7'
GREEN = '22863A'
AMBER = 'B45309'
RED = 'B91C1C'


def filename_safe(value: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in value).strip('_')


def budget_run_date() -> str:
    return date.today().isoformat()


def export_filename(engagement: dict[str, Any]) -> str:
    client = filename_safe(str(engagement.get('client_name') or 'Client'))
    code = filename_safe(str(engagement.get('engagement_code') or 'Engagement'))
    return f'{client}_{code}_{budget_run_date()}.xlsx'


def format_currency(value: Any) -> str:
    return f'${as_float(value):,.2f}'


def format_hours(value: Any) -> str:
    return f'{as_float(value):,.2f}'


def format_percent(value: Any) -> str:
    return f'{as_float(value) * 100:,.0f}%'


def engagement_payload(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    engagement = row_to_dict(
        conn.execute('SELECT * FROM engagements WHERE id = ?', (engagement_id,)).fetchone()
    )
    if engagement is None:
        raise ValueError('Engagement not found')
    adjustments = rows_to_dicts(
        conn.execute(
            """
            SELECT * FROM budget_adjustments
            WHERE engagement_id = ?
            ORDER BY effective_date DESC, id DESC
            """,
            (engagement_id,),
        ).fetchall()
    )
    entries = rows_to_dicts(
        conn.execute(
            """
            SELECT * FROM time_entries
            WHERE engagement_id = ?
            ORDER BY week_end_date DESC, entry_date DESC, id DESC
            """,
            (engagement_id,),
        ).fetchall()
    )
    return {
        'engagement': engagement,
        'metrics': engagement_metrics(conn, engagement_id),
        'team': team_summary(conn, engagement_id),
        'phases': phase_summary(conn, engagement_id),
        'adjustments': adjustments,
        'entries': entries,
    }


def build_excel(conn: sqlite3.Connection, engagement_id: int) -> tuple[str, bytes]:
    payload = engagement_payload(conn, engagement_id)
    engagement = payload['engagement']
    metrics = payload['metrics']
    workbook = Workbook()
    summary = workbook.active
    summary.title = 'Engagement Summary'
    header_fill = PatternFill('solid', fgColor=NAVY)
    header_font = Font(color='FFFFFF', bold=True)
    subheader_fill = PatternFill('solid', fgColor=PAGE_BG)

    def write_header(sheet, row: int, values: list[str]) -> None:
        for col, value in enumerate(values, 1):
            cell = sheet.cell(row=row, column=col, value=value)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='left')

    def style_subheader(sheet, row: int, cols: int) -> None:
        for col in range(1, cols + 1):
            cell = sheet.cell(row=row, column=col)
            cell.fill = subheader_fill
            cell.font = Font(bold=True, color=NAVY)

    summary.append(['Client', engagement['client_name']])
    summary.append(['Engagement Code', engagement['engagement_code']])
    summary.append(['Lead', engagement.get('engagement_lead')])
    summary.append(['Model Type', engagement.get('model_type')])
    summary.append(['Budget Run Date', budget_run_date()])
    summary.append([])
    write_header(summary, 7, ['Metric', 'Value'])
    metric_rows = [
        ('Total Budgeted Hours', metrics.get('total_budgeted_hours'), HOURS_FORMAT),
        ('Hours To Date', metrics.get('hours_to_date'), HOURS_FORMAT),
        ('Hours Remaining', metrics.get('hours_remaining'), HOURS_FORMAT),
        ('Total Budgeted Fees', metrics.get('total_budgeted_fees'), CURRENCY_FORMAT),
        ('Fees To Date', metrics.get('fees_to_date_contract'), CURRENCY_FORMAT),
        ('Net Budget', metrics.get('net_budget'), CURRENCY_FORMAT),
        ('Budget Remaining', metrics.get('budget_remaining'), CURRENCY_FORMAT),
        ('Projected Final', metrics.get('projected_final'), CURRENCY_FORMAT),
        ('Markdown Needed', metrics.get('markdown_needed'), CURRENCY_FORMAT),
        ('Utilization %', metrics.get('utilization_pct'), PERCENT_FORMAT),
        ('Status', metrics.get('status'), None),
    ]
    for label, value, number_format in metric_rows:
        summary.append([label, value])
        if number_format:
            summary.cell(row=summary.max_row, column=2).number_format = number_format

    summary.append([])
    chart_start = summary.max_row + 1
    write_header(summary, chart_start, ['Budget Visual', 'Amount'])
    visual_rows = [
        ('Net Budget', metrics.get('net_budget')),
        ('Fees To Date', metrics.get('fees_to_date_contract')),
        ('Projected Final', metrics.get('projected_final')),
        ('Markdown Needed', metrics.get('markdown_needed')),
    ]
    for label, value in visual_rows:
        summary.append([label, value])
        summary.cell(row=summary.max_row, column=2).number_format = CURRENCY_FORMAT

    bar = BarChart()
    bar.title = 'Budget vs Actuals'
    bar.y_axis.title = 'Amount'
    bar.x_axis.title = 'Metric'
    bar.add_data(Reference(summary, min_col=2, min_row=chart_start, max_row=chart_start + len(visual_rows)), titles_from_data=True)
    bar.set_categories(Reference(summary, min_col=1, min_row=chart_start + 1, max_row=chart_start + len(visual_rows)))
    bar.height = 7
    bar.width = 13
    summary.add_chart(bar, 'D7')

    summary.append([])
    team_header = summary.max_row + 1
    write_header(
        summary,
        team_header,
        [
            'Name',
            'Role',
            'Budgeted Hours',
            'Hours To Date',
            'Remaining',
            'Engagement Rate',
            'Budgeted Fees',
            'Fees To Date',
        ],
    )
    for member in payload['team']:
        budgeted_fees = as_float(member.get('budgeted_hours')) * as_float(member.get('engagement_rate'))
        summary.append(
            [
                member.get('name'),
                member.get('role'),
                member.get('budgeted_hours'),
                member.get('hours_to_date'),
                member.get('hours_remaining'),
                member.get('engagement_rate'),
                budgeted_fees,
                member.get('fees_to_date'),
            ]
        )
        row = summary.max_row
        for col in (3, 4, 5):
            summary.cell(row=row, column=col).number_format = HOURS_FORMAT
        for col in (6, 7, 8):
            summary.cell(row=row, column=col).number_format = CURRENCY_FORMAT

    if payload['team']:
        pie = PieChart()
        pie.title = 'Budgeted Fees by Team Member'
        pie.add_data(
            Reference(summary, min_col=7, min_row=team_header, max_row=team_header + len(payload['team'])),
            titles_from_data=True,
        )
        pie.set_categories(
            Reference(summary, min_col=1, min_row=team_header + 1, max_row=team_header + len(payload['team']))
        )
        pie.height = 7
        pie.width = 9
        summary.add_chart(pie, 'D22')

    weekly = workbook.create_sheet('Weekly Detail')
    write_header(
        weekly,
        1,
        [
            'Transaction ID',
            'Worker ID',
            'Worker',
            'Title',
            'Date',
            'Week End Date',
            'Financial Period',
            'Phase Desc',
            'Task Desc',
            'Work Loc',
            'Billing Status',
            'Hours',
            'Fees @ Std Rate',
            'Fees @ Contract Rate',
            'Memo',
        ],
    )
    for entry in payload['entries']:
        weekly.append(
            [
                entry.get('transaction_id'),
                entry.get('worker_id'),
                entry.get('worker_name'),
                entry.get('title'),
                entry.get('entry_date'),
                entry.get('week_end_date'),
                entry.get('financial_period'),
                entry.get('phase_desc'),
                entry.get('task_desc'),
                entry.get('work_location'),
                entry.get('billing_status'),
                entry.get('hours'),
                entry.get('fees_std_rate'),
                entry.get('fees_contract_rate'),
                entry.get('memo'),
            ]
        )
        row = weekly.max_row
        weekly.cell(row=row, column=12).number_format = HOURS_FORMAT
        weekly.cell(row=row, column=13).number_format = CURRENCY_FORMAT
        weekly.cell(row=row, column=14).number_format = CURRENCY_FORMAT

    adjustments = workbook.create_sheet('Adjustment Log')
    write_header(adjustments, 1, ['Date', 'Type', 'Amount', 'Description'])
    for adjustment in payload['adjustments']:
        adjustments.append(
            [
                adjustment.get('effective_date'),
                adjustment.get('adjustment_type'),
                adjustment.get('amount'),
                adjustment.get('description'),
            ]
        )
        adjustments.cell(row=adjustments.max_row, column=3).number_format = CURRENCY_FORMAT

    for sheet in workbook.worksheets:
        sheet.freeze_panes = 'A2'
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical='top')
        for column_cells in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in column_cells)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 12), 48)
    style_subheader(summary, 1, 2)

    output = io.BytesIO()
    workbook.save(output)
    return export_filename(engagement), output.getvalue()


def build_html_report(conn: sqlite3.Connection, engagement_id: int, narrative: str = '') -> str:
    payload = engagement_payload(conn, engagement_id)
    engagement = payload['engagement']
    metrics = payload['metrics']

    def esc(value: Any) -> str:
        return html.escape('' if value is None else str(value))

    def table(headers: list[str], rows: list[list[Any]]) -> str:
        head = ''.join(f'<th>{esc(header)}</th>' for header in headers)
        body = ''.join(
            '<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in row) + '</tr>' for row in rows
        )
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    def bar(label: str, value: Any, max_value: Any, css_class: str = '') -> str:
        maximum = max(as_float(max_value), 1)
        pct = min(max(as_float(value) / maximum, 0), 1) * 100
        return (
            f'<div class="bar-row"><div class="bar-label">{esc(label)}</div>'
            f'<div class="bar-track"><span class="{css_class}" style="width:{pct:.1f}%"></span></div>'
            f'<div class="bar-value">{format_currency(value)}</div></div>'
        )

    max_budget_value = max(
        as_float(metrics.get('net_budget')),
        as_float(metrics.get('projected_final')),
        as_float(metrics.get('fees_to_date_contract')),
        1,
    )
    budget_visual = ''.join(
        [
            bar('Net Budget', metrics.get('net_budget'), max_budget_value, 'navy'),
            bar('Fees To Date', metrics.get('fees_to_date_contract'), max_budget_value, 'green'),
            bar('Projected Final', metrics.get('projected_final'), max_budget_value, 'amber'),
            bar('Markdown Needed', metrics.get('markdown_needed'), max_budget_value, 'red'),
        ]
    )

    team_max = max(
        [as_float(member.get('budgeted_hours')) * as_float(member.get('engagement_rate')) for member in payload['team']] + [1]
    )
    team_visual = ''.join(
        bar(
            member.get('name'),
            as_float(member.get('budgeted_hours')) * as_float(member.get('engagement_rate')),
            team_max,
            'navy',
        )
        for member in payload['team']
    ) or '<div class="muted">No team budget configured.</div>'

    summary_table = table(
        ['Metric', 'Value'],
        [
            ['Total Budgeted Hours', format_hours(metrics['total_budgeted_hours'])],
            ['Hours To Date', format_hours(metrics['hours_to_date'])],
            ['Hours Remaining', format_hours(metrics['hours_remaining'])],
            ['Total Budgeted Fees', format_currency(metrics.get('total_budgeted_fees'))],
            ['Fees To Date', format_currency(metrics['fees_to_date_contract'])],
            ['Net Budget', format_currency(metrics['net_budget'])],
            ['Budget Remaining', format_currency(metrics['budget_remaining'])],
            ['Projected Final', format_currency(metrics['projected_final'])],
            ['Markdown Needed', format_currency(metrics['markdown_needed'])],
            ['Utilization %', format_percent(metrics['utilization_pct'])],
            ['Status', metrics['status']],
        ],
    )
    team_table = table(
        ['Name', 'Role', 'Budgeted Hours', 'Hours To Date', 'Remaining', 'Engagement Rate', 'Fees'],
        [
            [
                member.get('name'),
                member.get('role'),
                format_hours(member.get('budgeted_hours')),
                format_hours(member.get('hours_to_date')),
                format_hours(member.get('hours_remaining')),
                format_currency(member.get('engagement_rate')),
                format_currency(member.get('fees_to_date')),
            ]
            for member in payload['team']
        ],
    )
    phase_table = table(
        ['Phase', 'Budgeted Hours', 'Hours To Date', 'Fees To Date'],
        [
            [
                phase.get('phase_name'),
                format_hours(phase.get('budgeted_hours')),
                format_hours(phase.get('hours_to_date')),
                format_currency(phase.get('fees_to_date')),
            ]
            for phase in payload['phases']
        ],
    )
    adjustment_table = table(
        ['Date', 'Type', 'Amount', 'Description'],
        [
            [
                adjustment.get('effective_date'),
                adjustment.get('adjustment_type'),
                format_currency(adjustment.get('amount')),
                adjustment.get('description'),
            ]
            for adjustment in payload['adjustments']
        ],
    )

    return f'''<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{esc(engagement['client_name'])} Budget Report</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; color: #1B2A4A; margin: 32px; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; }}
    h2 {{ margin-top: 32px; font-size: 18px; page-break-before: always; }}
    h2:first-of-type {{ page-break-before: auto; }}
    .meta {{ color: #4b5563; margin-bottom: 24px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 18px 0 22px; }}
    .metric {{ border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; padding: 12px; }}
    .metric-label {{ color: #697386; font-size: 11px; }}
    .metric-value {{ font-size: 19px; font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th {{ background: #F4F5F7; text-align: left; }}
    th, td {{ border-bottom: 1px solid rgba(0,0,0,0.12); padding: 8px 10px; font-size: 12px; }}
    .visual {{ border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; padding: 14px; margin-top: 12px; }}
    .bar-row {{ display: grid; grid-template-columns: 150px 1fr 110px; gap: 10px; align-items: center; margin: 9px 0; font-size: 12px; }}
    .bar-track {{ height: 12px; background: #E6E8EC; border-radius: 999px; overflow: hidden; }}
    .bar-track span {{ display: block; height: 100%; background: #1B2A4A; }}
    .bar-track span.green {{ background: #22863A; }}
    .bar-track span.amber {{ background: #B45309; }}
    .bar-track span.red {{ background: #B91C1C; }}
    .bar-value {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .muted {{ color: #697386; }}
    .narrative {{ white-space: pre-wrap; line-height: 1.5; }}
    @media print {{ body {{ margin: 0.45in; }} section {{ page-break-inside: avoid; }} .metric-grid {{ break-inside: avoid; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{esc(engagement['client_name'])} Budget Report</h1>
    <div class="meta">
      Code: {esc(engagement['engagement_code'])} | Lead: {esc(engagement.get('engagement_lead'))}
      | Model: {esc(engagement.get('model_type'))} | Budget Run Date: {budget_run_date()}
    </div>
    <div class="metric-grid">
      <div class="metric"><div class="metric-label">Net Budget</div><div class="metric-value">{format_currency(metrics['net_budget'])}</div></div>
      <div class="metric"><div class="metric-label">Fees To Date</div><div class="metric-value">{format_currency(metrics['fees_to_date_contract'])}</div></div>
      <div class="metric"><div class="metric-label">Projected Final</div><div class="metric-value">{format_currency(metrics['projected_final'])}</div></div>
      <div class="metric"><div class="metric-label">Markdown Needed</div><div class="metric-value">{format_currency(metrics['markdown_needed'])}</div></div>
    </div>
  </header>
  <section><h2>Budget vs. Actuals</h2>{summary_table}<div class="visual">{budget_visual}</div></section>
  <section><h2>Team Budget Visualization</h2><div class="visual">{team_visual}</div></section>
  <section><h2>Team Summary</h2>{team_table}</section>
  <section><h2>Phase Summary</h2>{phase_table}</section>
  <section><h2>Adjustment Log</h2>{adjustment_table}</section>
  <section><h2>Status Narrative</h2><div class="narrative">{esc(narrative)}</div></section>
  <script>window.addEventListener('load', () => setTimeout(() => window.print(), 250));</script>
</body>
</html>'''
