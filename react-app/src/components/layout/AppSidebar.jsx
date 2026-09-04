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
        className={`app-sidebar-item${current ? " app-sidebar-item-current" : ""}`}
        aria-current={current ? "page" : undefined}
        disabled={disabled}
        onClick={onClick}
      >
        <span className="app-sidebar-icon" aria-hidden="true">
          <Icon strokeWidth={1.75} />
        </span>
        <span className="app-sidebar-label">{label}</span>
        {current && <span className="app-sidebar-item-current-dot" aria-hidden="true" />}
        <span className="app-sidebar-tooltip" aria-hidden="true">
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
          className="app-nav-backdrop"
          aria-label="Close navigation"
          onClick={closeMobile}
        />
      )}

      <nav
        id="app-sidebar"
        className="app-sidebar"
        aria-label="Application"
      >
        <div className="app-sidebar-brand">
          <span className="app-mark" aria-hidden="true">
            DH
          </span>
          <div className="app-sidebar-brand-text">
            <span className="app-sidebar-product">Data Health</span>
            <span className="app-sidebar-product-sub">Scanner</span>
          </div>
          <button
            type="button"
            className="btn btn-ghost app-sidebar-close"
            onClick={closeMobile}
            aria-label="Close navigation"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="app-sidebar-section">
          <p className="app-sidebar-heading">Workspace</p>
          <ul className="app-sidebar-list">
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
                label="Scanning"
                current
                disabled
              />
            )}
          </ul>
        </div>

        {phase === "report" && (
          <div className="app-sidebar-section">
            <p className="app-sidebar-heading">Investigate</p>
            <ul className="app-sidebar-list">
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

        <div className="app-sidebar-spacer" />

        <div className="app-sidebar-footer">
          <ThemeToggle />
          <button
            type="button"
            className="app-sidebar-collapse"
            onClick={() => setCollapsed(!collapsed)}
            aria-pressed={collapsed}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            <span className="app-sidebar-icon" aria-hidden="true">
              {collapsed ? (
                <PanelLeft strokeWidth={1.75} />
              ) : (
                <PanelLeftClose strokeWidth={1.75} />
              )}
            </span>
            <span className="app-sidebar-collapse-label">
              {collapsed ? "Expand" : "Collapse"}
            </span>
          </button>
        </div>
      </nav>
    </>
  );
}

export default AppSidebar;
