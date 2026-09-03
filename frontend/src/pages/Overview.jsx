import { Fragment, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api";

// Local formatters matching legacy app.js's num()/money()/pct() exactly
// (1-decimal hours, 2-decimal currency, em-dash for null percentages) so
// this page reads identically to the legacy Overview it replaced. Kept
// local rather than changed in ../format.js, which other React pages use
// with different (rounded) precision intentionally.
const hrs = (v) => Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const usd = (v) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(v || 0));
const pct = (v) => (v == null ? "—" : `${(Number(v) * 100).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`);

function StatusBadge({ status }) {
  const cls = String(status || "planning").toLowerCase().replaceAll(" ", "-");
  return <span className={`status-badge ${cls}`}>{status || "Planning"}</span>;
}

function StatusControl({ engagementId, status, onChanged }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  if (status !== "active" && status !== "closed") {
    return <p className="hint">Planning remains open until the first Cognos import is committed.</p>;
  }

  const closing = status === "active";
  const nextStatus = closing ? "closed" : "active";
  const label = closing ? "Close engagement" : "Reopen engagement";

  async function submit(event) {
    event.preventDefault();
    if (!reason.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api(`/api/engagements/${engagementId}`, { method: "PUT", body: { status: nextStatus, reason } });
      setOpen(false);
      setReason("");
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className="status-control" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{label}</summary>
      <form onSubmit={submit}>
        <p>
          {closing
            ? "Closing makes every engagement screen read-only."
            : "Reopening allows forecasts, imports and governed revisions again."}
        </p>
        <label className="field">
          <span>Reason</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} required />
        </label>
        {error && <p className="hint danger-text">{error}</p>}
        <button className={closing ? "btn danger" : "btn primary"} disabled={saving}>
          {label}
        </button>
      </form>
    </details>
  );
}

// A CSS Grid row (not a <table>) on purpose: an HTML table cell can never
// shrink below its content's natural width, so nesting the (potentially
// very wide, many-week) expanded detail inside a <td> meant it kept forcing
// the whole summary table wider instead of ever scrolling on its own -
// several attempts at containing that within table markup (table-layout,
// viewport-relative max-width hacks) each broke something else. A grid row
// doesn't have that limitation: max-width:100% + overflow:auto on a plain
// block child behaves exactly as expected, with no special-casing needed.
function PhaseBreakdownRow({ engagementId, phase, expanded, onToggle }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleToggle() {
    const opening = !expanded;
    onToggle();
    if (opening && !detail) {
      setLoading(true);
      setError(null);
      try {
        const data = await api(`/api/engagements/${engagementId}/phases/${phase.id}`);
        setDetail(data.grid);
      } catch (err) {
        setError(err);
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <>
      <div className="phase-breakdown-row">
        <div>
          <button className="phase-expander" onClick={handleToggle} aria-expanded={expanded}>
            {expanded ? "−" : "+"}
          </button>{" "}
          {phase.phase_name}
        </div>
        <div>{hrs(phase.budgeted_hours)}</div>
        <div>
          {hrs(phase.actual_hours)}
          {phase.allocation_confidence_pct != null && phase.allocation_confidence_pct < 1 && (
            <div className="phase-confidence-hint">{pct(phase.allocation_confidence_pct)} directly matched</div>
          )}
        </div>
        <div>{hrs(phase.hours_remaining)}</div>
        <div>{usd(phase.effective_sow)}</div>
        <div>{usd(phase.actual_contract_fees)}</div>
        <div>{pct(phase.realization)}</div>
        <div>
          <StatusBadge status={phase.status} />
        </div>
      </div>
      {expanded && (
        <div className="phase-breakdown-detail">
          {loading && <div className="inline-phase-detail loading">Loading weekly detail...</div>}
          {error && <div className="inline-phase-detail">{error.message}</div>}
          {detail && (
            <div className="inline-phase-detail">
              <p className="weekly-detail-explanation">
                Actual hours are completed time. Budget hours are the approved baseline. Forecast hours are the
                current estimate for work that remains.
              </p>
              <div className="weekly-grid-wrap">
                <table className="weekly-grid weekly-grid-rows">
                  <thead>
                    <tr>
                      <th>Person</th>
                      <th></th>
                      {detail.weeks.map((week) => (
                        <th key={week}>Week of {week}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.rows.map((row) => {
                      const currentPlan = (cell) =>
                        cell.actual_hours || (cell.forecasted_hours == null ? cell.budgeted_hours : cell.forecasted_hours);
                      return (
                        <Fragment key={row.member.id}>
                          <tr className="row-budget">
                            <th rowSpan={2}>{row.member.name}</th>
                            <td className="row-label">Budget</td>
                            {row.cells.map((cell) => (
                              <td key={cell.week_start_date}>{hrs(cell.budgeted_hours)}</td>
                            ))}
                          </tr>
                          <tr className="row-actual">
                            <td className="row-label">Actual / current plan</td>
                            {row.cells.map((cell) => (
                              <td key={cell.week_start_date}>{hrs(currentPlan(cell))}</td>
                            ))}
                          </tr>
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
                <div className="legend">
                  <span className="legend-budget">Budget hours</span>
                  <span className="legend-actual">Actual hours (or current forecast for future weeks)</span>
                </div>
              </div>
              <Link className="btn text" to={`/engagements/${engagementId}/phases/${phase.id}`}>
                Open forecast editor
              </Link>
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function Overview() {
  const { engagementId, engagement: e, metrics: m, phases, reload } = useOutletContext();
  const [expandedId, setExpandedId] = useState(null);

  const progressTone =
    m.status === "Watch" ? "watch" : m.status === "Trending Over" ? "trending-over" : m.status === "Over Budget" ? "over-budget" : "";
  const lowConfidence = m.allocation_resolved_pct != null && m.allocation_resolved_pct < m.confidence_threshold_pct;
  const hasOverageWeeks = m.budget_overage_weeks_count > 0;

  return (
    <>
      <section className="engagement-hero">
        <div>
          <span className="eyebrow">
            {e.engagement_code} · {e.complexity_mode} mode
          </span>
          <h2>{e.engagement_lead || "Lead not assigned"}</h2>
        </div>
        <div className="status-stack">
          <div className="hero-badges">
            <StatusBadge status={e.status} />
            <StatusBadge status={m.status} />
          </div>
          <StatusControl engagementId={engagementId} status={e.status} onChanged={reload} />
        </div>
      </section>

      <div className="metrics-legacy">
        <div className="metric-legacy">
          <span>Budgeted hours</span>
          <strong>{hrs(m.total_budgeted_hours)}</strong>
        </div>
        <div className="metric-legacy">
          <span>Actual hours</span>
          <strong>{hrs(m.hours_to_date)}</strong>
        </div>
        <div className="metric-legacy">
          <span>Remaining hours</span>
          <strong>{hrs(m.hours_remaining)}</strong>
          <small>{pct(m.hours_remaining_pct)} of budget</small>
        </div>
        <div className="metric-legacy">
          <span>Effective statement of work budget</span>
          <strong>{usd(m.effective_sow)}</strong>
        </div>
        <div className="metric-legacy">
          <span>Realization</span>
          <strong>{pct(m.realization)}</strong>
          <small>
            {m.realization_delta == null
              ? "No prior import"
              : `${m.realization_delta >= 0 ? "+" : ""}${pct(m.realization_delta)} since prior import`}
          </small>
        </div>
      </div>

      <div className="card budget-position-legacy">
        <div className="bp-main">
          <div className="bp-head">
            <h2>Budget position</h2>
            <strong>{pct(m.utilization_pct)} used</strong>
          </div>
          <div className={`bp-progress ${progressTone}`}>
            <i style={{ width: `${Math.min(100, (m.utilization_pct || 0) * 100)}%` }} />
          </div>
          <div className="bp-stats">
            <span>
              Projected final <b>{usd(m.projected_final)}</b>
            </span>
            <span>
              Remaining <b>{usd(m.budget_remaining)}</b>
            </span>
            <span>
              Markdown needed <b>{usd(m.markdown_needed)}</b>
            </span>
          </div>
        </div>
        <aside>
          <span>Realization</span>
          <strong>{pct(m.realization)}</strong>
          <small>
            Statement of work budget and change orders minus Crowe-paid expenses, divided by actual standard fees
          </small>
        </aside>
      </div>

      {(m.pending_exceptions_count > 0 || lowConfidence) && (
        <Link className="alert warning" to={`/engagements/${engagementId}/exceptions`}>
          <strong>{m.pending_exceptions_count > 0 ? "Exceptions pending review" : "Unresolved hours are piling up"}</strong>
          <span>
            {m.pending_exceptions_count > 0 &&
              `${m.pending_exceptions_count} imported entries are included in totals and need a decision.`}
            {lowConfidence && ` Only ${pct(m.allocation_resolved_pct)} of hours are matched to a phase; the rest are still awaiting review.`}
          </span>
        </Link>
      )}

      {hasOverageWeeks && (
        <Link className="alert warning" to={`/engagements/${engagementId}/hours-overages`}>
          <strong>Weekly hours overages</strong>
          <span>
            {m.budget_overage_weeks_count} person-week{m.budget_overage_weeks_count === 1 ? "" : "s"} logged more hours than budgeted.
            See who, and which weeks.
          </span>
        </Link>
      )}

      <div className="card">
        <div className="section-head">
          <h2>Phase breakdown</h2>
          <span className="section-hint">Expand a row for weekly detail</span>
        </div>
        <div className="phase-breakdown">
          <div className="phase-breakdown-head">
            <div>Phase</div>
            <div>Budget hours</div>
            <div>Actual hours</div>
            <div>Remaining</div>
            <div>Effective statement of work budget</div>
            <div>Actual fees</div>
            <div>Realization</div>
            <div>Status</div>
          </div>
          {phases.map((phase) => (
            <PhaseBreakdownRow
              key={phase.id}
              engagementId={engagementId}
              phase={phase}
              expanded={expandedId === phase.id}
              onToggle={() => setExpandedId(expandedId === phase.id ? null : phase.id)}
            />
          ))}
        </div>
      </div>
    </>
  );
}
