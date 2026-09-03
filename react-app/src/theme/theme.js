// Theme plumbing shared by the provider and by the inline boot script in
// index.html. Keep this file free of React imports so it stays usable from
// anywhere, including before the app mounts.

export const THEME_STORAGE_KEY = "dhs-theme";

export const THEMES = ["light", "dark", "system"];

export const DEFAULT_THEME = "light";

export function readStoredTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return THEMES.includes(stored) ? stored : DEFAULT_THEME;
  } catch {
    // Private mode or a blocked storage partition. Fall back to the default
    // rather than failing the render.
    return DEFAULT_THEME;
  }
}

export function storeTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Persistence is best-effort; the in-memory theme still applies.
  }
}

export function prefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// "system" is only ever reached by explicit user choice, so following the OS
// here does not break the app's default of never auto-switching.
export function resolveTheme(theme) {
  return theme === "system" ? (prefersDark() ? "dark" : "light") : theme;
}

export function applyTheme(theme) {
  const resolved = resolveTheme(theme);
  document.documentElement.classList.toggle("dark", resolved === "dark");
  return resolved;
}
