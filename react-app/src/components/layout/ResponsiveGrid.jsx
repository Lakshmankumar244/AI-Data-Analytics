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
      className={cn("responsive-grid", className)}
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
