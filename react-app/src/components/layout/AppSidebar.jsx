import {
  Activity,
  Boxes,
  Inbox,
  LayoutDashboard,
  PanelLeft,
  PanelLeftClose,
  ScanSearch,
  Table2,
  TrendingUp,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { useAppState, useActions } from "../../state/AppContext";
import { ThemeToggle } from "../shared/ThemeToggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const WORKSPACE_ITEMS = [
  { id: "home", phase: "home", label: "Reports", icon: Inbox, action: "showHome" },
  { id: "setup", phase: "setup", label: "New scan", icon: ScanSearch, action: "showSetup" },
];

const REPORT_ITEMS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "users", label: "Users", icon: Users },
  { id: "modules", label: "Modules", icon: Boxes },
  { id: "trend", label: "Trend", icon: TrendingUp },
  { id: "records", label: "Records", icon: Table2 },
  { id: "fix", label: "Fix", icon: Wrench },
];

const compactClip =
  "group-[.app-shell-collapsed]/shell:sr-only max-[1180px]:sr-only max-[760px]:!not-sr-only";
const compactHideHeading =
  "group-[.app-shell-collapsed]/shell:hidden max-[1180px]:hidden max-[760px]:!block";
const compactCenter =
  "group-[.app-shell-collapsed]/shell:justify-center group-[.app-shell-collapsed]/shell:px-1.5 max-[1180px]:justify-center max-[1180px]:px-1.5 max-[760px]:!justify-start max-[760px]:!px-2.5";

function SidebarItem({
  icon: Icon,
  label,
  current,
  onClick,
  disabled,
}) {
  return (
    <li>
      <button
        type="button"
        className={cn(
          "group/item relative flex w-full min-h-10 items-center gap-3 rounded-[var(--radius-md)] border-0 bg-transparent px-2.5 py-2 text-left text-[13px] font-medium text-ink-soft transition-[background-color,color] duration-[var(--duration-fast)] ease-[var(--ease-out)] hover:bg-surface-sunken hover:text-ink disabled:cursor-default",
          compactCenter,
          current &&
            "bg-[color-mix(in_srgb,var(--brand-soft)_80%,transparent)] font-semibold text-brand-strong hover:bg-[color-mix(in_srgb,var(--brand-soft)_80%,transparent)] hover:text-brand-strong before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:bg-brand"
        )}
        aria-current={current ? "page" : undefined}
        disabled={disabled}
        onClick={onClick}
      >
        <span className="grid size-5 shrink-0 place-items-center text-inherit" aria-hidden="true">
          <Icon className="size-4" strokeWidth={1.75} />
        </span>
        <span className={cn("min-w-0 truncate", compactClip)}>{label}</span>
        <span
          className={cn(
            "pointer-events-none absolute top-1/2 left-[calc(100%+12px)] z-50 -translate-y-1/2 rounded-[var(--radius-md)] bg-ink px-2.5 py-1.5 text-xs font-medium whitespace-nowrap text-surface opacity-0 invisible shadow-[var(--shadow-float)] group-hover/item:opacity-100 group-hover/item:visible group-focus-visible/item:opacity-100 group-focus-visible/item:visible",
            "hidden group-[.app-shell-collapsed]/shell:block max-[1180px]:block max-[760px]:!hidden"
          )}
          aria-hidden="true"
        >
          {label}
        </span>
      </button>
    </li>
  );
}

export function AppSidebar({
  collapsed,
  setCollapsed,
  mobileOpen,
  setMobileOpen,
}) {
  const { phase, tab } = useAppState();
  const { showHome, showSetup, setTab } = useActions();
  const closeMobile = () => setMobileOpen(false);

  function go(action) {
    action();
    closeMobile();
  }

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          className="hidden border-0 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-0 backdrop-blur-[2px] max-[760px]:fixed max-[760px]:inset-0 max-[760px]:z-[45] max-[760px]:block print:hidden"
          aria-label="Close navigation"
          onClick={closeMobile}
        />
      )}

      <nav
        id="app-sidebar"
        className={cn(
          "relative z-40 flex h-full min-w-0 w-[var(--app-rail-width)] flex-[0_0_var(--app-rail-width)] flex-col overflow-x-hidden overflow-y-auto overscroll-contain border-r border-[color-mix(in_srgb,var(--line)_72%,transparent)] bg-surface px-3.5 py-5",
          "group-[.app-shell-collapsed]/shell:px-2.5",
          "max-[1180px]:items-stretch max-[1180px]:px-2.5",
          "max-[760px]:fixed max-[760px]:inset-y-0 max-[760px]:left-0 max-[760px]:z-50 max-[760px]:!w-[min(248px,88vw)] max-[760px]:basis-[248px] max-[760px]:items-stretch max-[760px]:!px-4 max-[760px]:!py-5 max-[760px]:shadow-none max-[760px]:-translate-x-[105%] max-[760px]:invisible max-[760px]:pointer-events-none max-[760px]:transition-transform max-[760px]:duration-[var(--duration-med)] max-[760px]:ease-[var(--ease-out)]",
          "max-[760px]:in-[.app-shell-nav-open]:!translate-x-0 max-[760px]:in-[.app-shell-nav-open]:!visible max-[760px]:in-[.app-shell-nav-open]:!pointer-events-auto max-[760px]:in-[.app-shell-nav-open]:shadow-[var(--shadow-float)]",
          "motion-reduce:transition-none print:!hidden"
        )}
        aria-label="Application"
      >
        <div
          className={cn(
            "mb-7 flex min-w-0 items-center gap-3 px-1",
            "group-[.app-shell-collapsed]/shell:justify-center group-[.app-shell-collapsed]/shell:p-0",
            "max-[1180px]:justify-center max-[1180px]:p-0"
          )}
        >
          <span
            className="grid size-8 shrink-0 place-items-center rounded-[var(--radius-md)] bg-brand font-mono text-[11px] font-semibold tracking-[0.06em] text-on-brand"
            aria-hidden="true"
          >
            DH
          </span>
          <div className={cn("flex min-w-0 flex-1 flex-col gap-0.5 leading-tight", compactClip)}>
            <span className="font-heading text-[15px] font-semibold tracking-[-0.02em] text-ink">
              Data Health
            </span>
            <span className="text-[11px] font-medium text-ink-muted">Scanner</span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="ml-auto hidden size-8 text-ink-soft hover:bg-surface-sunken hover:text-ink max-[760px]:inline-flex"
            onClick={closeMobile}
            aria-label="Close navigation"
          >
            <X size={16} aria-hidden="true" />
          </Button>
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <p
            className={cn(
              "mx-2.5 mb-1 text-[11px] font-semibold tracking-[0.08em] text-ink-muted uppercase",
              compactHideHeading
            )}
          >
            Workspace
          </p>
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
            {WORKSPACE_ITEMS.map((item) => (
              <SidebarItem
                key={item.id}
                icon={item.icon}
                label={item.label}
                current={phase === item.phase}
                onClick={() => go(item.action === "showHome" ? showHome : showSetup)}
              />
            ))}
            {phase === "running" && (
              <SidebarItem
                icon={Activity}
                label="Scan status"
                current
                disabled
              />
            )}
          </ul>
        </div>

        {phase === "report" && (
          <div className="mt-8 flex min-w-0 flex-col gap-1.5">
            <p
              className={cn(
                "mx-2.5 mb-1 text-[11px] font-semibold tracking-[0.08em] text-ink-muted uppercase",
                compactHideHeading
              )}
            >
              Investigate
            </p>
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
              {REPORT_ITEMS.map((item) => (
                <SidebarItem
                  key={item.id}
                  icon={item.icon}
                  label={item.label}
                  current={tab === item.id}
                  onClick={() => go(() => setTab(item.id))}
                />
              ))}
            </ul>
          </div>
        )}

        <div className="min-h-5 flex-1" />

        <div className="flex flex-col gap-0.5 pt-4 shadow-[inset_0_1px_0_0_color-mix(in_srgb,var(--line)_65%,transparent)]">
          <ThemeToggle />
          <button
            type="button"
            className={cn(
              "inline-flex w-full min-h-10 items-center gap-3 rounded-[var(--radius-md)] border-0 bg-transparent px-2.5 py-2 text-[13px] font-medium text-ink-soft transition-[background-color,color] duration-[var(--duration-fast)] ease-[var(--ease-out)] hover:bg-surface-sunken hover:text-ink max-[1180px]:hidden",
              compactCenter
            )}
            onClick={() => setCollapsed(!collapsed)}
            aria-pressed={collapsed}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            <span className="grid size-5 shrink-0 place-items-center" aria-hidden="true">
              {collapsed ? (
                <PanelLeft className="size-4" strokeWidth={1.75} />
              ) : (
                <PanelLeftClose className="size-4" strokeWidth={1.75} />
              )}
            </span>
            <span className={compactClip}>
              {collapsed ? "Expand" : "Collapse"}
            </span>
          </button>
        </div>
      </nav>
    </>
  );
}

export default AppSidebar;
