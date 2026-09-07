import { cn } from "@/lib/utils";

function initials(name) {
  const parts = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export default function UserIdentity({ name, modules = [] }) {
  const unassigned = name === "Unassigned" || name === "Unknown owner";

  return (
    <div className="flex min-w-0 items-start gap-3">
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-full font-heading text-[11px] font-semibold tracking-wide",
          unassigned
            ? "bg-surface-sunken text-ink-muted"
            : "bg-brand-soft text-brand-strong"
        )}
        aria-hidden="true"
      >
        {initials(name)}
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <strong className="font-heading text-[15px] leading-snug font-semibold tracking-tight text-ink [overflow-wrap:anywhere]">
          {name}
        </strong>
        {modules.length > 0 && (
          <p className="m-0 text-[12px] leading-snug text-ink-muted [overflow-wrap:anywhere]">
            {modules.join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}
