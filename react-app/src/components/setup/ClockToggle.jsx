import { cn } from "@/lib/utils";

const CLOCK_OPTIONS = [
  { id: "created", label: "Created time" },
  { id: "modified", label: "Modified time" },
];

export default function ClockToggle({ value, onChange }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">Clock</p>
      <div
        className="mt-3 flex gap-6"
        role="radiogroup"
        aria-label="Clock"
      >
        {CLOCK_OPTIONS.map((option) => {
          const pressed = option.id === value;
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={pressed}
              className={cn(
                "border-b-2 py-2 text-[15px] font-semibold tracking-tight transition-colors",
                pressed
                  ? "border-brand text-ink"
                  : "border-transparent text-ink-muted hover:border-line-strong hover:text-ink"
              )}
              onClick={() => onChange(option.id)}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
