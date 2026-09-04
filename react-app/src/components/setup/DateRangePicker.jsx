import { formatReportPeriod } from "../../utils/format";

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
  return (
    <div className="field-row" role="group" aria-label="Date range presets">
      {QUICK_RANGES.map((range) => (
        <button
          key={range.id}
          type="button"
          className="chip"
          aria-pressed={value.id === range.id}
          onClick={() => onChange({ id: range.id, from: null, to: null })}
        >
          {range.label}
        </button>
      ))}
      <button
        type="button"
        className="chip"
        aria-pressed={value.id === "custom"}
        onClick={() => onChange({ id: "custom", from: value.from, to: value.to })}
      >
        Custom
      </button>
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

  return (
    <div className="setup-field">
      <p className="eyebrow">Date range</p>
      {isCustom ? (
        <div className="setup-date-inputs">
          <input
            type="date"
            className="setup-field-control"
            aria-label="Range start"
            value={toDateInputValue(value.from)}
            onChange={(event) => updateBound("from", event.target.value)}
          />
          <span className="setup-date-inputs-sep" aria-hidden="true">
            to
          </span>
          <input
            type="date"
            className="setup-field-control"
            aria-label="Range end"
            value={toDateInputValue(value.to)}
            onChange={(event) => updateBound("to", event.target.value)}
          />
        </div>
      ) : (
        <div className="setup-field-control setup-field-control-readonly">
          {resolvedPeriod || presetLabel || "\u2014"}
        </div>
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
