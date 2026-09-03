import { Link, useLocation } from "react-router-dom";

const TABS = [
  ["Overview", ""],
  ["Phases", "phases"],
  ["Exceptions", "exceptions"],
  ["Team", "team"],
  ["Rate model", "rates"],
  ["Weekly import", "import"],
  ["Adjustments", "adjustments"],
  ["Expenses", "expenses"],
  ["History", "history"],
  ["Export", "export"],
];

// Routes in REACT_OWNED are React-owned (see App.jsx's nested /engagements/:id
// layout route) - those use a client-side <Link> so switching between them is
// a real SPA transition, not a full reload. Every other tab is still served
// by the legacy vanilla-JS app, so it deliberately stays a plain
// full-navigation <a>. Extend the set as more sub-pages port.
const REACT_OWNED = new Set(["", "import", "exceptions", "phases"]);

export function EngagementTabs({ engagementId, mode }) {
  const location = useLocation();
  const tabs = mode === "complex" ? [...TABS.slice(0, 7), ["Revisions", "revisions"], ...TABS.slice(7)] : TABS;
  return (
    <nav className="tabs">
      {tabs.map(([label, route]) => {
        const href = `/engagements/${engagementId}${route ? `/${route}` : ""}`;
        if (REACT_OWNED.has(route)) {
          return (
            <Link key={route} to={href} className={location.pathname === href ? "active" : ""}>
              {label}
            </Link>
          );
        }
        return (
          <a key={route} href={href}>
            {label}
          </a>
        );
      })}
    </nav>
  );
}
