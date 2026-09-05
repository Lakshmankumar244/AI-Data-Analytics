import OverviewEmptyNote from "./OverviewEmptyNote";

export default function OverviewFindings({ findings }) {
  return (
    <section className="flex h-[380px] min-w-0 flex-col overflow-hidden">
      <header className="mb-3 shrink-0">
        <p className="eyebrow">Key findings</p>
        <h2 className="mt-1 font-heading text-lg font-semibold tracking-tight text-ink">
          Issues already measured
        </h2>
      </header>
      <div className="min-h-0 flex-1 overflow-auto pr-1">
        {findings.length > 0 ? (
          <ul className="m-0 flex list-none flex-col p-0">
            {findings.map((finding) => (
              <li
                key={`${finding.module}-${finding.text}`}
                className="flex min-w-0 flex-col gap-1 border-t border-line py-3 text-[13px] leading-normal text-ink-soft first:border-t-0"
              >
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-bold tracking-wider text-ink-soft uppercase">
                    {finding.kind}
                  </span>
                  <span className="text-[11px] font-bold tracking-wider text-ink-muted uppercase">
                    {finding.module}
                  </span>
                </span>
                <span>{finding.text}</span>
              </li>
            ))}
          </ul>
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
