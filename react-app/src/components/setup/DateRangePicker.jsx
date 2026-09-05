import { formatReportPeriod } from "../../utils/format";
import { cn } from "@/lib/utils";

export const QUICK_RANGES = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
  { id: "qtr", label: "This quarter" },
  { id: "fy", label: "This FY" },
  { id: "all", label: "All history" },
];

export const RANGE_LABELS = Object.fromEntries(
  QUICK_RANGES.map((range) => [range.id, range.label])
);

function toDateInputValue(value) {
  if (!value) return "";
  const match = String(value).match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
}

function fromDateInputValue(value) {
  return value ? `${value}T00:00:00.000Z` : null;
}

export function DateRangePresets({ value, onChange }) {
  const options = [...QUICK_RANGES, { id: "custom", label: "Custom" }];
  return (
    <div className="min-w-0">
      <p className="eyebrow">Period</p>
      <div
        className="mt-3 flex flex-wrap gap-x-5 gap-y-1"
        role="radiogroup"
        aria-label="Date range presets"
      >
        {options.map((range) => {
          const pressed = value.id === range.id;
          return (
            <button
              key={range.id}
              type="button"
              role="radio"
              aria-checked={pressed}
              className={cn(
                "border-b-2 py-2 text-[15px] font-semibold tracking-tight transition-colors",
                pressed
                  ? "border-brand text-ink"
                  : "border-transparent text-ink-muted hover:border-line-strong hover:text-ink"
              )}
              onClick={() =>
                onChange(
                  range.id === "custom"
                    ? { id: "custom", from: value.from, to: value.to }
                    : { id: range.id, from: null, to: null }
                )
              }
            >
              {range.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function DateRangeField({ value, onChange }) {
  const isCustom = value.id === "custom";
  const presetLabel = RANGE_LABELS[value.id];
  const resolvedPeriod = formatReportPeriod(value.from, value.to);

  function updateBound(bound, nextValue) {
    onChange({
      id: "custom",
      from: bound === "from" ? fromDateInputValue(nextValue) : value.from,
      to: bound === "to" ? fromDateInputValue(nextValue) : value.to,
    });
  }

  if (!isCustom) return null;

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <input
        type="date"
        className="min-h-10 min-w-0 flex-1 basis-[140px] border-0 border-b border-line-strong bg-transparent px-0 py-2 text-[13px] font-medium text-ink"
        aria-label="Range start"
        value={toDateInputValue(value.from)}
        onChange={(event) => updateBound("from", event.target.value)}
      />
      <span className="text-xs text-ink-muted" aria-hidden="true">
        to
      </span>
      <input
        type="date"
        className="min-h-10 min-w-0 flex-1 basis-[140px] border-0 border-b border-line-strong bg-transparent px-0 py-2 text-[13px] font-medium text-ink"
        aria-label="Range end"
        value={toDateInputValue(value.to)}
        onChange={(event) => updateBound("to", event.target.value)}
      />
      {resolvedPeriod && (
        <span className="sr-only">{resolvedPeriod || presetLabel}</span>
      )}
    </div>
  );
}

export default function DateRangePicker({ value, onChange }) {
  return (
    <div>
      <DateRangePresets value={value} onChange={onChange} />
      <DateRangeField value={value} onChange={onChange} />
    </div>
  );
}
