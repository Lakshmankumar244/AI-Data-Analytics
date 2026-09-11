import { cn } from "@/lib/utils";

function Toast({ open, children, className }) {
  if (!open) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-slot="toast"
      className={cn(
        "pointer-events-none fixed top-6 left-1/2 z-[80] -translate-x-1/2 rounded-md border border-line bg-surface px-4 py-2.5 text-[13px] text-ink shadow-lg duration-150 animate-in fade-in-0 zoom-in-95",
        className
      )}
    >
      {children}
    </div>
  );
}

export { Toast };
