import { useCallback, useState } from "react";

const STORAGE_KEY = "budget-theme";

function readInitialTheme() {
  if (typeof window === "undefined") return "light";
  return localStorage.getItem(STORAGE_KEY) || "light";
}

// Mirrors the legacy app's theme mechanism exactly (same localStorage key,
// same `document.documentElement.dataset.theme` attribute) so the two
// stacks read as one product while the migration is in progress.
export function useTheme() {
  const [theme, setTheme] = useState(readInitialTheme);

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next = current === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}
