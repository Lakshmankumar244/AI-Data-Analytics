import { useEffect, useRef } from "react";
import { formatNumber } from "../../utils/format";

export default function AccessibleModulesList({ modules, selected, onToggle, onSelectAll }) {
  const selectAllRef = useRef(null);
  const selectedModules = new Set(selected);
  const selectableModules = modules.filter((module) => Number(module.recordCount) > 0);
  const selectedCount = selectableModules.filter((module) => selectedModules.has(module.apiName)).length;
  const allSelected = selectableModules.length > 0 && selectedCount === selectableModules.length;
  const someSelected = selectedCount > 0 && !allSelected;

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  return (
    <div className="accessible-modules">
      <p className="eyebrow">Accessible to your account</p>
      <p className="setup-hint">
        These are the modules and record counts visible under your own Zoho login -
        not necessarily everything in the org. A small count here usually means your
        profile's visibility, not an empty module.
      </p>
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
        {modules.map((m) => {
          const checked = selected.includes(m.apiName);
          const unavailable = Number(m.recordCount) <= 0;
          return (
            <li key={m.apiName} className={`module-row${unavailable ? " module-row-disabled" : ""}`}>
              <label>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={unavailable}
                  onChange={() => onToggle(m.apiName)}
                />
                <span className="module-row-label">{m.label}</span>
              </label>
              <span className="module-row-count mono">
                {unavailable ? "0 records · No records available" : `${formatNumber(m.recordCount)} records`}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
