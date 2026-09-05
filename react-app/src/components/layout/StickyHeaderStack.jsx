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
        "sticky top-0 z-20 flex min-w-0 flex-col border-b border-line bg-[color-mix(in_srgb,var(--paper)_92%,transparent)] backdrop-blur-[16px] [--app-bar-padding-block:6px]",
        "supports-[not(backdrop-filter:blur(1px))]:bg-paper",
        "[@media(max-height:640px)]:[--app-bar-padding-block:4px]",
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
