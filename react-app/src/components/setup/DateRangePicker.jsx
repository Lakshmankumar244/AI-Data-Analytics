const QUICK_RANGES = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
  { id: "qtr", label: "This quarter" },
  { id: "fy", label: "This FY" },
  { id: "all", label: "All history" },
];

export default function DateRangePicker({ value, onChange }) {
  return (
    <div>
      <p className="eyebrow">Date range</p>
      <div className="field-row">
        {QUICK_RANGES.map((r) => (
          <button
            key={r.id}
            type="button"
            className="chip"
            aria-pressed={value.id === r.id}
            onClick={() => onChange({ id: r.id, from: null, to: null })}
          >
            {r.label}
          </button>
        ))}
      </div>
    </div>
  );
}
