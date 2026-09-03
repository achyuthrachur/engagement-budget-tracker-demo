import { BREAKPOINTS, FONT_DISPLAY, FONT_TEXT, THEME, TOKENS, themeVarsBlock } from "../tokens";

export function GlobalStyle() {
  return (
    <style>{`
      :root { ${themeVarsBlock(THEME.light)} }
      :root[data-theme="dark"] { ${themeVarsBlock(THEME.dark)} }

      * { box-sizing: border-box; }
      html, body, #root { margin: 0; min-height: 100%; }
      html { -webkit-font-smoothing: antialiased; }
      body { font-family: ${FONT_TEXT}; font-size: 17px; line-height: 1.45; background: var(--page-bg); color: var(--foreground); }
      button { font-family: inherit; cursor: pointer; }
      a { text-decoration: none; }
      img { max-width: 100%; }

      @keyframes staggerIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .stagger-in { opacity: 0; animation: staggerIn 0.5s cubic-bezier(0.16,1,0.3,1) forwards; }

      @keyframes fillIn { to { transform: scaleX(1); } }

      @keyframes revealIn {
        from { opacity: 0; transform: translateY(14px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .reveal-in { animation: revealIn 0.65s cubic-bezier(0.16,1,0.3,1) forwards; }
      .delay-1 { animation-delay: 0.08s; }
      .delay-2 { animation-delay: 0.16s; }
      .delay-3 { animation-delay: 0.24s; }

      /* ---- app shell (sidebar + main) ---- */
      .app-shell { display: flex; min-height: 100vh; background: var(--page-bg); }
      .app-sidebar {
        width: 248px; flex-shrink: 0; background: var(--navy); display: flex; flex-direction: column;
        position: sticky; top: 0; height: 100vh; overflow-y: auto; padding-top: 20px;
      }
      .app-brand { display: flex; align-items: center; gap: 12px; padding: 0 20px 18px; border-bottom: 1px solid rgba(255,255,255,0.1); }
      .app-brand img { height: 26px; width: auto; flex-shrink: 0; }
      .app-brand-label { color: #fff; font-size: 16px; font-weight: 700; line-height: 1.25; min-width: 0; }
      .app-nav { display: flex; flex-direction: column; padding: 14px 0; flex: 1; }
      .app-nav a {
        display: flex; align-items: center; gap: 12px; color: rgba(255,255,255,0.65);
        font-size: 16px; font-weight: 600; padding: 11px 20px; transition: background 0.15s ease, color 0.15s ease;
      }
      .app-nav a:hover { background: rgba(255,255,255,0.06); color: #fff; }
      .app-nav a.active { background: rgba(255,255,255,0.1); color: #fff; box-shadow: inset 3px 0 0 ${TOKENS.amber}; }
      .app-sidebar-foot {
        border-top: 1px solid rgba(255,255,255,0.12); margin-top: auto; padding: 14px 20px 18px;
        display: grid; gap: 10px; color: rgba(255,255,255,0.5); font-size: 14px;
      }
      .app-version-label { min-height: 1em; }
      .theme-toggle {
        display: flex; align-items: center; gap: 8px; background: transparent; border: 1px solid rgba(255,255,255,0.3);
        border-radius: 5px; color: #fff; font-size: 14px; font-weight: 600; padding: 8px 10px; text-align: left;
      }
      .theme-toggle:hover { background: rgba(255,255,255,0.08); }
      .app-main { flex: 1; min-width: 0; }

      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .app-sidebar { width: 64px; }
        .app-brand { padding: 0 0 18px; justify-content: center; }
        .app-brand-label, .app-nav-label { display: none; }
        .app-nav a { justify-content: center; padding: 12px 0; }
        .app-sidebar-foot { align-items: center; justify-items: center; padding: 14px 8px 18px; }
        .app-version-label { display: none; }
      }

      /* ---- landing (always brand-navy, no theme toggle available here) ---- */
      .landing {
        min-height: 100vh; width: 100%; background: ${TOKENS.indigo}; position: relative;
        overflow: hidden; display: flex; flex-direction: column; font-family: ${FONT_TEXT};
      }
      .landing-body { position: relative; z-index: 1; flex: 1; display: flex; flex-direction: column; justify-content: center; width: min(1280px, 92vw); margin: 0 auto; padding: 40px 0; }
      .landing-hero { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: clamp(32px, 6vw, 80px); align-items: center; }
      .landing-logo { height: 30px; width: auto; margin-bottom: 28px; opacity: 0; animation: revealIn 0.65s cubic-bezier(0.16,1,0.3,1) forwards; }
      .landing-eyebrow {
        display: inline-flex; align-items: center; gap: 8px; color: ${TOKENS.amber};
        font-size: 12px; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase;
        margin-bottom: 22px; opacity: 0; animation: revealIn 0.65s cubic-bezier(0.16,1,0.3,1) 0.08s forwards;
      }
      .landing-headline {
        font-family: ${FONT_DISPLAY}; font-weight: 700; font-size: clamp(36px, 5vw, 60px);
        line-height: 1.06; color: #fff; margin: 0; letter-spacing: -0.01em;
        opacity: 0; animation: revealIn 0.65s cubic-bezier(0.16,1,0.3,1) 0.16s forwards;
      }
      .landing-sub {
        font-size: 18px; line-height: 1.6; color: rgba(255,255,255,0.72); max-width: 480px;
        margin: 20px 0 34px; opacity: 0; animation: revealIn 0.65s cubic-bezier(0.16,1,0.3,1) 0.24s forwards;
      }
      .landing-actions {
        display: flex; gap: 14px; flex-wrap: wrap;
        opacity: 0; animation: revealIn 0.65s cubic-bezier(0.16,1,0.3,1) 0.32s forwards;
      }
      .landing-cta { font-size: 15px; padding: 14px 24px; }
      .landing-pulse {
        background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px; padding: 28px 30px; backdrop-filter: blur(6px);
        opacity: 0; animation: revealIn 0.65s cubic-bezier(0.16,1,0.3,1) 0.24s forwards;
      }
      .landing-pulse-label { color: rgba(255,255,255,0.5); font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; display: block; margin-bottom: 18px; }
      .landing-pulse-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
      .pulse-stat { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
      .pulse-stat strong { color: #fff; font-family: ${FONT_DISPLAY}; font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
      .pulse-stat span { color: rgba(255,255,255,0.55); font-size: 12.5px; }
      .landing-footer {
        position: relative; z-index: 1; border-top: 1px solid rgba(255,255,255,0.08);
        padding: 20px 0; display: flex; justify-content: space-between; align-items: center;
        width: min(1280px, 92vw); margin: 0 auto;
      }
      .landing-footer > span { color: rgba(255,255,255,0.4); font-size: 12.5px; }

      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .landing-hero { grid-template-columns: 1fr; }
        .landing-pulse-grid { grid-template-columns: 1fr 1fr; }
      }

      /* ---- topbar ---- */
      .topbar { background: var(--navy); padding: 20px 0; }
      .topbar-inner {
        /* width relative to .app-main (100%), not the full viewport (92vw) -
           .app-main is already narrower than the viewport by the sidebar's
           width, so a vw-based width here overflowed past it. No max-width
           cap: the page should fill whatever screen/aspect ratio it's on. */
        width: 100%; margin: 0 auto; padding: 0 clamp(20px, 2.5vw, 48px);
        display: flex; align-items: center; gap: 20px; flex-wrap: wrap; box-sizing: border-box;
      }
      .topbar-title { flex: 1; display: flex; flex-direction: column; min-width: 0; }
      .topbar-client { color: #fff; font-family: ${FONT_DISPLAY}; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .topbar-meta { color: rgba(255,255,255,0.55); font-size: 14.5px; margin-top: 4px; }

      /* ---- engagement sub-page header (legacy shell() parity: plain white
         bar with an eyebrow + title, not the navy portfolio-level topbar
         above) - used by EngagementLayout for Overview/Phases/Import/Exceptions ---- */
      .engagement-topbar {
        align-items: center; background: var(--card); border-bottom: 1px solid var(--border);
        display: flex; height: 68px; padding: 0 clamp(20px, 2.5vw, 48px); position: sticky; top: 0; z-index: 10;
      }
      .engagement-topbar-inner { width: 100%; margin: 0 auto; }
      .engagement-topbar h1 { color: var(--foreground); font-size: 23px; font-weight: 800; letter-spacing: -0.01em; line-height: 1.1; margin: 2px 0 0; }

      /* No max-width cap - fills the window on any monitor/aspect ratio;
         side padding scales gently with viewport width via clamp(). */
      .page-body { width: 100%; margin: 0 auto; padding: 32px clamp(20px, 2.5vw, 48px) 60px; box-sizing: border-box; }

      /* ---- tab nav (parity with legacy engagementTabs) ---- */
      .tabs { border-bottom: 1px solid var(--border); display: flex; gap: 4px; overflow: auto; margin-bottom: 20px; }
      .tabs a { color: var(--muted); font-size: 13px; font-weight: 700; padding: 11px 14px; white-space: nowrap; box-shadow: inset 0 -2px 0 transparent; }
      .tabs a:hover { background: rgba(245,168,0,0.1); color: var(--foreground); }
      .tabs a.active { color: var(--emphasis); box-shadow: inset 0 -2px 0 ${TOKENS.amber}; }

      /* ---- generic content primitives (card/table/alert/eyebrow), reused
         across every engagement sub-page as legacy screens port over ---- */
      .eyebrow { display: block; color: ${TOKENS.amber}; font-size: 13px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 6px; }
      .card { background: var(--card); border: 1px solid var(--border); box-shadow: var(--shadow); border-radius: 10px; padding: 22px 24px; margin-bottom: 20px; }
      .card h2 { font-family: ${FONT_DISPLAY}; font-size: 18px; color: var(--emphasis); margin: 0 0 6px; }
      .card > .hint:first-of-type { margin-top: 0; }
      .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; margin: 14px 0; }
      .table-wrap table { width: 100%; border-collapse: collapse; font-size: 16px; }
      .table-wrap th { text-align: left; color: var(--muted); font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; padding: 10px 12px; border-bottom: 1px solid var(--border); background: var(--hover-overlay); white-space: nowrap; }
      .table-wrap td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--foreground); vertical-align: top; }
      .table-wrap tr:last-child td { border-bottom: none; }
      .table-wrap td.mono, .mono { font-family: ui-monospace, "SFMono-Regular", Consolas, monospace; font-size: 12.5px; }
      .table-wrap td input, .table-wrap td select {
        width: 100%; padding: 7px 9px; border: 1px solid var(--border); border-radius: 4px;
        background: var(--input); color: var(--foreground); font-size: 13.5px; font-family: inherit;
      }
      .table-wrap td input:disabled, .table-wrap td select:disabled { opacity: 0.55; }

      /* ---- two-column table + side-panel form layout (Phases, and future
         Adjustments/Expenses pages that share this shape) ---- */
      .split-layout { display: grid; gap: 18px; grid-template-columns: minmax(0, 1.7fr) minmax(300px, 0.7fr); align-items: start; }
      .side-form form { display: grid; gap: 14px; }
      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .split-layout { grid-template-columns: 1fr; }
      }
      .field textarea, .field select {
        padding: 9px 11px; border: 1px solid var(--border); border-radius: 5px; font-size: 14px;
        background: var(--input); color: var(--foreground); font-family: inherit;
      }
      .field.compact { max-width: 320px; }
      .alert { display: flex; align-items: flex-start; gap: 10px; border-radius: 8px; padding: 14px 18px; margin: 14px 0; font-size: 14px; }
      .alert.warning { background: var(--warning-bg); border: 1px solid var(--warning-border); color: ${TOKENS.amberDark}; }
      .alert.success { background: rgba(5,171,140,0.1); border: 1px solid rgba(5,171,140,0.35); color: ${TOKENS.teal}; }
      .alert strong { color: inherit; }

      /* ---- close/reopen control (lives inside the navy .engagement-hero) ---- */
      .status-stack { align-items: flex-end; display: grid; gap: 12px; justify-items: end; }
      .status-control { color: #fff; max-width: 320px; text-align: left; }
      .status-control summary { cursor: pointer; font-size: 14px; font-weight: 700; color: #fff; }
      .status-stack .hint { color: rgba(255,255,255,0.72); text-align: right; }
      .status-control form {
        background: var(--card); border: 1px solid var(--border); box-shadow: 0 8px 24px rgba(1,30,65,0.12);
        color: var(--foreground); display: grid; gap: 10px; margin-top: 8px; padding: 16px;
        position: absolute; right: 0; width: 320px; z-index: 5; text-align: left; border-radius: 8px;
      }
      .field { display: grid; gap: 6px; }
      .field span { font-size: 15px; font-weight: 600; color: var(--muted); }
      .field input { padding: 9px 11px; border: 1px solid var(--border); border-radius: 5px; font-size: 14px; background: var(--input); color: var(--foreground); }
      .hint { color: var(--muted); font-size: 15px; }
      .danger-text { color: var(--destructive) !important; }
      .btn { display: inline-flex; align-items: center; gap: 7px; border: none; border-radius: 5px; font-size: 16px; font-weight: 700; padding: 10px 18px; transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease, background 0.15s ease; }
      .btn.primary { background: ${TOKENS.amber}; color: ${TOKENS.indigo}; box-shadow: 0 1px 2px rgba(0,0,0,0.16); }
      .btn.primary:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(245,168,0,0.28); }
      .btn.danger { background: var(--destructive); color: #fff; }
      .btn.text { background: transparent; color: ${TOKENS.indigoBright}; font-size: 14px; padding: 5px 0; margin-top: 10px; display: inline-block; }
      .btn.secondary { background: var(--card); border: 1px solid var(--border); color: var(--foreground); }
      .btn.secondary:hover { border-color: var(--navy); }
      .btn.ghost { background: transparent; color: #fff; border: 1px solid rgba(255,255,255,0.28); }
      .btn.ghost:hover { border-color: rgba(255,255,255,0.55); background: rgba(255,255,255,0.06); }
      .button-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

      /* ---- dashboard ---- */
      .topbar-inner .button-row { margin-left: auto; }
      .empty { color: var(--muted); font-size: 15px; padding: 20px 4px; }

      .portfolio-grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); margin-bottom: 20px; }
      .portfolio-card {
        background: var(--card); border: 1px solid var(--border); border-left: 4px solid ${TOKENS.teal}; box-shadow: var(--shadow);
        border-radius: 8px; display: block; padding: 20px 22px; color: inherit; min-width: 0;
        transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
      }
      .portfolio-card:hover { transform: translateY(-2px); border-left-color: ${TOKENS.indigo}; box-shadow: 0 10px 24px rgba(1,30,65,0.1); }
      .portfolio-card.status-watch { border-left-color: ${TOKENS.amberDark}; }
      .portfolio-card.status-trending-over { border-left-color: ${TOKENS.amber}; }
      .portfolio-card.status-over-budget { border-left-color: ${TOKENS.coral}; }
      .portfolio-card.proposal-card { border-left-color: ${TOKENS.indigoBright}; }
      .portfolio-card-kicker { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
      .portfolio-card-kicker > span:first-child { color: var(--muted); font-size: 14px; font-weight: 700; letter-spacing: 0.03em; }
      .portfolio-card h3 {
        font-family: ${FONT_DISPLAY}; font-size: 21px; line-height: 1.25; color: var(--foreground); margin: 10px 0 2px;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
      }
      .portfolio-card p, .portfolio-card small { color: var(--muted); font-size: 15px; }
      .portfolio-card p { margin: 0 0 12px; }
      .portfolio-progress { background: var(--track); border-radius: 3px; height: 8px; margin: 0 0 12px; overflow: hidden; }
      .portfolio-progress i { display: block; height: 100%; background: ${TOKENS.teal}; }
      .status-watch .portfolio-progress i { background: ${TOKENS.amberDark}; }
      .status-trending-over .portfolio-progress i { background: ${TOKENS.amber}; }
      .status-over-budget .portfolio-progress i { background: ${TOKENS.coral}; }
      .portfolio-card-stats { display: flex; justify-content: space-between; gap: 14px; margin: 4px 0 8px; font-size: 16px; }
      .portfolio-card-stats b { font-variant-numeric: tabular-nums; }
      .proposal-tag { background: rgba(0,63,159,0.1); color: ${TOKENS.indigoBright}; font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 10px; }

      /* ---- onboarding welcome + weekly routine cards (parity with legacy) ---- */
      .welcome-card, .workflow-card {
        background: var(--navy); border-bottom: 4px solid ${TOKENS.amber}; border-radius: 10px; color: #fff;
        display: flex; gap: 28px; justify-content: space-between; align-items: center; flex-wrap: wrap;
        padding: 26px 30px; margin-bottom: 20px;
      }
      .welcome-card h2, .workflow-card h2 { font-family: ${FONT_DISPLAY}; color: #fff; margin: 6px 0; }
      .welcome-card p { color: rgba(255,255,255,0.82); margin: 0; max-width: 760px; }
      .welcome-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; flex-shrink: 0; }
      .workflow-card { background: var(--card); border: 1px solid var(--border); border-left: 4px solid ${TOKENS.amber}; color: var(--foreground); }
      .workflow-card h2 { color: var(--foreground); }
      .workflow-card a { color: ${TOKENS.indigoBright}; font-weight: 700; flex-shrink: 0; }
      .workflow-steps { counter-reset: step; display: flex; flex-wrap: wrap; gap: 8px; list-style: none; margin: 0; padding: 0; }
      .workflow-steps li {
        align-items: center; background: var(--page-bg); border: 1px solid var(--border); color: var(--foreground);
        display: flex; font-size: 14px; font-weight: 700; gap: 6px; padding: 7px 10px; border-radius: 4px;
      }
      .workflow-steps li::before {
        align-items: center; background: var(--navy); color: #fff; counter-increment: step; content: counter(step);
        border-radius: 50%; display: inline-flex; font-size: 9px; height: 16px; justify-content: center; width: 16px; flex-shrink: 0;
      }
      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .welcome-card, .workflow-card { align-items: flex-start; display: grid; }
      }
      @media (max-width: ${BREAKPOINTS.snapped}px) {
        .welcome-card, .workflow-card { padding: 22px; }
        .workflow-steps { display: grid; grid-template-columns: repeat(2, 1fr); width: 100%; }
      }

      /* ---- metrics ---- */
      .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
      .metric-card {
        background: var(--card); border: 1px solid var(--border); box-shadow: var(--shadow);
        border-radius: 8px; padding: 18px 20px; position: relative;
        transition: box-shadow 0.2s ease, transform 0.2s ease;
      }
      .metric-card:hover { box-shadow: 0 6px 18px rgba(1,30,65,0.08); transform: translateY(-2px); }
      .metric-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
      .metric-icon { color: ${TOKENS.amberDark}; display: flex; }
      .metric-card.tone-warning .metric-icon { color: ${TOKENS.coral}; }
      .metric-label { color: var(--muted); font-size: 14px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
      .metric-value { display: block; color: var(--emphasis); font-family: ${FONT_DISPLAY}; font-size: 30px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
      .metric-card.tone-warning .metric-value { color: ${TOKENS.coral}; }
      .metric-sub { color: var(--muted); font-size: 15px; }

      .section-card { background: var(--card); border: 1px solid var(--border); box-shadow: var(--shadow); border-radius: 10px; padding: 24px 24px 10px; }
      .section-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; padding: 0 4px; flex-wrap: wrap; gap: 10px; }
      .section-head h2 { font-family: ${FONT_DISPLAY}; font-size: 18px; color: var(--emphasis); margin: 0; }
      .section-hint { color: var(--muted); font-size: 15px; }

      .added-tag { background: rgba(0,63,159,0.08); color: ${TOKENS.indigoBright}; font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 10px; }

      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .topbar-inner .button-row { margin-left: 0; width: 100%; }
      }

      /* ---- legacy-parity: Overview page (engagement hero, plain metric
         cards, budget position, phase breakdown table) ---- */
      .status-badge { border: 1px solid currentColor; display: inline-flex; font-size: 13px; font-weight: 800; letter-spacing: 0.05em; padding: 5px 8px; text-transform: uppercase; border-radius: 3px; }
      .status-badge.on-track, .status-badge.active { color: ${TOKENS.teal}; }
      .status-badge.watch, .status-badge.planning { color: ${TOKENS.amberDark}; }
      .status-badge.trending-over { color: ${TOKENS.amber}; }
      .status-badge.over-budget, .status-badge.closed { color: var(--destructive); }

      .engagement-hero {
        align-items: end; background: var(--navy); color: #fff; display: flex; flex-wrap: wrap;
        justify-content: space-between; gap: 20px; min-height: 120px; padding: 26px 30px;
        position: relative; border-radius: 10px; margin-bottom: 20px; overflow: hidden;
      }
      .engagement-hero::after { background: ${TOKENS.amber}; content: ""; height: 7px; position: absolute; inset: auto 0 0; }
      .engagement-hero h2 { color: #fff; font-family: ${FONT_DISPLAY}; font-size: 26px; margin: 8px 0 0; }
      .hero-badges { display: flex; gap: 8px; }

      .metrics-legacy { display: grid; gap: 12px; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 20px; }
      .metric-legacy { background: var(--card); border: 1px solid var(--border); border-top: 3px solid ${TOKENS.amber}; border-radius: 6px; padding: 18px 20px; }
      .metric-legacy span { color: var(--muted); display: block; font-size: 14px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
      .metric-legacy strong { color: var(--foreground); display: block; font-family: ${FONT_DISPLAY}; font-size: 26px; font-variant-numeric: tabular-nums; font-weight: 800; letter-spacing: -0.02em; margin-top: 10px; }
      .metric-legacy small { color: var(--muted); }
      @media (max-width: 1100px) { .metrics-legacy { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
      @media (max-width: ${BREAKPOINTS.narrow}px) { .metrics-legacy { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

      .budget-position-legacy { display: grid; gap: 24px; grid-template-columns: 1fr 260px; }
      .budget-position-legacy .bp-main { display: grid; gap: 16px; }
      .budget-position-legacy .bp-head { align-items: center; display: flex; justify-content: space-between; }
      .budget-position-legacy .bp-head h2 { margin: 0; }
      .budget-position-legacy .bp-progress { background: color-mix(in srgb, var(--navy) 10%, transparent); border-radius: 4px; height: 12px; overflow: hidden; }
      .budget-position-legacy .bp-progress i { background: ${TOKENS.teal}; display: block; height: 100%; }
      .budget-position-legacy .bp-progress.watch i { background: ${TOKENS.amberDark}; }
      .budget-position-legacy .bp-progress.trending-over i { background: ${TOKENS.amber}; }
      .budget-position-legacy .bp-progress.over-budget i { background: var(--destructive); }
      .budget-position-legacy .bp-stats { align-items: center; display: flex; flex-wrap: wrap; gap: 14px; justify-content: space-between; font-size: 14px; }
      .budget-position-legacy .bp-stats b { font-variant-numeric: tabular-nums; }
      .budget-position-legacy aside { background: var(--navy); color: #fff; display: grid; padding: 20px; border-radius: 6px; }
      .budget-position-legacy aside span:first-child { color: rgba(255,255,255,0.7); font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; }
      .budget-position-legacy aside strong { color: ${TOKENS.amber}; font-family: ${FONT_DISPLAY}; font-size: 32px; margin: 6px 0; }
      .budget-position-legacy aside small { color: #c5d0df; }
      @media (max-width: ${BREAKPOINTS.narrow}px) { .budget-position-legacy { grid-template-columns: 1fr; } }

      /* Phase breakdown: CSS Grid rows, not a <table> - see the comment on
         PhaseBreakdownRow in Overview.jsx for why. Column proportions here
         must stay in sync with the 8 <div>s in .phase-breakdown-head and
         each row: Phase, Budget hours, Actual hours, Remaining, Effective
         SOW, Actual fees, Realization, Status. */
      .phase-breakdown { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
      .phase-breakdown-head, .phase-breakdown-row {
        display: grid; grid-template-columns: 20fr 9fr 9fr 9fr 18fr 11fr 10fr 14fr;
        gap: 12px; align-items: center; padding: 10px 12px;
      }
      .phase-breakdown-head {
        background: var(--hover-overlay); border-bottom: 1px solid var(--border);
        color: var(--muted); font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
      }
      .phase-breakdown-row { border-bottom: 1px solid var(--border); font-size: 16px; color: var(--foreground); }
      .phase-confidence-hint { color: var(--muted); font-size: 12px; font-weight: 400; margin-top: 2px; }
      .phase-breakdown-detail { background: color-mix(in srgb, ${TOKENS.amber} 5%, var(--card)); padding: 18px; border-bottom: 1px solid var(--border); }

      .phase-expander { background: ${TOKENS.amber}; border: 0; border-radius: 4px; color: ${TOKENS.indigo}; cursor: pointer; font-weight: 800; height: 26px; width: 26px; font-size: 14px; line-height: 1; }
      .weekly-detail-explanation { color: var(--muted); margin: 0 0 12px; }
      .inline-phase-detail .weekly-grid td { min-width: 90px; text-align: right; font-variant-numeric: tabular-nums; }

      /* Excel-style budget/actual split: one row per metric per person
         (not stacked inside a single cell) so the two numbers are easy to
         tell apart at a glance, color-coded like the source workbook.
         Freezing the name column reuses the generic .weekly-grid
         th:first-child sticky rule (auto table layout, proven elsewhere in
         this table) - only ONE column freezes; the row-label column
         deliberately scrolls with the rest rather than also being pinned.
         table-layout:fixed was tried here and rejected: forcing every
         column to a fixed pixel width made the browser collapse all but
         the first column to near-zero width instead of laying out cleanly,
         so this sticks to auto layout throughout. Opaque color-mix (not
         translucent rgba) backgrounds so the frozen name column doesn't
         show scrolled-past cells ghosting through it. */
      .weekly-grid.weekly-grid-rows th:first-child { min-width: 180px; }
      .weekly-grid.weekly-grid-rows .row-label {
        color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.02em; text-align: left !important; min-width: 150px; white-space: nowrap;
      }
      .weekly-grid.weekly-grid-rows tr.row-budget td, .weekly-grid.weekly-grid-rows tr.row-budget th { background: color-mix(in srgb, ${TOKENS.indigoBright} 7%, var(--card)); }
      .weekly-grid.weekly-grid-rows tr.row-actual td, .weekly-grid.weekly-grid-rows tr.row-actual th { background: color-mix(in srgb, ${TOKENS.amber} 10%, var(--card)); border-bottom: 2px solid var(--border); }
      .weekly-grid.weekly-grid-rows tbody th { vertical-align: middle; }
      .legend-budget::before, .legend-actual::before { content: ""; display: inline-block; height: 8px; width: 8px; margin-right: 4px; border-radius: 2px; }
      .legend-budget::before { background: ${TOKENS.indigoBright}; }
      .legend-actual::before { background: ${TOKENS.amber}; }

      /* ---- weekly import ---- */
      .upload-zone {
        display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center;
        border: 1px dashed var(--border); border-radius: 8px; padding: 26px 20px; margin: 14px 0;
        cursor: pointer; color: var(--muted); transition: border-color 0.15s ease, background 0.15s ease;
      }
      .upload-zone:hover { border-color: ${TOKENS.indigoBright}; background: var(--hover-overlay); }
      .upload-zone svg { color: ${TOKENS.amberDark}; }
      .upload-zone strong { color: var(--foreground); font-size: 14px; }
      .upload-zone span { font-size: 12.5px; }
      .upload-zone input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }

      .resolution-row {
        display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 0;
        border-top: 1px solid var(--border); font-size: 14px;
      }
      .resolution-row:first-of-type { border-top: none; }
      .resolution-row > span { flex: 1; min-width: 220px; color: var(--foreground); }
      .resolution-row select { flex-shrink: 0; }

      .assignment-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin-top: 12px; }

      .flag-key { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 10px; font-size: 13px; color: var(--muted); }
      .flag-key b { color: var(--foreground); }

      .flag {
        display: inline-block; background: rgba(229,55,107,0.12); color: ${TOKENS.coral};
        font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em;
        border-radius: 10px; padding: 2px 8px; margin: 0 4px 4px 0;
      }
      tr.duplicate .flag, tr.zero_hours .flag { background: rgba(130,130,130,0.15); color: var(--muted); }
      .flag-guidance { display: block; color: var(--muted); font-size: 11.5px; margin-top: 2px; }
      tr.duplicate td { opacity: 0.55; }

      .commit-confirm {
        background: var(--hover-overlay); border: 1px solid var(--border); border-radius: 8px;
        padding: 16px 18px; margin-top: 14px;
      }
      .commit-confirm p { margin: 0 0 12px; color: var(--foreground); font-size: 14px; }

      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .resolution-row > span { min-width: 0; width: 100%; }
      }

      /* ---- exceptions queue ---- */
      .exceptions-table tr.resolved td, .exceptions-table tr.excluded td { opacity: 0.6; }
      /* ---- weekly hours overages (reuses .exceptions-table) ---- */
      .exceptions-table tr.mild td:first-child { border-left: 3px solid ${TOKENS.amberDark}; }
      .exceptions-table tr.severe td:first-child { border-left: 3px solid var(--destructive); }
      .exception-status {
        display: inline-block; font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
        border-radius: 10px; padding: 3px 9px;
      }
      .exception-status.pending { background: var(--warning-bg); color: ${TOKENS.amberDark}; }
      .exception-status.resolved { background: rgba(5,171,140,0.12); color: ${TOKENS.teal}; }
      .exception-status.excluded { background: rgba(130,130,130,0.15); color: var(--muted); }
      .exception-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
      .exception-actions select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 5px; font-size: 13px; background: var(--input); color: var(--foreground); }
      .exception-actions input { padding: 6px 9px; border: 1px solid var(--border); border-radius: 5px; font-size: 13px; background: var(--input); color: var(--foreground); width: 150px; }
      .exception-actions .btn.text { margin-top: 0; white-space: nowrap; }
      .allocation-candidates { flex-basis: 100%; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12.5px; }
      .allocation-candidates-label { color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em; font-size: 11px; }
      .allocation-candidate { background: rgba(5,171,140,0.12); color: ${TOKENS.teal}; border-radius: 12px; padding: 3px 10px !important; font-size: 12.5px !important; }
      .allocation-memo-hint { flex-basis: 100%; margin: 0; font-size: 13px; }
      .allocation-memo-hint .btn.text { margin-left: 6px; }
      .allocation-rules-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
      .allocation-rules-list li { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; }

      /* ---- phase detail / weekly grid ---- */
      .weekly-grid-wrap { border: 1px solid var(--border); border-radius: 8px; max-width: 100%; overflow: auto; margin: 14px 0; }
      .weekly-grid { border-collapse: separate; border-spacing: 0; min-width: max-content; font-size: 15px; }
      .weekly-grid th, .weekly-grid td { background: var(--card); border-bottom: 1px solid var(--border); border-right: 1px solid var(--border); min-width: 96px; padding: 8px; }
      .weekly-grid thead th { background: var(--navy); color: #fff; position: sticky; top: 0; z-index: 2; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; white-space: nowrap; }
      .weekly-grid tbody th { background: var(--card); color: var(--foreground); text-align: left; font-weight: 700; }
      /* First column stays frozen while scrolling horizontally, in both the
         header and body rows - combining with the top-sticky rule above
         gives thead's first cell a pinned top-left corner. */
      .weekly-grid th:first-child { position: sticky; left: 0; min-width: 200px; z-index: 3; border-right: 3px solid ${TOKENS.indigo}; }
      .weekly-grid thead th:first-child { z-index: 4; }
      .weekly-grid td label { align-items: center; color: var(--muted); display: flex; font-size: 10px; gap: 5px; margin: 3px 0; }
      .weekly-grid td input { min-width: 66px; padding: 6px; width: 100%; border: 1px solid var(--border); border-radius: 4px; background: var(--input); color: var(--foreground); font-size: 14px; }
      .weekly-grid td output { color: var(--foreground); font-size: 15px; }
      .weekly-grid td.variance { box-shadow: inset 0 0 0 2px ${TOKENS.amber}; position: relative; }
      .weekly-grid td.variance::after { border-color: ${TOKENS.amber} ${TOKENS.amber} transparent transparent; border-style: solid; border-width: 7px; content: ""; position: absolute; right: 0; top: 0; }
      .weekly-grid td.budget-mild { border-left: 3px solid ${TOKENS.amberDark}; }
      .weekly-grid td.budget-severe { border-left: 3px solid var(--destructive); }
      .cell-revise { background: transparent; border: 0; color: ${TOKENS.indigoBright}; font-size: 9px; padding: 0; text-decoration: underline; cursor: pointer; }
      .legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 12px 0; color: var(--muted); font-size: 11px; align-items: center; }
      .legend .variance-key::before, .legend .legend-budget-mild::before, .legend .legend-budget-severe::before {
        content: ""; display: inline-block; height: 8px; margin-right: 4px; width: 8px;
      }
      .legend .variance-key::before { background: ${TOKENS.amber}; }
      .legend .legend-budget-mild::before { background: ${TOKENS.amberDark}; }
      .legend .legend-budget-severe::before { background: var(--destructive); }
      .bulk-forecast {
        align-items: end; background: color-mix(in srgb, ${TOKENS.amber} 7%, var(--card)); border: 1px solid var(--border);
        display: grid; gap: 12px; grid-template-columns: 1.4fr repeat(5, minmax(120px, 1fr)); margin: 18px 0; padding: 16px; border-radius: 8px;
      }
      .bulk-forecast .field { margin: 0; }
      .bulk-forecast h3 { margin: 4px 0 0; font-size: 15px; color: var(--foreground); }

      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .bulk-forecast { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }
      @media (max-width: ${BREAKPOINTS.snapped}px) {
        .bulk-forecast { grid-template-columns: 1fr; }
      }

      /* ---- help page ---- */
      .help-hero {
        background: var(--navy); border-bottom: 4px solid ${TOKENS.amber}; border-radius: 10px; color: #fff;
        display: flex; align-items: flex-start; gap: 28px; justify-content: space-between; flex-wrap: wrap;
        padding: 26px 30px; margin-bottom: 24px;
      }
      .help-hero h2 { font-family: ${FONT_DISPLAY}; color: #fff; margin: 6px 0; }
      .help-hero p { color: #d5dfeb; margin: 0; max-width: 620px; }
      .help-jumps { display: grid; gap: 6px; min-width: 260px; }
      .help-jumps a { background: rgba(255,255,255,0.08); border-left: 3px solid ${TOKENS.amber}; color: #fff; font-size: 13px; font-weight: 600; padding: 8px 10px; }
      .help-jumps a:hover { background: rgba(255,255,255,0.14); }

      .help-section {
        background: var(--card); border: 1px solid var(--border); border-radius: 10px;
        display: grid; grid-template-columns: 64px 1fr; gap: 24px; padding: 26px;
        scroll-margin-top: 20px; margin-bottom: 18px;
      }
      .help-section h2 { font-family: ${FONT_DISPLAY}; font-size: 19px; color: var(--foreground); margin-top: 0; }
      .help-section li { color: var(--foreground); margin: 8px 0; }
      .help-section p { color: var(--foreground); margin: 0; }
      .step-number { font-family: ${FONT_DISPLAY}; color: ${TOKENS.amber}; font-size: 30px; font-weight: 900; }
      .glossary dl { display: grid; gap: 8px 20px; grid-template-columns: 160px 1fr; margin: 0; }
      .glossary dt { color: var(--foreground); font-weight: 800; }
      .glossary dd { color: var(--muted); margin: 0; }

      @media (max-width: ${BREAKPOINTS.narrow}px) {
        .help-hero { align-items: flex-start; display: grid; }
        .help-jumps { min-width: 0; }
      }
      @media (max-width: ${BREAKPOINTS.snapped}px) {
        .help-section { grid-template-columns: 1fr; }
        .glossary dl { grid-template-columns: 1fr; }
        .glossary dd { margin-bottom: 10px; }
      }

      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { animation: none !important; transition: none !important; }
      }
    `}</style>
  );
}
