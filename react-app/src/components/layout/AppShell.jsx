import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { AppSidebar } from "./AppSidebar";
import { AppHeader } from "./AppHeader";

const COLLAPSE_KEY = "dhs-nav-collapsed";

function readCollapsed() {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function persistCollapsed(collapsed) {
  try {
    window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
  } catch {
    // Persistence is best-effort.
  }
}

/*
  Viewport chrome: sidebar + header + scrolling main column.

  The rail used to be a slotted progress widget. The shell now owns the
  product navigation so every screen sits inside one consistent frame.

  `app-shell-collapsed` / `app-shell-nav-open` stay as class hooks: ThemeToggle
  and the rail query them, and they override `--app-rail-width` for descendants.
*/
export function AppShell({ className, children, ...props }) {
  const [collapsed, setCollapsedState] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);

  const setCollapsed = useCallback((next) => {
    setCollapsedState(next);
    persistCollapsed(next);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setMobileOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  return (
    <div
      className={cn(
        "app-shell group/shell flex h-[100vh] supports-[height:100dvh]:h-[100dvh] min-w-0 items-stretch bg-paper print:h-auto print:overflow-visible",
        collapsed && "app-shell-collapsed",
        collapsed && "[--app-rail-width:var(--app-rail-collapsed)]",
        mobileOpen && "app-shell-nav-open",
        "max-[1180px]:[--app-rail-width:var(--app-rail-collapsed)]",
        "max-[760px]:![--app-rail-width:0px]",
        className
      )}
      {...props}
    >
      <a href="#app-main" className="skip-link">
        Skip to content
      </a>
      <AppSidebar
        collapsed={collapsed}
        setCollapsed={setCollapsed}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
      />
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col print:h-auto print:overflow-visible"
        inert={mobileOpen || undefined}
      >
        <AppHeader mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        {children}
      </div>
    </div>
  );
}

/*
  The main column. Everything measured "against the app" is measured against
  this element: it carries the container context that `--app-gutter` and the
  fluid clamps resolve against, and it is the boundary that stops overflow
  from reaching the page.
*/
export function MainContent({ className, children, ...props }) {
  return (
    <main
      id="app-main"
      className={cn(
        "@container/app-main flex min-h-0 min-w-0 flex-1 flex-col overflow-x-clip overflow-y-auto overscroll-contain print:h-auto print:overflow-visible",
        className
      )}
      tabIndex={-1}
      {...props}
    >
      {children}
    </main>
  );
}

export default AppShell;
