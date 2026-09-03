import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  DEFAULT_THEME,
  applyTheme,
  prefersDark,
  readStoredTheme,
  resolveTheme,
  storeTheme,
} from "./theme";

const ThemeContext = createContext(null);

/**
 * Owns the `.dark` class on <html> and persists the user's choice.
 *
 * Nothing in the UI drives this yet — it exists so the application shell can
 * pick it up when the screens are redesigned.
 */
export function ThemeProvider({ children, defaultTheme = DEFAULT_THEME }) {
  const [theme, setThemeState] = useState(() =>
    typeof window === "undefined" ? defaultTheme : readStoredTheme()
  );
  const [resolvedTheme, setResolvedTheme] = useState(() =>
    typeof window === "undefined" ? defaultTheme : resolveTheme(readStoredTheme())
  );

  useEffect(() => {
    setResolvedTheme(applyTheme(theme));
  }, [theme]);

  // Only "system" tracks the OS; light and dark stay pinned.
  useEffect(() => {
    if (theme !== "system") return undefined;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setResolvedTheme(applyTheme("system"));
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next) => {
    storeTheme(next);
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(resolveTheme(readStoredTheme()) === "dark" ? "light" : "dark");
  }, [setTheme]);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme, toggleTheme, systemPrefersDark: prefersDark }),
    [theme, resolvedTheme, setTheme, toggleTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
