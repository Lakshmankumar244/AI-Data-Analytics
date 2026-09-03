const DEPTHS = [
  { id: "quick", label: "Quick", cap: "1,000 / module", note: "Smoke test after a fix. Cheapest run." },
  { id: "presales", label: "Presales", cap: "5,000 / module", note: "Enough to produce a real picture." },
  { id: "deep", label: "Deep", cap: "20,000 / module", note: "Enough volume for plausibility checks." },
  { id: "full", label: "Full", cap: "Uncapped", note: "Everything in range." },
];

export default function DepthSelector({ value, onChange }) {
  return (
    <div>
      <p className="eyebrow">Scan depth</p>
      <div className="depth-grid">
        {DEPTHS.map((d) => (
          <button
            key={d.id}
            type="button"
            className={`depth-card ${value === d.id ? "depth-card-active" : ""}`}
            aria-pressed={value === d.id}
            onClick={() => onChange(d.id)}
          >
            <span className="depth-card-label">{d.label}</span>
            <span className="depth-card-cap mono">{d.cap}</span>
            <span className="depth-card-note">{d.note}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
