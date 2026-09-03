import "./TabNav.css";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "users", label: "Users" },
  { id: "modules", label: "Modules" },
  { id: "trend", label: "Trend" },
  { id: "records", label: "Records" },
  { id: "fix", label: "Fix" },
];

// Each tab resolves to a report component in ReportShell.
export default function TabNav({ active, onChange }) {
  return (
    <nav className="tab-nav" aria-label="Report sections">
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`tab-nav-item${active === t.id ? " tab-nav-item-active" : ""}`}
          onClick={() => onChange(t.id)}
          aria-current={active === t.id ? "page" : undefined}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
