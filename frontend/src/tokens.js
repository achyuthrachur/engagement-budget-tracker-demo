export const TOKENS = {
  indigo: "#011E41",
  indigoBright: "#003F9F",
  indigoCore: "#002E62",
  amber: "#F5A800",
  amberDark: "#D7761D",
  amberBright: "#FFD231",
  teal: "#05AB8C",
  coral: "#E5376B",
  white: "#FFFFFF",
  tintLightest: "#E0E0E0",
  tintLight: "#BDBDBD",
  tintMid: "#828282",
  tintMidDark: "#4F4F4F",
  tintDark: "#333333",
};

export const FONT_DISPLAY =
  "'Helvetica Now Display','Helvetica Now',Arial,Helvetica,sans-serif";
export const FONT_TEXT =
  "'Helvetica Now Text','Helvetica Now',Arial,Helvetica,sans-serif";

export const STATUS_COLOR = {
  "On Track": TOKENS.teal,
  Watch: TOKENS.amberDark,
  "Trending Over": TOKENS.amber,
  "Over Budget": TOKENS.coral,
};

// Semantic surface/text tokens that invert between light and dark mode.
// Dark values are pinned to legacy's `:root[data-theme="dark"]` block in
// app/static/styles.css so both stacks read as the same product while they
// coexist. Brand colors (TOKENS above) do not change between themes.
export const THEME = {
  light: {
    pageBg: "#F3F4F6",
    card: "#FFFFFF",
    foreground: "#16202C",
    muted: "#57626E",
    border: "rgba(1,30,65,0.12)",
    input: "#FFFFFF",
    navy: TOKENS.indigo,
    navyHover: "#0A2E57",
    destructive: "#B42318",
    track: TOKENS.tintLightest,
    hoverOverlay: "rgba(1,30,65,0.028)",
    emphasis: TOKENS.indigo,
    warningBg: "#FDF1E4",
    warningBorder: "#F2CE9A",
    shadow: "0 1px 2px rgba(1,30,65,0.05)",
  },
  dark: {
    pageBg: "#071527",
    card: "#0E2440",
    foreground: "#EDF3FA",
    muted: "#9FADC0",
    border: "rgba(143,225,255,0.14)",
    input: "#102C4D",
    navy: "#01152E",
    navyHover: "#123B69",
    destructive: "#FF8A9B",
    track: "#173458",
    hoverOverlay: "rgba(255,255,255,0.04)",
    emphasis: "#EDF3FA",
    warningBg: "rgba(215,118,29,0.16)",
    warningBorder: "rgba(215,118,29,0.4)",
    shadow: "0 1px 2px rgba(0,0,0,0.35)",
  },
};

export function themeVarsBlock(vars) {
  return `
    --page-bg: ${vars.pageBg};
    --card: ${vars.card};
    --foreground: ${vars.foreground};
    --muted: ${vars.muted};
    --border: ${vars.border};
    --input: ${vars.input};
    --navy: ${vars.navy};
    --navy-hover: ${vars.navyHover};
    --destructive: ${vars.destructive};
    --track: ${vars.track};
    --hover-overlay: ${vars.hoverOverlay};
    --emphasis: ${vars.emphasis};
    --warning-bg: ${vars.warningBg};
    --warning-border: ${vars.warningBorder};
    --shadow: ${vars.shadow};
  `;
}

// Named breakpoints framed around real Windows window-management states
// (this is a desktop app opened in a resizable browser window, not a public
// responsive site) rather than generic mobile/tablet/desktop device tiers.
// Each value is the upper bound (max-width) of the named tier.
export const BREAKPOINTS = {
  snapped: 640, // quarter-snapped / aggressively shrunk window
  narrow: 900, // half-snapped side-by-side windows - the common "cramped" case
  standard: 1440, // maximized on a typical 13-15" laptop
  wide: 1920, // maximized on a 1920x1080+ external monitor
};

export const TYPE = {
  xs: "11px",
  sm: "12.5px",
  base: "14px",
  md: "15px",
  lg: "18px",
  xl: "22px",
  displaySm: "26px",
  displayMd: "30px",
  displayLg: "clamp(36px, 5vw, 60px)",
};

// 4px-based spacing scale, keyed by step number.
export const SPACE = {
  1: "4px",
  2: "8px",
  3: "12px",
  4: "16px",
  5: "20px",
  6: "24px",
  8: "32px",
  10: "40px",
  12: "48px",
  16: "64px",
};
