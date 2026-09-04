import { cn } from "@/lib/utils";

/*
  Screen-level title block: eyebrow, heading, supporting copy, and an optional
  action cluster that drops below the text when there is no room beside it.
  `children` renders under the copy for screens that need extra controls in the
  header (the running scan status row, for example).
*/
export function PageHeader({
  eyebrow,
  title,
  description,
  meta,
  actions,
  className,
  children,
  ...props
}) {
  return (
    <header className={cn("page-header", className)} {...props}>
      <div className="page-header-text">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        {title && <h1>{title}</h1>}
        {description && <p className="page-header-description">{description}</p>}
        {meta && <p className="page-header-meta">{meta}</p>}
        {children}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export default PageHeader;
