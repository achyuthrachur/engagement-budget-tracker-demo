import { useState } from "react";
import { Briefcase, Clock, DollarSign, AlertTriangle } from "lucide-react";
import { useDashboard } from "../hooks/useDashboard";
import { MetricCard } from "../components/MetricCard";
import { EngagementCard } from "../components/EngagementCard";
import { ProposalCard } from "../components/ProposalCard";
import { AppShell } from "../components/AppShell";
import { formatHours, formatMoney } from "../format";

const ONBOARDING_KEY = "budget-onboarding-complete";
const WEEKLY_STEPS = [
  "Back up",
  "Export Cognos",
  "Preview",
  "Resolve warnings",
  "Commit actuals",
  "Update forecast",
  "Export report",
];

function WelcomeCard({ onDismiss }) {
  return (
    <section className="welcome-card">
      <div>
        <span className="eyebrow">First-time setup</span>
        <h2>Welcome to the Engagement Budget Tracker</h2>
        <p>
          Start by reviewing the rate card, then build either a proposal or an engagement. The tracker will guide you
          before any actual time is committed.
        </p>
      </div>
      <div className="welcome-actions">
        <a className="btn secondary" href="/settings">
          Review settings
        </a>
        <button className="btn primary" onClick={onDismiss}>
          I understand
        </button>
      </div>
    </section>
  );
}

function WorkflowCard() {
  return (
    <section className="workflow-card">
      <div>
        <span className="eyebrow">Weekly routine</span>
        <h2>Run the budget in seven steps</h2>
      </div>
      <ol className="workflow-steps">
        {WEEKLY_STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <a href="/help#weekly">Open the guided weekly checklist</a>
    </section>
  );
}

export default function Dashboard() {
  const { data, proposals, error, loading } = useDashboard();
  const [onboardingComplete, setOnboardingComplete] = useState(
    () => localStorage.getItem(ONBOARDING_KEY) === "true"
  );

  if (loading && !data) return <AppShell><div className="page-body">Loading portfolio…</div></AppShell>;
  if (error) return <AppShell><div className="page-body">{error.message}</div></AppShell>;
  if (!data) return null;

  const { metrics: m, engagements } = data;

  function completeOnboarding() {
    localStorage.setItem(ONBOARDING_KEY, "true");
    setOnboardingComplete(true);
  }

  return (
    <AppShell>
      <div className="topbar">
        <div className="topbar-inner">
          <div className="topbar-title">
            <span className="topbar-client">Engagement portfolio</span>
            <span className="topbar-meta">Budget, actual, and forecast hours across every active engagement</span>
          </div>
          <div className="button-row">
            <a className="btn secondary" href="/proposals/new">
              New proposal
            </a>
            <a className="btn primary" href="/engagements/new">
              New engagement
            </a>
          </div>
        </div>
      </div>

      <div className="page-body">
        {!onboardingComplete && <WelcomeCard onDismiss={completeOnboarding} />}
        <WorkflowCard />
        <div className="metrics-grid">
          <MetricCard index={0} icon={<Briefcase size={16} />} label="Active engagements" value={m.total_active_engagements} format={(v) => String(Math.round(v))} />
          <MetricCard index={1} icon={<Clock size={16} />} label="Hours this month" value={m.total_hours_mtd} format={formatHours} />
          <MetricCard index={2} icon={<DollarSign size={16} />} label="Fees this month" value={m.total_fees_mtd} format={formatMoney} />
          <MetricCard
            index={3}
            icon={<AlertTriangle size={16} />}
            label="Needs attention"
            value={m.watch_or_over_budget}
            format={(v) => String(Math.round(v))}
            tone={m.watch_or_over_budget > 0 ? "warning" : undefined}
          />
        </div>

        <div className="section-card">
          <div className="section-head">
            <h2>Pre-engagement planning</h2>
            <a className="btn secondary" href="/proposals">
              Open proposals
            </a>
          </div>
          <div className="portfolio-grid">
            {proposals.length ? (
              proposals.slice(0, 3).map((proposal) => <ProposalCard key={proposal.id} proposal={proposal} />)
            ) : (
              <div className="empty">No proposals yet. Start a proposal to estimate staffing and fees before setup.</div>
            )}
          </div>
        </div>

        <div className="section-head" style={{ marginTop: 26 }}>
          <h2>Current engagements</h2>
        </div>
        <div className="portfolio-grid">
          {engagements.length ? (
            engagements.map((engagement) => <EngagementCard key={engagement.id} engagement={engagement} />)
          ) : (
            <div className="empty">No engagements yet. Create the first budget to begin.</div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
