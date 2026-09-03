import { formatHours, formatMoney } from "../format";

export function ProposalCard({ proposal }) {
  const m = proposal.metrics;
  return (
    <a className="portfolio-card proposal-card" href={`/proposals/${proposal.id}`}>
      <div className="portfolio-card-kicker">
        <span>{proposal.proposal_code}</span>
        <span className="proposal-tag">Proposal</span>
      </div>
      <h3>{proposal.client_name}</h3>
      <p>{proposal.engagement_type || "Planning estimate"}</p>
      <div className="portfolio-card-stats">
        <span>
          <b>{formatHours(m.forecast_hours)}</b> forecast hours
        </span>
        <span>
          <b>{formatMoney(m.estimated_fees)}</b> estimated fees
        </span>
      </div>
      <small>
        {m.people_count} people &middot; starts {proposal.first_monday || "date not set"}
      </small>
    </a>
  );
}
