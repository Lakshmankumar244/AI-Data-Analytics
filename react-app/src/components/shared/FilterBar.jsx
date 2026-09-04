import { useEffect, useRef, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { useAppState, useActions } from "../../state/AppContext";
import { formatNumber, formatReportPeriod } from "../../utils/format";
import { ContentContainer } from "../layout";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
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

function useReportFilters() {
  const { connection, scan, scanConfig, filterModules, tab } = useAppState();
  const { setFilter } = useActions();
  const [openMenu, setOpenMenu] = useState(null);

  const reportClock = scan?.reportContext?.clock;
  const clockLabel = reportClock
    ? reportClock === "Created_Time" ? "Created date" : reportClock === "Modified_Time" ? "Modified date" : reportClock
    : CLOCK_LABELS[scanConfig.clock] ?? scanConfig.clock;
  const rangeLabel = scan?.reportContext
    ? formatReportPeriod(scan.reportContext.fromUtc, scan.reportContext.toUtc) ?? "—"
    : RANGE_LABELS[scanConfig.range?.id] ?? "Custom range";
  const rangeLabelCompact = scan?.reportContext
    ? formatReportPeriod(scan.reportContext.fromUtc, scan.reportContext.toUtc, {
        compact: true,
      }) ?? rangeLabel
    : rangeLabel;
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
  const modulesValueLabel =
    filterModules.length === 0 || filterModules.length === scannedModules.length
      ? `All ${scannedModules.length}`
      : displayedModules.map((module) => module.label).join(", ");

  const compareDays = periodLengthDays(scan, scanConfig);
  const compareLabel = compareDays ? `Prior ${compareDays} day${compareDays === 1 ? "" : "s"}` : "Prior period";
  const showUsers = tab !== "users";
  const filterCount = 4 + (showUsers ? 1 : 0);

  function toggleModule(apiName) {
    const set = new Set(filterModules);
    set.has(apiName) ? set.delete(apiName) : set.add(apiName);
    setFilter({ filterModules: Array.from(set) });
  }

  function setAttribution(clockId) {
    setFilter({ scanConfig: { ...scanConfig, clock: clockId } });
    setOpenMenu(null);
  }

  return {
    openMenu,
    setOpenMenu,
    clockLabel,
    rangeLabel,
    rangeLabelCompact,
    depthLabel,
    accountLabel,
    scannedModules,
    displayedModules,
    modulesValueLabel,
    compareLabel,
    showUsers,
    filterCount,
    filterModules,
    scanConfig,
    toggleModule,
    setAttribution,
  };
}

function ModuleOptions({ scannedModules, filterModules, toggleModule }) {
  return (
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
  );
}

function AttributionOptions({ scanConfig, setAttribution }) {
  return (
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
  );
}

function FilterCommand({
  variant,
  rangeLabel,
  rangeLabelCompact,
  modulesValueLabel,
  clockLabel,
  compareLabel,
  showUsers,
  openMenu,
  setOpenMenu,
  scannedModules,
  filterModules,
  toggleModule,
  scanConfig,
  setAttribution,
}) {
  const isSheet = variant === "sheet";

  return (
    <div
      className={`filter-command filter-command-${variant}${
        !isSheet && !showUsers ? " filter-command-no-users" : ""
      }`}
    >
      <div className="filter-control filter-control-period">
        <span className="eyebrow">Period</span>
        <span className="filter-control-value filter-control-period-value mono" title={rangeLabel}>
          <span className="filter-period-full">{rangeLabel}</span>
          <span className="filter-period-compact">{rangeLabelCompact ?? rangeLabel}</span>
        </span>
      </div>

      {isSheet ? (
        <div className="filter-control filter-control-stack">
          <span className="eyebrow">Modules</span>
          <span className="filter-control-value">{modulesValueLabel}</span>
          <ModuleOptions
            scannedModules={scannedModules}
            filterModules={filterModules}
            toggleModule={toggleModule}
          />
        </div>
      ) : (
        <FilterDropdown
          label="Modules"
          valueLabel={modulesValueLabel}
          isOpen={openMenu === "modules"}
          onToggle={() => setOpenMenu(openMenu === "modules" ? null : "modules")}
          onClose={() => setOpenMenu(null)}
        >
          <ModuleOptions
            scannedModules={scannedModules}
            filterModules={filterModules}
            toggleModule={toggleModule}
          />
        </FilterDropdown>
      )}

      {showUsers && (
        isSheet ? (
          <div className="filter-control filter-control-stack">
            <span className="eyebrow">Users</span>
            <span className="filter-control-value filter-control-placeholder">
              {formatNumber(null)}
            </span>
            <p className="filter-sheet-note">User filtering is not enabled yet.</p>
          </div>
        ) : (
          <FilterDropdown
            label="Users"
            valueLabel={formatNumber(null)}
            isOpen={false}
            onToggle={() => {}}
            onClose={() => {}}
            disabled
          />
        )
      )}

      {isSheet ? (
        <div className="filter-control filter-control-stack">
          <span className="eyebrow">Attribution</span>
          <span className="filter-control-value">{clockLabel}</span>
          <AttributionOptions scanConfig={scanConfig} setAttribution={setAttribution} />
        </div>
      ) : (
        <FilterDropdown
          label="Attribution"
          valueLabel={clockLabel}
          isOpen={openMenu === "attribution"}
          onToggle={() => setOpenMenu(openMenu === "attribution" ? null : "attribution")}
          onClose={() => setOpenMenu(null)}
        >
          <AttributionOptions scanConfig={scanConfig} setAttribution={setAttribution} />
        </FilterDropdown>
      )}

      <div className="filter-control filter-control-compare">
        <span className="eyebrow">Compare</span>
        <span className="filter-control-value filter-control-strong">{compareLabel}</span>
      </div>
    </div>
  );
}

export default function FilterBar() {
  const { showHome } = useActions();
  const filters = useReportFilters();
  const [sheetOpen, setSheetOpen] = useState(false);

  function handlePrint() {
    window.print();
  }

  function handleExport() {
    console.log("Export: not yet implemented");
  }

  return (
    <header className="filter-bar">
      <ContentContainer className="filter-bar-inner">
        <div className="filter-bar-lead">
          <button type="button" className="filter-bar-back" onClick={showHome}>
            <span aria-hidden="true">←</span> Reports
          </button>

          <div className="filter-bar-title-block">
            <h1>{filters.displayedModules.map((module) => module.label).join(" + ") || "Analytics"}</h1>
            {filters.accountLabel && (
              <p className="filter-bar-subtitle" title={filters.accountLabel}>
                {filters.accountLabel} · {filters.depthLabel} scan
              </p>
            )}
          </div>
        </div>

        <FilterCommand variant="bar" {...filters} />

        <div className="filter-bar-toolbar">
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="filter-bar-mobile-trigger"
              onClick={() => setSheetOpen(true)}
            >
              <SlidersHorizontal />
              Filters · {filters.filterCount}
            </Button>
            <SheetContent side="right" className="filter-sheet" showCloseButton>
              <SheetHeader>
                <SheetTitle>Report filters</SheetTitle>
                <SheetDescription>
                  Changes apply immediately to the current report.
                </SheetDescription>
              </SheetHeader>
              <div className="filter-sheet-body">
                <FilterCommand variant="sheet" {...filters} />
              </div>
              <SheetFooter>
                <SheetClose asChild>
                  <Button type="button" className="filter-sheet-done">
                    Done
                  </Button>
                </SheetClose>
              </SheetFooter>
            </SheetContent>
          </Sheet>

          <div className="filter-bar-actions">
            <button type="button" className="filter-bar-action" onClick={handlePrint}>
              Print
            </button>
            <button type="button" className="filter-bar-action filter-bar-action-caret" onClick={handleExport}>
              Export <ChevronIcon />
            </button>
          </div>
        </div>
      </ContentContainer>
    </header>
  );
}
