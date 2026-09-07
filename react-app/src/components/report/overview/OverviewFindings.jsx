import OverviewEmptyNote from "./OverviewEmptyNote";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const KIND_TONE = {
  Validity: { background: "var(--risk-soft)", color: "var(--risk)" },
  Completeness: { background: "var(--attention-soft)", color: "var(--attention)" },
};

export default function OverviewFindings({ findings, onOpenModule, onOpenRecords, onOpenUsers }) {
  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col">
      <header className="mb-4 shrink-0 border-b border-line pb-3">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          Key findings
        </h2>
        <div className="mt-2 flex flex-wrap gap-2 print:hidden">
          {onOpenRecords && (
            <Button type="button" variant="outline" size="sm" onClick={onOpenRecords}>
              Investigate records
            </Button>
          )}
          {onOpenUsers && (
            <Button type="button" variant="outline" size="sm" onClick={onOpenUsers}>
              Open Users
            </Button>
          )}
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        {findings.length > 0 ? (
          <ol className="m-0 flex list-none flex-col p-0">
            {findings.map((finding, index) => {
              const tone = KIND_TONE[finding.kind];
              return (
                <li
                  key={`${finding.module}-${finding.text}`}
                  className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-2.5 border-t border-line py-3 first:border-t-0"
                >
                  <span className="mono pt-0.5 text-[13px] font-semibold text-ink-muted">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span
                        className={cn(
                          "inline-flex rounded-sm px-1.5 py-0.5 text-[10px] font-semibold tracking-wider uppercase"
                        )}
                        style={
                          tone
                            ? { background: tone.background, color: tone.color }
                            : undefined
                        }
                      >
                        {finding.kind}
                      </span>
                      <span className="text-[11px] font-semibold tracking-wider text-ink-muted uppercase">
                        {finding.module}
                      </span>
                    </p>
                    <p className="mt-1 text-[13px] leading-snug text-ink">{finding.text}</p>
                    {onOpenModule && finding.apiName && (
                      <Button
                        type="button"
                        variant="link"
                        size="sm"
                        className="mt-1 h-auto px-0 print:hidden"
                        onClick={() => onOpenModule(finding.apiName)}
                      >
                        Inspect {finding.module}
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <OverviewEmptyNote fill>
            No completeness or validity findings are available for the modules in
            this view.
          </OverviewEmptyNote>
        )}
      </div>
    </section>
  );
}
