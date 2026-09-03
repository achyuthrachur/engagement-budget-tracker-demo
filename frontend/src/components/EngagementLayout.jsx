import { Outlet, useParams } from "react-router-dom";
import { useEngagementOverview } from "../hooks/useEngagementOverview";
import { AppShell } from "./AppShell";
import { EngagementTabs } from "./EngagementTabs";

// Shared topbar/tabs shell for every React-owned engagement sub-page
// (Overview, Weekly import, ...). Fetches once here via the existing
// useEngagementOverview hook and hands engagement/metrics/phases/reload
// down through the route Outlet context instead of each page re-fetching.
//
// Header mirrors legacy shell()'s plain "eyebrow + title" bar exactly
// (client name/code/lead and status live in Overview's own engagement-hero
// instead, matching where legacy places them).
export function EngagementLayout() {
  const { id } = useParams();
  const engagementId = Number(id);
  const { data, error, loading, reload } = useEngagementOverview(engagementId);

  if (loading && !data) return <AppShell><div className="page-body">Loading engagement…</div></AppShell>;
  if (error) return <AppShell><div className="page-body">{error.message}</div></AppShell>;
  if (!data) return null;

  const { engagement, metrics, phases } = data;

  return (
    <AppShell>
      <header className="engagement-topbar">
        <div className="engagement-topbar-inner">
          <span className="eyebrow">Budget governance</span>
          <h1>{engagement.client_name}</h1>
        </div>
      </header>

      <div className="page-body">
        <EngagementTabs engagementId={engagementId} mode={engagement.complexity_mode} />
        <Outlet context={{ engagementId, engagement, metrics, phases, reload }} />
      </div>
    </AppShell>
  );
}
