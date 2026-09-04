import { DOMAIN_LABELS } from "../../../utils/bands";

export default function OverviewCoverageNotice({
  domainScores = [],
  unmeasuredDomains = [],
}) {
  if (!unmeasuredDomains.length) return null;

  const measuredCount = domainScores.filter((domain) => domain.applicable).length;

  return (
    <section className="overview-coverage" aria-label="Measurement coverage">
      <p className="eyebrow">Measurement coverage</p>
      <p>
        <strong>
          {measuredCount} of {domainScores.length} quality dimensions measured.
        </strong>{" "}
        {unmeasuredDomains
          .map((domain) => DOMAIN_LABELS[domain.domain] ?? domain.domain)
          .join(", ")}{" "}
        {unmeasuredDomains.length === 1 ? "was" : "were"} not applicable or are
        not supported by the current pipeline.
      </p>
    </section>
  );
}
