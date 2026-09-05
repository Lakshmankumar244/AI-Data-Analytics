import { useEffect, useRef, useState } from "react";
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
      <path
        d="M1 1L4.5 4.5L8 1"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/*
 * Generic single-select dropdown: compact trigger + popover list, styled to
 * match the app's own controls instead of the browser's native <select>
 * chrome (which can't be restyled and looks inconsistent across OSes).
 *
 * Props:
 *   label      - small-caps label shown above the trigger (optional)
 *   value      - id of the currently selected option
 *   options    - [{ id, label }]
 *   onChange   - (id) => void
 *   disabled   - boolean
 *   variant    - "chip" (default, compact filter) or "field" (full-width form)
 */
export default function Dropdown({
  label,
  value,
  options,
  onChange,
  disabled,
  variant = "chip",
}) {
  const [open, setOpen] = useState(false);
  const [alignRight, setAlignRight] = useState(false);
  const ref = useRef(null);
  const selected = options.find((option) => option.id === value);
  const isField = variant === "field";

  useEffect(() => {
    if (!open) return;
    // Decide which edge to anchor from BEFORE it renders off-screen:
    // if the trigger sits closer to the right edge of the viewport than
    // the panel's own width, opening from the left would push it past
    // the page edge - so anchor from the right instead in that case.
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      const estimatedPanelWidth = isField ? rect.width : 320;
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
  }, [open, isField]);

  function choose(id) {
    setOpen(false);
    if (id !== value) onChange(id);
  }

  return (
    <div
      className={cn("relative flex flex-col gap-[3px]", isField && "w-full min-w-0")}
      ref={ref}
    >
      {label && (
        <span
          className={
            isField
              ? "eyebrow"
              : "font-mono text-[10px] tracking-wide text-ink-muted uppercase"
          }
        >
          {label}
        </span>
      )}
      <button
        type="button"
        className={cn(
          "cursor-pointer font-[inherit]",
          isField
            ? cn(
                "flex min-h-10 w-full items-center justify-between gap-2 border border-line-strong bg-surface px-3 py-2 text-[13px] font-medium text-ink",
                !disabled && "hover:border-ink-soft",
                open && "border-brand"
              )
            : cn(
                "inline-flex min-h-8 items-center gap-2 rounded-full border border-line-strong bg-surface px-[11px] py-[5px] text-[13px] font-semibold text-ink-soft",
                !disabled && "hover:border-brand hover:bg-brand-soft hover:text-brand-strong",
                open && "border-brand bg-brand-soft text-brand-strong"
              ),
          disabled && "cursor-not-allowed opacity-60"
        )}
        aria-expanded={open}
        aria-disabled={disabled}
        onClick={() => !disabled && setOpen((current) => !current)}
      >
        <span
          className={cn(
            "truncate",
            isField ? "min-w-0 flex-1 text-left" : "max-w-80"
          )}
        >
          {selected?.label ?? "\u2014"}
        </span>
        <ChevronIcon open={open && !disabled} />
      </button>
      {open && !disabled && (
        <div
          className={cn(
            "absolute top-[calc(100%+8px)] z-30 flex min-w-full flex-col gap-0.5 border border-line bg-surface p-2 shadow-[var(--shadow-float)]",
            isField ? "w-full max-w-none" : "max-w-[360px]",
            alignRight ? "right-0 left-auto" : "left-0"
          )}
        >
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              className={cn(
                "overflow-hidden border-0 bg-transparent px-2.5 py-2 text-left text-[13px] font-medium text-ellipsis whitespace-nowrap text-ink-soft hover:bg-surface-sunken",
                option.id === value && "bg-brand-soft font-semibold text-brand-strong"
              )}
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
