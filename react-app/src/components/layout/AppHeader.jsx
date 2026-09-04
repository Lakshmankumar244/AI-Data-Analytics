import { Menu } from "lucide-react";
import { useAppState } from "../../state/AppContext";
import { ContentContainer } from "./ContentContainer";
import { ThemeToggle } from "../shared/ThemeToggle";

const TAB_LABELS = {
  overview: "Overview",
  users: "Users",
  modules: "Modules",
  trend: "Trend",
  records: "Records",
  fix: "Fix",
};

function contextFor(phase, tab) {
  switch (phase) {
    case "boot":
      return { kicker: "Workspace", title: "Restoring session" };
    case "home":
      return { kicker: "Workspace", title: "Reports" };
    case "setup":
      return { kicker: "Scan", title: "Configure scan" };
    case "running":
      return { kicker: "Scan", title: "Scan in progress" };
    case "report":
      return { kicker: "Report", title: TAB_LABELS[tab] || "Overview" };
    case "error":
      return { kicker: "Workspace", title: "Needs attention" };
    default:
      return { kicker: "Workspace", title: "Data Health" };
  }
}

function connectionLabels(connection) {
  if (!connection || connection === "loading") return null;
  const organization =
    connection.organizationName || connection.organizationId || null;
  const user =
    connection.connectedUser?.name || connection.connectedUser?.email || null;
  if (!organization && !user) return null;
  return { organization, user };
}

function scanMeta(phase, scan, scanConfig) {
  if (phase !== "report" && phase !== "running") return null;
  const depth = String(scan?.reportContext?.depth || scanConfig?.depth || "")
    .trim();
  if (!depth) return null;
  return `${depth.charAt(0).toUpperCase()}${depth.slice(1)} scan`;
}

export function AppHeader({ mobileOpen, setMobileOpen }) {
  const { phase, tab, connection, scan, scanConfig } = useAppState();
  const context = contextFor(phase, tab);
  const account = connectionLabels(connection);
  const meta = scanMeta(phase, scan, scanConfig);

  return (
    <header className="app-header">
      <ContentContainer className="app-header-inner">
        <div className="app-header-lead">
          <button
            type="button"
            className="btn btn-ghost app-header-menu"
            onClick={() => setMobileOpen(true)}
            aria-expanded={Boolean(mobileOpen)}
            aria-controls="app-sidebar"
            aria-label="Open navigation"
          >
            <Menu size={18} aria-hidden="true" />
          </button>
          <div className="app-header-context">
            <p className="eyebrow app-header-kicker">{context.kicker}</p>
            <p className="app-header-title">{context.title}</p>
            {meta && <p className="app-header-meta">{meta}</p>}
          </div>
        </div>

        <div className="app-header-actions">
          {account && (
            <div className="app-header-org" title={[account.organization, account.user].filter(Boolean).join(" · ")}>
              {account.organization && (
                <span className="app-header-org-name">{account.organization}</span>
              )}
              {account.user && (
                <span className="app-header-org-user">{account.user}</span>
              )}
            </div>
          )}
          <ThemeToggle compact />
        </div>
      </ContentContainer>
    </header>
  );
}

export default AppHeader;
