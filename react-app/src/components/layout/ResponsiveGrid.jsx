import { cn } from "@/lib/utils";

/*
  Column count follows the available width instead of a breakpoint list, so the
  same grid behaves correctly in a narrow window and in a zoomed-in wide one.
  `min` is the point at which a column is too cramped to keep; below that the
  grid drops a column on its own.
*/
export function ResponsiveGrid({
  as: Tag = "div",
  min = "240px",
  gap,
  className,
  style,
  children,
  ...props
}) {
  return (
    <Tag
      className={cn(
        "grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(var(--responsive-grid-min,240px),100%),1fr))] gap-[var(--responsive-grid-gap,var(--sp-4))]",
        className
      )}
      style={{
        "--responsive-grid-min": min,
        ...(gap ? { "--responsive-grid-gap": gap } : null),
        ...style,
      }}
      {...props}
    >
      {children}
    </Tag>
  );
}

export default ResponsiveGrid;
