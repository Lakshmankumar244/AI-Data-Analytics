import OverviewEmptyNote from "./OverviewEmptyNote";

export default function OverviewFindings({ findings }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Key findings</p>
          <h2>Issues already measured</h2>
        </div>
      </div>
      {findings.length > 0 ? (
        <ul className="overview-findings-list">
          {findings.map((finding) => (
            <li key={`${finding.module}-${finding.text}`}>
              <span className="overview-finding-meta">
                <span className="overview-finding-kind">{finding.kind}</span>
                <span className="overview-finding-module">{finding.module}</span>
              </span>
              <span>{finding.text}</span>
            </li>
          ))}
        </ul>
      ) : (
        <OverviewEmptyNote>
          No completeness or validity findings are available for the modules in
          this view.
        </OverviewEmptyNote>
      )}
    </section>
  );
}
