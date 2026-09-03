import { StatusPill } from "./StatusPill";
import { formatHours, formatMoney } from "../format";

export function EngagementCard({ engagement }) {
  const m = engagement.metrics;
  const statusSlug = String(m.status || "").toLowerCase().replaceAll(" ", "-");
  const pct = Math.min(100, Math.max(0, (m.utilization_pct || 0) * 100));
  return (
    <a className={`portfolio-card status-${statusSlug}`} href={`/engagements/${engagement.id}`}>
      <div className="portfolio-card-kicker">
        <span>{engagement.engagement_code}</span>
        <StatusPill status={m.status} small />
      </div>
      <h3>{engagement.client_name}</h3>
      <p>{engagement.engagement_lead || "Lead not assigned"}</p>
      <div className="portfolio-progress">
        <i style={{ width: `${pct}%` }} />
      </div>
      <div className="portfolio-card-stats">
        <span>
          <b>{formatHours(m.hours_to_date)}</b> hours
        </span>
        <span>
          <b>{formatMoney(m.fees_to_date_contract)}</b> used
        </span>
      </div>
      <small>
        {engagement.complexity_mode} mode &middot; Last import {engagement.last_import_date || "none"}
      </small>
    </a>
  );
}
