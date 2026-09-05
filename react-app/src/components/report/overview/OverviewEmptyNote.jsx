import { cn } from "@/lib/utils";

export default function OverviewEmptyNote({ children, fill = false }) {
  return (
    <div
      className={cn(
        "flex items-center bg-surface-sunken px-4 py-3 text-left text-[13px] leading-normal text-ink-soft",
        fill ? "h-full min-h-0" : "min-h-16"
      )}
    >
      <p className="max-w-[46ch]">{children}</p>
    </div>
  );
}
