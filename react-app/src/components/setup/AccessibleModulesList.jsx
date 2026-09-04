import { useEffect, useRef, useState } from "react";
import { formatNumber } from "../../utils/format";

function ChevronIcon() {
  return (
    <svg width="9" height="6" viewBox="0 0 9 6" fill="none" aria-hidden="true" className="dropdown-caret">
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
    <div className="accessible-modules">
      <p className="setup-hint">
        These are the modules and record counts visible under your own Zoho login -
        not necessarily everything in the org. A small count here usually means your
        profile&apos;s visibility, not an empty module.
      </p>
      <div className="setup-field" ref={rootRef}>
        <p className="eyebrow">Modules</p>
        <button
          type="button"
          className="dropdown-trigger dropdown-trigger-field"
          aria-expanded={open}
          aria-haspopup="listbox"
          onClick={() => setOpen((current) => !current)}
        >
          <span className="dropdown-trigger-label">
            {selectedItems.length} {selectedItems.length === 1 ? "module" : "modules"} selected
          </span>
          <span className="badge badge-brand">{selectedItems.length}</span>
          <ChevronIcon />
        </button>
        {open && (
          <div className="dropdown-panel dropdown-panel-field setup-module-panel">
            <label className="module-select-all">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={(event) => onSelectAll(event.target.checked)}
                disabled={selectableModules.length === 0}
              />
              <span>Select all</span>
            </label>
            <ul className="module-list" role="group" aria-label="Modules to include in the scan">
              {modules.map((module) => {
                const checked = selected.includes(module.apiName);
                const unavailable = Number(module.recordCount) <= 0;
                return (
                  <li
                    key={module.apiName}
                    className={`module-row${unavailable ? " module-row-disabled" : ""}`}
                  >
                    <label>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={unavailable}
                        onChange={() => onToggle(module.apiName)}
                      />
                      <span className="module-row-label">{module.label}</span>
                    </label>
                    <span className="module-row-count mono">
                      {unavailable
                        ? "0 records \u00b7 No records available"
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
        <div className="setup-module-chips" aria-label="Selected modules">
          {selectedItems.map((module) => (
            <span key={module.apiName} className="setup-module-chip">
              {module.label}
              <button
                type="button"
                className="setup-module-chip-remove"
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
