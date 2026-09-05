import { cn } from "@/lib/utils";

/*
  Sticks its children to the top of the viewport as one unit.

  Bars stacked inside this share a single sticky context, so a bar never needs
  to know the height of the bar above it. That is deliberate: the filter row
  changes height when it wraps and when the browser is zoomed, and no static
  `top` value can track that.
*/
export function StickyHeaderStack({ className, children, ...props }) {
  return (
    <div
      className={cn(
        "sticky top-0 z-20 flex min-w-0 flex-col bg-[color-mix(in_srgb,var(--paper)_88%,transparent)] shadow-[inset_0_-1px_0_0_color-mix(in_srgb,var(--line)_70%,transparent)] backdrop-blur-[18px] [--app-bar-padding-block:8px]",
        "supports-[not(backdrop-filter:blur(1px))]:bg-paper",
        "[@media(max-height:640px)]:[--app-bar-padding-block:6px]",
        "[@media(max-height:420px)]:static",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export default StickyHeaderStack;
