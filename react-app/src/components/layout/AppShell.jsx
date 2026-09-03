import { cn } from "@/lib/utils";

/*
  The outermost frame: a two column grid of [navigation rail | main column].

  The rail is passed in rather than imported so the shell stays a layout
  component - it does not need to know what a phase is.
*/
export function AppShell({ rail, className, children, ...props }) {
  return (
    <div className={cn("app-shell", className)} {...props}>
      {rail}
      {children}
    </div>
  );
}

/*
  The main column. Everything measured "against the app" is measured against
  this element: it carries the container context that `--app-gutter` and the
  fluid clamps resolve against, and it is the boundary that stops horizontal
  overflow from reaching the page.
*/
export function MainContent({ className, children, ...props }) {
  return (
    <main className={cn("app-main", className)} {...props}>
      {children}
    </main>
  );
}

export default AppShell;
