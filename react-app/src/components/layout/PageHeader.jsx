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
    <header
      className={cn(
        "mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4",
        className
      )}
      {...props}
    >
      <div className="min-w-0 flex-[1_1_min(100%,420px)]">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        {title && (
          <h1 className="mt-1.5 text-[clamp(24px,2.6cqi,32px)] leading-tight tracking-[-0.03em]">
            {title}
          </h1>
        )}
        {description && (
          <p className="mt-2 max-w-[62ch] text-sm leading-relaxed text-ink-soft">
            {description}
          </p>
        )}
        {meta && <p className="mt-2 text-[13px] text-ink-muted">{meta}</p>}
        {children}
      </div>
      {actions && (
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          {actions}
        </div>
      )}
    </header>
  );
}

export default PageHeader;
