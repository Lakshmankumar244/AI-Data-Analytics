import { formatNumber } from "../../../utils/format";
import { matrixBand } from "../../../utils/bands";
import { cn } from "@/lib/utils";

function scoreTone(score) {
  const band = matrixBand(score);
  const unmeasured = score === null || score === undefined;
  const weak = !unmeasured && (band.id === "warn" || band.id === "bad");
  const watch = !unmeasured && band.id === "fair";
  return { band, unmeasured, weak, watch };
}

function RateCell({ value, unavailableLabel = "Not checked" }) {
  if (value === null || value === undefined) {
    return (
      <span className="text-[12px] text-ink-muted italic">{unavailableLabel}</span>
    );
  }
  const { band, weak, watch } = scoreTone(value);
  return (
    <span
      className="inline-flex min-w-0 items-center justify-end gap-2"
      title={band.label}
    >
      <span className="relative hidden h-1.5 w-12 overflow-hidden bg-surface-sunken @min-[640px]:block">
        <span
          className="absolute inset-y-0 left-0"
          style={{
            width: `${value}%`,
            background: band.color,
            opacity: weak ? 1 : 0.72,
          }}
        />
      </span>
      <span
        className={cn(
          "mono min-w-[2.5rem] text-right text-[13px] font-semibold tracking-tight",
          weak && "px-1.5 py-0.5"
        )}
        style={
          weak
            ? { background: band.soft, color: band.color }
            : watch
              ? { color: band.color }
              : { color: "var(--ink)" }
        }
      >
        {value}%
      </span>
    </span>
  );
}

function CountCell({ value, tone = "neutral" }) {
  if (value === null || value === undefined) {
    return <span className="text-ink-muted">—</span>;
  }
  const flagged = Number(value) > 0 && tone !== "neutral";
  return (
    <span
      className={cn(
        "mono text-[13px]",
        flagged && tone === "empty" && "font-semibold text-attention",
        flagged && tone === "invalid" && "font-semibold text-risk",
        !flagged && "text-ink"
      )}
    >
      {formatNumber(value)}
    </span>
  );
}

export default function FieldQualityTable({ fields }) {
  return (
    <div className="min-w-0 overflow-x-auto overscroll-x-contain">
      <table className="w-full min-w-[640px] border-separate border-spacing-0 text-[13px]">
        <caption className="sr-only">
          Field quality for this module, including populated and empty counts,
          completeness, checked and invalid values, and validity
        </caption>
        <thead>
          <tr>
            {[
              ["Field", "left"],
              ["Populated", "right"],
              ["Empty", "right"],
              ["Completeness", "right"],
              ["Checked", "right"],
              ["Invalid", "right"],
              ["Validity", "right"],
            ].map(([heading, align]) => (
              <th
                key={heading}
                className={cn(
                  "border-b border-line px-2.5 py-2.5 align-middle",
                  align === "left" ? "text-left" : "text-right"
                )}
              >
                <span className="eyebrow">{heading}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&>tr:last-child>th]:border-b-0 [&>tr:last-child>td]:border-b-0">
          {fields.map((field) => {
            const completenessTone = scoreTone(field.completeness);
            const validityTone = scoreTone(field.validity);
            const hasIssue =
              completenessTone.weak ||
              validityTone.weak ||
              Number(field.empty) > 0 ||
              Number(field.invalid) > 0;

            return (
              <tr key={field.apiName} className="group hover:bg-surface-sunken/70">
                <th
                  scope="row"
                  className="border-b border-line py-2.5 pr-4 pl-2 text-left align-middle font-semibold leading-tight text-ink"
                  style={
                    hasIssue
                      ? { boxShadow: "inset 2px 0 0 var(--attention)" }
                      : undefined
                  }
                >
                  <span className="block text-[13px] tracking-tight [overflow-wrap:anywhere]">
                    {field.label}
                  </span>
                  <span className="mono mt-0.5 block text-[11px] font-normal text-ink-muted">
                    {field.apiName}
                  </span>
                </th>
                <td className="border-b border-line px-2.5 py-2.5 text-right whitespace-nowrap">
                  <CountCell value={field.populated} />
                </td>
                <td className="border-b border-line px-2.5 py-2.5 text-right whitespace-nowrap">
                  <CountCell value={field.empty} tone="empty" />
                </td>
                <td className="border-b border-line px-2.5 py-2.5 text-right whitespace-nowrap">
                  <RateCell value={field.completeness} />
                </td>
                <td className="border-b border-line px-2.5 py-2.5 text-right whitespace-nowrap">
                  <CountCell value={field.checked} />
                </td>
                <td className="border-b border-line px-2.5 py-2.5 text-right whitespace-nowrap">
                  <CountCell value={field.invalid} tone="invalid" />
                </td>
                <td className="border-b border-line px-2.5 py-2.5 text-right whitespace-nowrap">
                  <RateCell value={field.validity} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
