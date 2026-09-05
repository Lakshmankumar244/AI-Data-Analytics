import { useEffect, useRef, useState } from "react";
import { Check, SlidersHorizontal } from "lucide-react";
import { useAppState, useActions } from "../../state/AppContext";
import { formatNumber, formatReportPeriod } from "../../utils/format";
import { exportVisibleTables } from "../../utils/exportTable";
import { groupOwnerAnalytics } from "../../data/ownerAnalytics";
import { cn } from "@/lib/utils";
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

const RANGE_LABELS = { "30d": "Last 30 days", "90d": "Last 90 days", "180d": "Last 6 months", all: "All time" };
const CLOCK_LABELS = { created: "Created date", modified: "Modified date" };

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

function ChevronIcon({ open = false }) {
  return (
    <svg
      width="9"
      height="6"
      viewBox="0 0 9 6"
      fill="none"
      aria-hidden="true"
      className={cn(
        "shrink-0 text-ink-muted transition-transform duration-150",
        open && "rotate-180 text-brand-strong"
      )}
    >
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
    <div className="relative flex min-w-0 flex-col justify-center gap-px px-2.5 py-0.5" ref={ref}>
      <span className="eyebrow">{label}</span>
      <button
        type="button"
        className={cn(
          "inline-flex max-w-full items-center gap-1 border-0 bg-transparent p-0",
          disabled ? "cursor-not-allowed" : "cursor-pointer"
        )}
        aria-expanded={isOpen}
        aria-disabled={disabled}
        title={disabled ? "User analytics were not measured in this scan" : undefined}
        onClick={() => !disabled && onToggle()}
      >
        <span
          className={cn(
            "truncate text-xs font-medium",
            disabled
              ? "text-ink-muted opacity-70"
              : isOpen
                ? "text-brand-strong"
                : "text-ink hover:text-brand-strong"
          )}
        >
          {valueLabel}
        </span>
        <ChevronIcon open={isOpen && !disabled} />
      </button>
      {isOpen && !disabled && (
        <div className="absolute top-[calc(100%+10px)] left-0 z-30 min-w-[min(200px,100%)] max-w-[min(300px,70cqi)] bg-surface p-2 shadow-floating ring-1 ring-line">
          {children}
        </div>
      )}
    </div>
  );
}

function useReportFilters() {
  const { connection, scan, scanConfig, filterModules, filterUsers } = useAppState();
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
  const scannedUsers = groupOwnerAnalytics(scan?.moduleAnalytics ?? [], filterModules);
  const displayedUsers = filterUsers.length
    ? scannedUsers.filter((owner) => filterUsers.includes(owner.ownerKey))
    : scannedUsers;
  const usersEnabled = scannedUsers.length > 0;
  const usersValueLabel = !usersEnabled
    ? formatNumber(null)
    : filterUsers.length === 0 || filterUsers.length === scannedUsers.length
      ? `All ${scannedUsers.length}`
      : displayedUsers.map((owner) => owner.ownerName).join(", ");

  const compareDays = periodLengthDays(scan, scanConfig);
  const compareLabel = compareDays ? `Prior ${compareDays} day${compareDays === 1 ? "" : "s"}` : "Prior period";
  const filterCount = 5;

  function toggleModule(apiName) {
    const set = new Set(filterModules);
    set.has(apiName) ? set.delete(apiName) : set.add(apiName);
    setFilter({ filterModules: Array.from(set) });
  }

  function toggleUser(ownerKey) {
    const set = new Set(filterUsers);
    set.has(ownerKey) ? set.delete(ownerKey) : set.add(ownerKey);
    setFilter({ filterUsers: Array.from(set) });
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
    scannedUsers,
    usersEnabled,
    usersValueLabel,
    compareLabel,
    showUsers: true,
    filterCount,
    filterModules,
    filterUsers,
    toggleModule,
    toggleUser,
  };
}

function FilterOption({ pressed, onClick, children }) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-2.5 border-0 px-2.5 py-2 text-left text-[13px] font-medium",
        pressed
          ? "bg-brand-soft font-semibold text-brand-strong"
          : "bg-transparent text-ink-soft hover:bg-surface-sunken"
      )}
      aria-pressed={pressed}
      onClick={onClick}
    >
      <span
        className={cn(
          "grid size-[15px] shrink-0 place-items-center border-[1.5px]",
          pressed
            ? "border-brand bg-brand text-on-brand"
            : "border-line-strong bg-surface"
        )}
        aria-hidden="true"
      >
        {pressed && <Check className="size-2.5" strokeWidth={3} />}
      </span>
      {children}
    </button>
  );
}

function ModuleOptions({ scannedModules, filterModules, toggleModule }) {
  return (
    <div className="flex max-h-60 flex-col gap-0.5 overflow-y-auto" aria-label="Filter report modules">
      {scannedModules.map((module) => {
        const isActive = filterModules.length === 0 || filterModules.includes(module.apiName);
        return (
          <FilterOption
            key={module.apiName}
            pressed={isActive}
            onClick={() => toggleModule(module.apiName)}
          >
            {module.label}
          </FilterOption>
        );
      })}
    </div>
  );
}

function UserOptions({ scannedUsers, filterUsers, toggleUser }) {
  return (
    <div className="flex max-h-60 flex-col gap-0.5 overflow-y-auto" aria-label="Filter report users">
      {scannedUsers.map((owner) => {
        const isActive = filterUsers.length === 0 || filterUsers.includes(owner.ownerKey);
        return (
          <FilterOption
            key={owner.ownerKey}
            pressed={isActive}
            onClick={() => toggleUser(owner.ownerKey)}
          >
            {owner.ownerName}
          </FilterOption>
        );
      })}
    </div>
  );
}

function Readout({ label, value, title, wrap = false }) {
  return (
    <div className="flex min-w-0 flex-col justify-center gap-px px-2.5 py-0.5">
      <span className="eyebrow">{label}</span>
      <span
        className={cn(
          "text-xs font-semibold text-ink",
          wrap ? "whitespace-normal" : "truncate"
        )}
        title={title ?? (typeof value === "string" ? value : undefined)}
      >
        {value}
      </span>
    </div>
  );
}

function FilterCommand({
  variant,
  rangeLabel,
  rangeLabelCompact,
  modulesValueLabel,
  usersValueLabel,
  usersEnabled,
  clockLabel,
  compareLabel,
  showUsers,
  openMenu,
  setOpenMenu,
  scannedModules,
  filterModules,
  toggleModule,
  scannedUsers,
  filterUsers,
  toggleUser,
}) {
  const isSheet = variant === "sheet";

  const moduleControl = isSheet ? (
    <div className="flex min-w-0 flex-col gap-2">
      <span className="eyebrow">Modules</span>
      <span className="text-xs font-medium whitespace-normal text-ink">{modulesValueLabel}</span>
      <div className="bg-surface-sunken p-1.5 ring-1 ring-line">
        <ModuleOptions
          scannedModules={scannedModules}
          filterModules={filterModules}
          toggleModule={toggleModule}
        />
      </div>
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
  );

  const userControl = showUsers && (
    isSheet ? (
      <div className="flex min-w-0 flex-col gap-2">
        <span className="eyebrow">Users</span>
        <span className="text-xs font-medium whitespace-normal text-ink">{usersValueLabel}</span>
        {usersEnabled ? (
          <div className="bg-surface-sunken p-1.5 ring-1 ring-line">
            <UserOptions
              scannedUsers={scannedUsers}
              filterUsers={filterUsers}
              toggleUser={toggleUser}
            />
          </div>
        ) : (
          <p className="text-xs leading-snug text-ink-muted">
            User analytics were not measured in this scan.
          </p>
        )}
      </div>
    ) : (
      <FilterDropdown
        label="Users"
        valueLabel={usersValueLabel}
        isOpen={openMenu === "users"}
        onToggle={() => setOpenMenu(openMenu === "users" ? null : "users")}
        onClose={() => setOpenMenu(null)}
        disabled={!usersEnabled}
      >
        <UserOptions
          scannedUsers={scannedUsers}
          filterUsers={filterUsers}
          toggleUser={toggleUser}
        />
      </FilterDropdown>
    )
  );

  if (isSheet) {
    return (
      <div className="flex w-full min-w-0 flex-col gap-5">
        <Readout label="Period" value={rangeLabel} title={rangeLabel} wrap />
        {moduleControl}
        {userControl}
        <Readout
          label="Attribution"
          value={clockLabel}
          title="Attribution is set when the scan starts. Start a new scan to change created vs modified date."
          wrap
        />
        <Readout label="Compare" value={compareLabel} wrap />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "grid min-w-0 w-full divide-x divide-line @max-[760px]:hidden",
        showUsers
          ? "grid-cols-[minmax(8rem,1.5fr)_repeat(4,minmax(5rem,1fr))]"
          : "grid-cols-[minmax(8rem,1.5fr)_repeat(3,minmax(5rem,1fr))]"
      )}
    >
      <Readout
        label="Period"
        value={rangeLabelCompact ?? rangeLabel}
        title={rangeLabel}
      />
      {moduleControl}
      {userControl}
      <Readout
        label="Attribution"
        value={clockLabel}
        title="Attribution is set when the scan starts. Start a new scan to change created vs modified date."
      />
      <Readout label="Compare" value={compareLabel} />
    </div>
  );
}

export default function FilterBar() {
  const { showHome } = useActions();
  const { tab } = useAppState();
  const filters = useReportFilters();
  const [sheetOpen, setSheetOpen] = useState(false);

  function handlePrint() {
    window.print();
  }

  function handleExport() {
    const root = document.querySelector("[data-export-root]") || document.querySelector(".report-shell-panel");
    exportVisibleTables(root, `crm-data-health-${tab || "report"}`);
  }

  return (
    <header className="min-w-0">
      <ContentContainer className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2.5 py-[var(--app-bar-padding-block,6px)] @max-[760px]:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex min-w-0 items-center gap-2.5">
          <Button type="button" variant="outline" size="sm" onClick={showHome}>
            <span aria-hidden="true">←</span> Reports
          </Button>
          <div className="min-w-0 border-r border-line pr-2.5 @max-[900px]:border-r-0 @max-[900px]:pr-0">
            <h1 className="max-w-[clamp(96px,14cqi,200px)] truncate text-[13px] leading-tight font-semibold">
              {filters.displayedModules.map((module) => module.label).join(" + ") || "Analytics"}
            </h1>
            {filters.accountLabel && (
              <p
                className="mt-0.5 hidden max-w-[clamp(96px,14cqi,200px)] truncate text-[11px] text-ink-muted @min-[901px]:block"
                title={filters.accountLabel}
              >
                {filters.accountLabel} · {filters.depthLabel} scan
              </p>
            )}
          </div>
        </div>

        <FilterCommand variant="bar" {...filters} />

        <div className="flex items-center gap-2">
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="hidden @max-[760px]:inline-flex print:hidden"
              onClick={() => setSheetOpen(true)}
            >
              <SlidersHorizontal />
              Filters · {filters.filterCount}
            </Button>
            <SheetContent side="right" className="bg-surface text-ink" showCloseButton>
              <SheetHeader>
                <SheetTitle>Report filters</SheetTitle>
                <SheetDescription>
                  Changes apply immediately to the current report.
                </SheetDescription>
              </SheetHeader>
              <div className="min-h-0 flex-1 overflow-auto px-4 pb-2">
                <FilterCommand variant="sheet" {...filters} />
              </div>
              <SheetFooter>
                <SheetClose asChild>
                  <Button type="button" className="w-full">
                    Done
                  </Button>
                </SheetClose>
              </SheetFooter>
            </SheetContent>
          </Sheet>

          <div className="flex items-center gap-1">
            <Button type="button" variant="ghost" size="sm" onClick={handlePrint}>
              Print
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={handleExport}>
              Export <ChevronIcon />
            </Button>
          </div>
        </div>
      </ContentContainer>
    </header>
  );
}
