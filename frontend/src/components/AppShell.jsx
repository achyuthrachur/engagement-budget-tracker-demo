import { FilePlus, HelpCircle, LayoutDashboard, Moon, Settings, Sun } from "lucide-react";
import { useTheme } from "../hooks/useTheme";
import { useAppHealth } from "../hooks/useAppHealth";

const NAV = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "New engagement", href: "/engagements/new", icon: FilePlus },
  { label: "Settings", href: "/settings", icon: Settings },
  { label: "Help", href: "/help", icon: HelpCircle },
];

function isActive(href) {
  const path = window.location.pathname;
  return href === "/dashboard" ? path === href : path.startsWith(href);
}

// Persistent sidebar + theme toggle, replacing legacy app.js's shell().
// Every page not exempted for editorial reasons (Landing's full-bleed hero)
// renders inside this so cross-page nav and dark mode work everywhere.
export function AppShell({ children }) {
  const { theme, toggleTheme } = useTheme();
  const health = useAppHealth();

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <a className="app-brand" href="/dashboard">
          <img src="/static/assets/crowe-logo-white.svg" alt="Crowe" />
          <span className="app-brand-label">Engagement Budget Tracker</span>
        </a>
        <nav className="app-nav">
          {NAV.map(({ label, href, icon: Icon }) => (
            <a key={href} href={href} className={isActive(href) ? "active" : ""}>
              <Icon size={16} strokeWidth={2} />
              <span className="app-nav-label">{label}</span>
            </a>
          ))}
        </nav>
        <div className="app-sidebar-foot">
          <span className="app-version-label">
            {health ? `v${health.app_version} · Database format ${health.schema_version}` : " "}
          </span>
          <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label="Toggle color theme">
            {theme === "light" ? <Moon size={14} /> : <Sun size={14} />}
            <span className="app-nav-label">{theme === "light" ? "Dark mode" : "Light mode"}</span>
          </button>
        </div>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
