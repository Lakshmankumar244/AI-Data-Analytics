import { cn } from "@/lib/utils";

export default function OverviewEmptyNote({ children, fill = false }) {
  return (
    <div
      className={cn(
        "flex items-center py-3 text-left text-[13px] leading-relaxed text-ink-soft",
        fill ? "h-full min-h-0" : "min-h-12"
      )}
    >
      <p className="max-w-[46ch]">{children}</p>
    </div>
  );
}
