import { useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { useWeeklyBudgetModel } from "../hooks/useWeeklyBudgetModel";
import { WeeklyGrid } from "../components/WeeklyGrid";
import { StatusPill } from "../components/StatusPill";
import { MetricCard } from "../components/MetricCard";
import { formatHours, formatMoney } from "../format";
import { api } from "../api";

function WeeklyCell({ engagementId, member, cell, budgetLocked, closed, canRevise, cellValue, setCell }) {
  const week = cell.week_start_date;
  const budgeted = cellValue(member.id, week, cell, "budgeted_hours");
  const forecasted = cellValue(member.id, week, cell, "forecasted_hours");

  return (
    <>
      <label>
        <span>Budget hours</span>
        <input
          type="number"
          value={budgeted}
          disabled={budgetLocked}
          onChange={(e) => setCell(member.id, week, "budgeted_hours", e.target.value)}
        />
      </label>
      {canRevise && cell.phase_person_week_id && (
        <a
          className="cell-revise"
          href={`/engagements/${engagementId}/revisions?target_type=phase_person_week&target_id=${cell.phase_person_week_id}&field_name=budgeted_hours`}
        >
          Revise
        </a>
      )}
      <label>
        <span>Actual hours</span>
        <output>{formatHours(cell.actual_hours)}</output>
      </label>
      <label>
        <span>Forecast hours</span>
        <input
          type="number"
          value={forecasted ?? ""}
          placeholder="Uses budget hours"
          disabled={closed}
          onChange={(e) => setCell(member.id, week, "forecasted_hours", e.target.value)}
        />
      </label>
    </>
  );
}

function BulkForecastForm({ engagementId, phaseId, rows, weeks, onApplied }) {
  const [memberId, setMemberId] = useState("all");
  const [startWeek, setStartWeek] = useState(weeks[0] || "");
  const [endWeek, setEndWeek] = useState(weeks[weeks.length - 1] || "");
  const [mode, setMode] = useState("flat");
  const [value, setValue] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const team_member_ids = memberId === "all" ? rows.map((row) => row.member.id) : [Number(memberId)];
      const result = await api(`/api/engagements/${engagementId}/forecasts/bulk`, {
        method: "PATCH",
        body: { team_member_ids, phase_ids: [phaseId], start_week: startWeek, end_week: endWeek, mode, value: Number(value) },
      });
      onApplied(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="bulk-forecast" onSubmit={submit}>
        <div>
          <span className="eyebrow">Bulk future-week update</span>
          <h3>Reforecast a range</h3>
        </div>
        <label className="field">
          <span>Person</span>
          <select value={memberId} onChange={(e) => setMemberId(e.target.value)}>
            <option value="all">Whole team</option>
            {rows.map((row) => (
              <option key={row.member.id} value={row.member.id}>
                {row.member.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Start week</span>
          <input type="date" value={startWeek} onChange={(e) => setStartWeek(e.target.value)} required />
        </label>
        <label className="field">
          <span>End week</span>
          <input type="date" value={endWeek} onChange={(e) => setEndWeek(e.target.value)} required />
        </label>
        <label className="field">
          <span>Apply as</span>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="flat">Hours each week</option>
            <option value="spread">Total spread evenly</option>
          </select>
        </label>
        <label className="field">
          <span>Hours</span>
          <input type="number" min="0" step="0.25" value={value} onChange={(e) => setValue(e.target.value)} required />
        </label>
        <button className="btn secondary" disabled={busy}>
          {busy ? "Applying…" : "Apply forecast"}
        </button>
      </form>
      {error && <p className="hint danger-text">{error}</p>}
    </>
  );
}

export default function PhaseDetail() {
  const { phaseId } = useParams();
  const { engagementId, engagement } = useOutletContext();
  const numericPhaseId = Number(phaseId);
  const { data, error, loading, reload, cellValue, setCell, dirty, saving, saveError, save } = useWeeklyBudgetModel(
    engagementId,
    numericPhaseId
  );

  if (loading && !data) return <p className="hint">Loading phase…</p>;
  if (error) return <p className="hint danger-text">{error.message}</p>;
  if (!data) return null;

  const { phase, grid } = data;
  const closed = engagement.status === "closed";
  // Once a phase has any actual hours and the engagement is past planning, budget
  // hours are locked - editing goes through the Revisions audit flow instead
  // (ported from renderPhaseDetail's identical `e.status!=='planning'&&p.actual_hours` gate).
  const budgetLocked = engagement.status !== "planning" && phase.actual_hours > 0;
  const canRevise = engagement.status === "active" && phase.actual_hours > 0;

  return (
    <>
      <div className="section-head">
        <div>
          <span className="eyebrow">{phase.phase_code || "No phase code"}</span>
          <h2>{phase.phase_name}</h2>
        </div>
        <StatusPill status={phase.status} />
      </div>

      <div className="metrics-grid">
        <MetricCard index={0} label="Budget hours" value={phase.budgeted_hours} format={formatHours} />
        <MetricCard index={1} label="Actual hours" value={phase.actual_hours} format={formatHours} />
        <MetricCard index={2} label="Contract fees" value={phase.actual_contract_fees} format={formatMoney} />
        <MetricCard index={3} label="Advance billing tracking" value={phase.actual_dte_fees} format={formatMoney} />
      </div>

      <section className="card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Weekly plan</span>
            <h2>Budget, actual and forecast</h2>
          </div>
          {!closed && (
            <a className="btn secondary" href={`/engagements/${engagementId}/adjustments?phase=${numericPhaseId}`}>
              Add change order
            </a>
          )}
        </div>
        <p className="hint">
          Budget hours are the approved baseline. Actual hours come from Cognos. Forecast hours are your estimate for
          future weeks - a blank forecast uses budget hours, an explicit zero stays zero. Actual hours replace
          forecast hours once time arrives.
        </p>

        {grid.weeks.length === 0 ? (
          <p className="hint">No weekly plan yet - add phase-person weeks to begin tracking.</p>
        ) : (
          <>
            {!closed && (
              <BulkForecastForm
                engagementId={engagementId}
                phaseId={numericPhaseId}
                rows={grid.rows}
                weeks={grid.weeks}
                onApplied={reload}
              />
            )}

            <WeeklyGrid
              weeks={grid.weeks}
              rows={grid.rows}
              rowKey={(row) => row.member.id}
              renderRowHeader={(row) => (
                <>
                  {row.member.name} {row.member.is_offshore && <span className="added-tag">Offshore</span>}
                </>
              )}
              cellClassName={(row, weekIndex) => {
                const cell = row.cells[weekIndex];
                return [
                  cell.variance_flagged ? "variance" : "",
                  cell.budget_variance_flag ? `budget-${cell.budget_variance_flag}` : "",
                ]
                  .filter(Boolean)
                  .join(" ");
              }}
              cellTitle={(row, weekIndex) => {
                const flag = row.cells[weekIndex].budget_variance_flag;
                if (flag === "severe") return "Actual hours exceed budget by more than 10%";
                if (flag === "mild") return "Actual hours exceed budget";
                return undefined;
              }}
              renderCell={(row, weekIndex) => (
                <WeeklyCell
                  engagementId={engagementId}
                  member={row.member}
                  cell={row.cells[weekIndex]}
                  budgetLocked={budgetLocked}
                  closed={closed}
                  canRevise={canRevise}
                  cellValue={cellValue}
                  setCell={setCell}
                />
              )}
            />

            <div className="legend">
              <span>Budget hours: approved baseline</span>
              <span>Actual hours: completed time</span>
              <span>Forecast hours: current estimate</span>
              <span className="variance-key">Week-over-week variance review</span>
              <span className="legend-budget-mild">Budget mild overage</span>
              <span className="legend-budget-severe">Budget severe overage</span>
            </div>

            {!closed && (
              <div className="button-row">
                <button className="btn primary" onClick={save} disabled={!dirty || saving}>
                  {saving ? "Saving…" : "Save weekly grid"}
                </button>
                {saveError && <p className="hint danger-text">{saveError}</p>}
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
