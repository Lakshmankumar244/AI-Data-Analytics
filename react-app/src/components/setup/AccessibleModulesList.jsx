import { useEffect, useRef, useState } from "react";
import { formatNumber } from "../../utils/format";
import { cn } from "@/lib/utils";

function ChevronIcon({ open }) {
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

export default function AccessibleModulesList({ modules, selected, onToggle, onSelectAll }) {
  const selectAllRef = useRef(null);
  const rootRef = useRef(null);
  const [open, setOpen] = useState(false);
  const selectedModules = new Set(selected);
  const selectableModules = modules.filter((module) => Number(module.recordCount) > 0);
  const selectedCount = selectableModules.filter((module) => selectedModules.has(module.apiName)).length;
  const allSelected = selectableModules.length > 0 && selectedCount === selectableModules.length;
  const someSelected = selectedCount > 0 && !allSelected;
  const selectedItems = modules.filter((module) => selected.includes(module.apiName));

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  useEffect(() => {
    if (!open) return;
    function handleOutside(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    function handleKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <div className="flex flex-col gap-5">
      <div className="relative min-w-0" ref={rootRef}>
        <button
          type="button"
          className={cn(
            "flex w-full min-w-0 cursor-pointer items-center justify-between gap-3 border border-line bg-paper px-3 py-2.5 text-left text-[13px] font-semibold text-ink transition-colors",
            open
              ? "border-brand text-brand-strong"
              : "hover:border-line-strong hover:text-ink"
          )}
          aria-expanded={open}
          aria-haspopup="listbox"
          onClick={() => setOpen((current) => !current)}
        >
          <span className="min-w-0 truncate">
            {selectedItems.length === 0
              ? "Choose modules"
              : `${selectedItems.length} ${
                  selectedItems.length === 1 ? "module" : "modules"
                } selected`}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <span className="mono text-[11px] text-ink-muted">{selectedItems.length}</span>
            <ChevronIcon open={open} />
          </span>
        </button>
        {open && (
          <div className="absolute top-[calc(100%+8px)] z-30 w-full min-w-[min(100%,20rem)] bg-surface py-2 shadow-floating ring-1 ring-line">
            <label
              className={cn(
                "flex min-h-10 items-center gap-2 px-3 font-semibold",
                selectableModules.length === 0
                  ? "cursor-not-allowed text-ink-muted"
                  : "cursor-pointer"
              )}
            >
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={(event) => onSelectAll(event.target.checked)}
                disabled={selectableModules.length === 0}
              />
              <span>Select all</span>
            </label>
            <ul
              className="m-0 max-h-[280px] list-none overflow-y-auto border-t border-line p-0 [scrollbar-gutter:stable]"
              role="group"
              aria-label="Modules to include in the scan"
            >
              {modules.map((module) => {
                const checked = selected.includes(module.apiName);
                const unavailable = Number(module.recordCount) <= 0;
                return (
                  <li
                    key={module.apiName}
                    className={cn(
                      "flex items-center justify-between gap-3 px-3 py-3",
                      unavailable && "opacity-50"
                    )}
                  >
                    <label
                      className={cn(
                        "flex min-w-0 items-center gap-2",
                        unavailable ? "cursor-not-allowed" : "cursor-pointer"
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={unavailable}
                        onChange={() => onToggle(module.apiName)}
                      />
                      <span className="font-medium">{module.label}</span>
                    </label>
                    <span className="mono shrink-0 text-[13px] text-ink-muted">
                      {unavailable
                        ? "0 records"
                        : `${formatNumber(module.recordCount)} records`}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      {selectedItems.length > 0 && (
        <div className="flex flex-wrap gap-x-2 gap-y-2" aria-label="Selected modules">
          {selectedItems.map((module) => (
            <span
              key={module.apiName}
              className="inline-flex min-h-8 items-center gap-1.5 bg-surface-sunken py-1 pr-1.5 pl-2.5 text-[13px] font-medium text-ink"
            >
              {module.label}
              <button
                type="button"
                className="grid size-5 place-items-center border-0 bg-transparent p-0 text-base leading-none text-ink-muted hover:text-ink"
                aria-label={`Remove ${module.label}`}
                onClick={() => onToggle(module.apiName)}
              >
                {"\u00d7"}
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
