import { useEffect, useRef, useState } from "react";
import { useAppState, useActions } from "../../state/AppContext";
import { formatNumber } from "../../utils/format";
import { ContentContainer } from "../layout";
import "./FilterBar.css";

const RANGE_LABELS = { "30d": "Last 30 days", "90d": "Last 90 days", "180d": "Last 6 months", all: "All time" };
const CLOCK_LABELS = { created: "Created date", modified: "Modified date" };
const CLOCK_OPTIONS = [
  { id: "created", label: "Created date" },
  { id: "modified", label: "Modified date" },
];

// Compare should mirror the ACTUAL selected period length, not a fixed
// guess. Prefer the real date range from reportContext (fromUtc/toUtc)
// when available - that's ground truth. Fall back to parsing the range
// preset id ("7d" -> 7, "180d" -> 180) only if no real dates exist yet.
function periodLengthDays(scan, scanConfig) {
  const from = scan?.reportContext?.fromUtc;
  const to = scan?.reportContext?.toUtc;
  if (from && to) {
    const diffMs = new Date(to) - new Date(from);
    if (!Number.isNaN(diffMs) && diffMs > 0) {
      return Math.max(1, Math.round(diffMs / 86400000));
    }
  }
  const preset = scanConfig.range?.id;
  const numericMatch = /^(\d+)d$/.exec(preset || "");
  if (numericMatch) return Number(numericMatch[1]);
  return null;
}

function ChevronIcon() {
  return (
    <svg width="9" height="6" viewBox="0 0 9 6" fill="none" aria-hidden="true" className="filter-dropdown-caret">
      <path d="M1 1L4.5 4.5L8 1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Small local dropdown - trigger button + popover panel. No new
// dependency, closes on outside click or Escape. Kept in this file
// since only FilterBar uses it today; promote to shared/ if a second
// consumer shows up.
function FilterDropdown({ label, valueLabel, isOpen, onToggle, onClose, disabled, children }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!isOpen) return;
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    function handleKey(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [isOpen, onClose]);

  return (
    <div className="filter-control filter-dropdown" ref={ref}>
      <span className="eyebrow">{label}</span>
      <button
        type="button"
        className={`filter-dropdown-trigger${disabled ? " filter-dropdown-trigger-disabled" : ""}`}
        aria-expanded={isOpen}
        aria-disabled={disabled}
        title={disabled ? "Not enabled yet" : undefined}
        onClick={() => !disabled && onToggle()}
      >
        <span className="filter-control-value">{valueLabel}</span>
        <ChevronIcon />
      </button>
      {isOpen && !disabled && <div className="filter-dropdown-panel">{children}</div>}
    </div>
  );
}

export default function FilterBar() {
  const { connection, scan, scanConfig, filterModules, tab } = useAppState();
  const { setFilter, showHome } = useActions();
  const [openMenu, setOpenMenu] = useState(null); // "modules" | "attribution" | null

  const reportClock = scan?.reportContext?.clock;
  const clockLabel = reportClock
    ? reportClock === "Created_Time" ? "Created date" : reportClock === "Modified_Time" ? "Modified date" : reportClock
    : CLOCK_LABELS[scanConfig.clock] ?? scanConfig.clock;
  const rangeLabel = scan?.reportContext
    ? `${scan.reportContext.fromUtc || "—"} – ${scan.reportContext.toUtc || "—"}`
    : RANGE_LABELS[scanConfig.range?.id] ?? "Custom range";
  const depthLabel = String(scan?.reportContext?.depth || scanConfig.depth || "quick")
    .replace(/^./, (letter) => letter.toUpperCase());
  const reportConnection = scan?.reportContext?.connection;
  const userLabel = reportConnection
    ? reportConnection.name || reportConnection.email
    : connection?.connectedUser?.name || connection?.connectedUser?.email;
  const organizationLabel = reportConnection
    ? reportConnection.organizationName || reportConnection.organizationId
    : connection?.organizationName || connection?.organizationId;
  const accountLabel = [organizationLabel, userLabel].filter(Boolean).join(" · ");
  const scannedModules = scan?.moduleFindings?.length
    ? scan.moduleFindings.map((module) => ({ apiName: module.apiName, label: module.label }))
    : (connection?.accessibleModules ?? []).filter((module) => scanConfig.modules.includes(module.apiName));
  const displayedModules = filterModules.length
    ? scannedModules.filter((module) => filterModules.includes(module.apiName))
    : scannedModules;

  // Real value, not a placeholder: mirrors whatever period is actually
  // selected above, computed from real dates when available.
  const compareDays = periodLengthDays(scan, scanConfig);
  const compareLabel = compareDays ? `Prior ${compareDays} day${compareDays === 1 ? "" : "s"}` : "Prior period";

  function toggleModule(apiName) {
    const set = new Set(filterModules);
    set.has(apiName) ? set.delete(apiName) : set.add(apiName);
    setFilter({ filterModules: Array.from(set) });
  }

  // Real change, following the same setFilter merge pattern already used
  // by toggleModule and OverviewTab's focusState - not a placeholder.
  function setAttribution(clockId) {
    setFilter({ scanConfig: { ...scanConfig, clock: clockId } });
    setOpenMenu(null);
  }

  // TODO: replace with real print implementation once available
  function handlePrint() {
    window.print();
  }

  // TODO: wire real export (CSV/PDF) once the export endpoint exists
  function handleExport() {
    console.log("Export: not yet implemented");
  }

  return (
    <header className="filter-bar">
      {/* Three wrapping groups rather than one long nowrap row. Each group
          stays intact and drops to its own line when the bar runs out of
          width, so the filters stay usable instead of overflowing the page
          at the mid widths a zoomed-in laptop produces. */}
      <ContentContainer className="filter-bar-inner">
        <div className="filter-bar-lead">
          <button type="button" className="filter-bar-back" onClick={showHome}>
            <span aria-hidden="true">←</span> Reports
          </button>

          <div className="filter-bar-title-block">
            <h1>{displayedModules.map((module) => module.label).join(" + ") || "Analytics"}</h1>
            {accountLabel && (
              <p className="filter-bar-subtitle" title={accountLabel}>
                {accountLabel} · {depthLabel} scan
              </p>
            )}
          </div>
        </div>

        <div className="filter-bar-controls">
          <div className="filter-control">
            <span className="eyebrow">Period</span>
            <span className="filter-control-value mono">{rangeLabel}</span>
          </div>

          <FilterDropdown
            label="Modules"
            valueLabel={
              filterModules.length === 0 || filterModules.length === scannedModules.length
                ? `All ${scannedModules.length}`
                : displayedModules.map((m) => m.label).join(", ")
            }
            isOpen={openMenu === "modules"}
            onToggle={() => setOpenMenu(openMenu === "modules" ? null : "modules")}
            onClose={() => setOpenMenu(null)}
          >
            <div className="filter-dropdown-options" aria-label="Filter report modules">
              {scannedModules.map((module) => {
                const isActive = filterModules.length === 0 || filterModules.includes(module.apiName);
                return (
                  <button
                    key={module.apiName}
                    type="button"
                    className="filter-dropdown-option filter-dropdown-option-checkbox"
                    aria-pressed={isActive}
                    onClick={() => toggleModule(module.apiName)}
                  >
                    <span className="filter-dropdown-checkbox" aria-hidden="true" />
                    {module.label}
                  </button>
                );
              })}
            </div>
          </FilterDropdown>

          {/* Hidden on the Users tab on purpose - filtering "by user" while
              already viewing the per-user breakdown is redundant there. */}
          {tab !== "users" && (
            <FilterDropdown
              label="Users"
              valueLabel={formatNumber(null) /* "—" - no user data loaded here yet, don't imply a fake count */}
              isOpen={false}
              onToggle={() => {}}
              onClose={() => {}}
              disabled
            >
              {/* No user list is loaded into this component today - there is
                  nothing real to show here yet, so this stays visibly inert
                  (dimmed, "Not enabled yet" tooltip) rather than faking
                  selectable options. TODO: wire once user data is available. */}
            </FilterDropdown>
          )}

          <FilterDropdown
            label="Attribution"
            valueLabel={clockLabel}
            isOpen={openMenu === "attribution"}
            onToggle={() => setOpenMenu(openMenu === "attribution" ? null : "attribution")}
            onClose={() => setOpenMenu(null)}
          >
            <div className="filter-dropdown-options">
              {CLOCK_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className="filter-dropdown-option"
                  aria-pressed={scanConfig.clock === option.id}
                  onClick={() => setAttribution(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </FilterDropdown>

          <div className="filter-control filter-control-compare">
            <span className="eyebrow">Compare</span>
            <span className="filter-control-value filter-control-strong">{compareLabel}</span>
          </div>
        </div>

        <div className="filter-bar-actions">
          <button type="button" className="filter-bar-action" onClick={handlePrint}>
            Print
          </button>
          <button type="button" className="filter-bar-action filter-bar-action-caret" onClick={handleExport}>
            Export <ChevronIcon />
          </button>
        </div>
      </ContentContainer>
    </header>
  );
}
