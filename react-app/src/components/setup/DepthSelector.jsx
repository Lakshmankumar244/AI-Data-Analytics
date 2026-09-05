import { cn } from "@/lib/utils";

const DEPTHS = [
  { id: "quick", label: "Quick", cap: "1,000 / module", note: "Smoke test after a fix. Cheapest run." },
  { id: "presales", label: "Presales", cap: "5,000 / module", note: "Enough to produce a real picture." },
  { id: "deep", label: "Deep", cap: "20,000 / module", note: "Enough volume for plausibility checks." },
  { id: "full", label: "Full", cap: "Uncapped", note: "Everything in range." },
];

export default function DepthSelector({ value, onChange }) {
  const selected = DEPTHS.find((depth) => depth.id === value) ?? DEPTHS[1];
  return (
    <div className="min-w-0">
      <p className="eyebrow">Scan depth</p>
      <div
        className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4"
        role="radiogroup"
        aria-label="Scan depth"
      >
        {DEPTHS.map((depth) => {
          const pressed = depth.id === value;
          return (
            <button
              key={depth.id}
              type="button"
              role="radio"
              aria-checked={pressed}
              className={cn(
                "flex min-w-0 flex-col items-start gap-0.5 border-b-2 py-2.5 text-left transition-colors",
                pressed
                  ? "border-brand text-ink"
                  : "border-transparent text-ink-muted hover:border-line-strong hover:text-ink"
              )}
              onClick={() => onChange(depth.id)}
            >
              <span className="font-heading text-[15px] font-semibold tracking-tight">
                {depth.label}
              </span>
              <span className="mono text-[11px] text-ink-muted">{depth.cap}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-3 text-[13px] text-ink-soft">{selected.note}</p>
    </div>
  );
}
