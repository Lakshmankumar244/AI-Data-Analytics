export default function ClockToggle({ value, onChange }) {
  return (
    <div>
      <p className="eyebrow">Clock</p>
      <div className="field-row" role="radiogroup" aria-label="Which timestamp to scope by">
        {["created", "modified"].map((id) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={value === id}
            className="chip"
            aria-pressed={value === id}
            onClick={() => onChange(id)}
          >
            {id === "created" ? "Created time" : "Modified time"}
          </button>
        ))}
      </div>
    </div>
  );
}
