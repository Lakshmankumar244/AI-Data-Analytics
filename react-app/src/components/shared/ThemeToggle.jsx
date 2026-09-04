import { Moon, Sun } from "lucide-react";
import { useTheme } from "../../theme/ThemeProvider";
import { cn } from "@/lib/utils";

export function ThemeToggle({ compact = false, className }) {
  const { resolvedTheme, toggleTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      className={cn("theme-toggle", compact && "theme-toggle-compact", className)}
      onClick={toggleTheme}
      aria-pressed={isDark}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
    >
      {isDark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
      {!compact && (
        <span className="theme-toggle-label">{isDark ? "Light" : "Dark"}</span>
      )}
    </button>
  );
}

export default ThemeToggle;
