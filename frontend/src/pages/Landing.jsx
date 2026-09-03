import { ArrowRight, FilePlus } from "lucide-react";
import { usePortfolioMetrics } from "../hooks/usePortfolioMetrics";
import { useCountUp } from "../hooks/useCountUp";
import { useAppHealth } from "../hooks/useAppHealth";
import { formatHours, formatMoney } from "../format";
import "../styles/texture.css";

function Stat({ label, value, format, active }) {
  const isNumeric = typeof value === "number";
  const animated = useCountUp(isNumeric ? value : 0, 900, isNumeric && active);
  return (
    <div className="pulse-stat">
      <strong>{isNumeric ? format(animated) : "—"}</strong>
      <span>{label}</span>
    </div>
  );
}

export default function Landing() {
  const { metrics, loading } = usePortfolioMetrics();
  const health = useAppHealth();

  return (
    <div className="landing">
      <div className="texture-dots" aria-hidden="true" />
      <div className="glow-a" aria-hidden="true" />
      <div className="glow-b" aria-hidden="true" />

      <div className="landing-body">
        <div className="landing-hero">
          <div>
            <img className="landing-logo" src="/static/assets/crowe-logo-white.svg" alt="Crowe" />
            <div className="landing-eyebrow">Engagement Budget Tracker</div>
            <h1 className="landing-headline">Know where every hour and dollar stands.</h1>
            <p className="landing-sub">
              Budgeted, actual, and forecast hours for every open engagement — updated as time comes in.
            </p>
            <div className="landing-actions">
              <a className="btn primary landing-cta" href="/dashboard">
                Enter dashboard
                <ArrowRight size={16} strokeWidth={2.5} />
              </a>
              <a className="btn ghost landing-cta" href="/engagements/new">
                <FilePlus size={16} strokeWidth={2.25} />
                New engagement
              </a>
            </div>
          </div>

          <div className="landing-pulse">
            <span className="landing-pulse-label">Portfolio right now</span>
            <div className="landing-pulse-grid">
              <Stat label="Active engagements" value={metrics?.total_active_engagements} format={(v) => String(Math.round(v))} active={!loading} />
              <Stat label="Hours this month" value={metrics?.total_hours_mtd} format={formatHours} active={!loading} />
              <Stat label="Fees this month" value={metrics?.total_fees_mtd} format={formatMoney} active={!loading} />
              <Stat label="Need attention" value={metrics?.watch_or_over_budget} format={(v) => String(Math.round(v))} active={!loading} />
            </div>
          </div>
        </div>
      </div>

      <div className="landing-footer">
        <span>Local build{health ? ` · v${health.app_version}` : ""}</span>
        <a href="/dashboard" style={{ color: "rgba(255,255,255,0.55)", fontSize: 12.5, fontWeight: 600 }}>
          Skip to dashboard
        </a>
      </div>
    </div>
  );
}
