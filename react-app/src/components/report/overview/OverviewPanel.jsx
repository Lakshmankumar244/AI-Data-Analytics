import { cn } from "@/lib/utils";

const VARIANT = {
  hero: "border border-line bg-surface p-6 @min-[640px]:p-7",
  analysis: "border border-line bg-surface p-5 @min-[640px]:p-6",
  chart: "border border-line bg-surface p-5 @min-[640px]:p-6",
  rank: "border border-line bg-surface p-5",
  findings: "border border-line bg-surface p-5",
};

export default function OverviewPanel({
  as: Tag = "section",
  variant = "analysis",
  title,
  eyebrow,
  actions,
  accent,
  className,
  children,
  ...props
}) {
  return (
    <Tag
      className={cn(
        "flex h-full min-h-0 min-w-0 flex-col rounded-md",
        VARIANT[variant] || VARIANT.analysis,
        className
      )}
      style={accent ? { boxShadow: `inset 3px 0 0 ${accent}` } : undefined}
      {...props}
    >
      {(title || actions) && (
        <header className="mb-4 flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
          <div className="min-w-0">
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && (
              <h2
                className={cn(
                  "font-heading text-xl font-semibold tracking-tight text-ink",
                  eyebrow && "mt-1"
                )}
              >
                {title}
              </h2>
            )}
          </div>
          {actions ? <div className="flex flex-wrap gap-2 print:hidden">{actions}</div> : null}
        </header>
      )}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</div>
    </Tag>
  );
}
