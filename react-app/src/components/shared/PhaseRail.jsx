import "./PhaseRail.css";

const STEPS = [
  { id: "connect", label: "Connect" },
  { id: "scope", label: "Scope" },
  { id: "scan", label: "Scan" },
  { id: "result", label: "Result" },
];

// This is a genuine sequence - you cannot scope before connecting, or see a
// result before scanning - so numbering it is informative, not decorative.
function stepIndexForPhase(phase) {
  switch (phase) {
    case "home":
      return 1;
    case "setup":
      return 1; // connect assumed complete once a connection fixture is loaded
    case "running":
      return 2;
    case "report":
      return 3;
    default:
      return 0;
  }
}

export default function PhaseRail({ phase }) {
  const activeIndex = stepIndexForPhase(phase);

  return (
    <nav className="phase-rail" aria-label="Scan progress">
      <div className="phase-rail-mark">
        <span className="phase-rail-mark-glyph">DH</span>
      </div>
      <ol>
        {STEPS.map((step, i) => {
          const state = i < activeIndex ? "done" : i === activeIndex ? "active" : "upcoming";
          return (
            <li key={step.id} className={`phase-step phase-step-${state}`}>
              <span className="phase-step-index mono">{String(i + 1).padStart(2, "0")}</span>
              <span className="phase-step-label">{step.label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
