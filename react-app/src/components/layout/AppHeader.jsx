import { Menu } from "lucide-react";
import { useAppState } from "../../state/AppContext";
import { ContentContainer } from "./ContentContainer";
import { Button } from "@/components/ui/button";

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
    <header className="flex min-h-[var(--app-header-height)] min-w-0 shrink-0 items-center bg-paper print:!hidden [@media(max-height:640px)]:min-h-11">
      <ContentContainer className="flex w-full flex-nowrap items-center justify-between gap-x-6 gap-y-3 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-3.5">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="hidden size-9 rounded-[var(--radius-md)] text-ink-soft hover:bg-surface-sunken hover:text-ink max-[760px]:inline-flex"
            onClick={() => setMobileOpen(true)}
            aria-expanded={Boolean(mobileOpen)}
            aria-controls="app-sidebar"
            aria-label="Open navigation"
          >
            <Menu size={18} aria-hidden="true" />
          </Button>
          <div className="min-w-0">
            <p className="eyebrow">{context.kicker}</p>
            <div className="mt-0.5 flex min-w-0 flex-wrap items-baseline gap-x-3">
              <p className="m-0 overflow-hidden text-ellipsis whitespace-nowrap font-heading text-base font-semibold leading-tight tracking-[-0.02em] text-ink max-[560px]:max-w-[46vw]">
                {context.title}
              </p>
              {meta && (
                <p className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] text-ink-muted max-[560px]:hidden">
                  {meta}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end">
          {account && (
            <div
              className="flex max-w-[min(280px,40cqi)] min-w-0 flex-col items-end gap-0.5 max-[760px]:hidden"
              title={[account.organization, account.user].filter(Boolean).join(" · ")}
            >
              {account.organization && (
                <span className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-medium text-ink">
                  {account.organization}
                </span>
              )}
              {account.user && (
                <span className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-ink-muted">
                  {account.user}
                </span>
              )}
            </div>
          )}
        </div>
      </ContentContainer>
    </header>
  );
}

export default AppHeader;
