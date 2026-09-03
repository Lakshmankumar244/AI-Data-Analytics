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
    <div className={cn("app-header-stack", className)} {...props}>
      {children}
    </div>
  );
}

export default StickyHeaderStack;
