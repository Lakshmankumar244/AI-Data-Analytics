import { cn } from "@/lib/utils";

/*
  The shared content column. Every horizontal edge in the app - the filter bar,
  the tab bar, and each screen body - comes from an instance of this, which is
  what keeps them aligned without anyone calculating a centring offset.

  `flush` drops the gutter for callers that are already inside a padded box but
  still want the max-width and centring.
*/
export function ContentContainer({ as: Tag = "div", flush = false, className, children, ...props }) {
  return (
    <Tag
      className={cn("content-container", flush && "content-container-flush", className)}
      {...props}
    >
      {children}
    </Tag>
  );
}

export default ContentContainer;
