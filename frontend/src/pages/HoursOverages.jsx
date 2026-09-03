import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api";

// 1-decimal hours (not format.js's 0-decimal formatHours): a 0.5hr overage
// would otherwise round away to nothing and look like no overage at all.
const hrs = (v) => Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pct = (v) => (v == null ? "—" : `${(Number(v) * 100).toLocaleString("en-US", { maximumFractionDigits: 0 })}%`);

export default function HoursOverages() {
  const { engagementId } = useOutletContext();
  const [overages, setOverages] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api(`/api/engagements/${engagementId}/hours-overages`).then(setOverages).catch((err) => setError(err.message));
  }, [engagementId]);

  if (error) return <p className="hint danger-text">{error}</p>;
  if (!overages) return <p className="hint">Loading weekly hours overages…</p>;

  return (
    <section className="card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Actual hours exceeded that week's budget</span>
          <h2>Weekly hours overages</h2>
        </div>
        <span className="section-hint">{overages.length} person-weeks</span>
      </div>
      <p className="hint">
        Who logged more hours than budgeted, and in which week - a staffing/pacing signal, separate from whether the
        engagement or phase has exceeded its total fee budget.
      </p>
      <div className="table-wrap">
        <table className="exceptions-table">
          <thead>
            <tr>
              <th>Week</th>
              <th>Worker</th>
              <th>Phase</th>
              <th>Budgeted hours</th>
              <th>Actual hours</th>
              <th>Overage</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody>
            {overages.length === 0 && (
              <tr>
                <td colSpan={7}>No person-week has exceeded its budgeted hours</td>
              </tr>
            )}
            {overages.map((o) => (
              <tr key={`${o.phase_id}-${o.team_member_id}-${o.week_start_date}`} className={o.severity}>
                <td>Week of {o.week_start_date}</td>
                <td>{o.team_member_name}</td>
                <td>{o.phase_name}</td>
                <td>{hrs(o.budgeted_hours)}</td>
                <td>{hrs(o.actual_hours)}</td>
                <td>
                  +{hrs(o.overage_hours)} ({pct(o.overage_pct)})
                </td>
                <td>{o.severity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
