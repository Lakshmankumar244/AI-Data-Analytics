import { Moon, Sun } from "lucide-react";
import { useTheme } from "../../theme/ThemeProvider";
import { cn } from "@/lib/utils";

export function ThemeToggle({ compact = false, className }) {
  const { resolvedTheme, toggleTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      className={cn(
        "inline-flex w-full min-h-10 items-center justify-start gap-3 rounded-[var(--radius-md)] border-0 bg-transparent px-2.5 py-2 text-[13px] font-medium text-ink-soft transition-[background-color,color] duration-[var(--duration-fast)] ease-[var(--ease-out)] hover:bg-surface-sunken hover:text-ink",
        "in-[.app-shell-collapsed]:justify-center in-[.app-shell-collapsed]:px-1.5",
        "max-[1180px]:justify-center max-[1180px]:px-1.5",
        "max-[760px]:!justify-start max-[760px]:!px-2.5",
        compact && "size-9 w-9 justify-center p-1.5",
        className
      )}
      onClick={toggleTheme}
      aria-pressed={isDark}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
    >
      {isDark ? (
        <Sun aria-hidden="true" className="size-4 shrink-0" />
      ) : (
        <Moon aria-hidden="true" className="size-4 shrink-0" />
      )}
      {!compact && (
        <span
          className={cn(
            "text-[13px] font-medium",
            "in-[.app-shell-collapsed]:hidden",
            "max-[1180px]:hidden",
            "max-[760px]:!inline"
          )}
        >
          {isDark ? "Light" : "Dark"}
        </span>
      )}
    </button>
  );
}

export default ThemeToggle;
