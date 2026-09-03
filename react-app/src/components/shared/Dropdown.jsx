import { useEffect, useRef, useState } from "react";
import "./Dropdown.css";

function ChevronIcon() {
  return (
    <svg width="9" height="6" viewBox="0 0 9 6" fill="none" aria-hidden="true" className="dropdown-caret">
      <path d="M1 1L4.5 4.5L8 1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/*
 * Generic single-select dropdown: pill trigger + popover list, styled to
 * match the app's own controls instead of the browser's native <select>
 * chrome (which can't be restyled and looks inconsistent across OSes).
 *
 * Props:
 *   label      - small-caps label shown above the trigger (optional)
 *   value      - id of the currently selected option
 *   options    - [{ id, label }]
 *   onChange   - (id) => void
 *   disabled   - boolean
 */
export default function Dropdown({ label, value, options, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const [alignRight, setAlignRight] = useState(false);
  const ref = useRef(null);
  const selected = options.find((option) => option.id === value);

  useEffect(() => {
    if (!open) return;
    // Decide which edge to anchor from BEFORE it renders off-screen:
    // if the trigger sits closer to the right edge of the viewport than
    // the panel's own width, opening from the left would push it past
    // the page edge - so anchor from the right instead in that case.
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      const estimatedPanelWidth = 320; // matches .dropdown-panel max-width
      const wouldOverflowRight = rect.left + estimatedPanelWidth > window.innerWidth;
      setAlignRight(wouldOverflowRight);
    }
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function handleKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  function choose(id) {
    setOpen(false);
    if (id !== value) onChange(id);
  }

  return (
    <div className="dropdown-field" ref={ref}>
      {label && <span className="dropdown-label">{label}</span>}
      <button
        type="button"
        className={`chip dropdown-trigger${disabled ? " dropdown-trigger-disabled" : ""}`}
        aria-expanded={open}
        aria-disabled={disabled}
        onClick={() => !disabled && setOpen((current) => !current)}
      >
        <span className="dropdown-trigger-label">{selected?.label ?? "—"}</span>
        <ChevronIcon />
      </button>
      {open && !disabled && (
        <div className={`dropdown-panel${alignRight ? " dropdown-panel-right" : ""}`}>
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              className="dropdown-option"
              aria-pressed={option.id === value}
              onClick={() => choose(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
