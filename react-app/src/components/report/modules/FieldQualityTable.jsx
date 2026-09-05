import { formatNumber } from "../../../utils/format";
import { matrixBand } from "../../../utils/bands";

function RateCell({ value, unavailableLabel = "Not checked" }) {
  if (value === null || value === undefined) {
    return (
      <span className="text-[11px] text-ink-muted italic">{unavailableLabel}</span>
    );
  }
  const band = matrixBand(value);
  return (
    <span
      className="mono inline-block min-w-11 px-1.5 py-0.5 text-center"
      style={{ background: band.soft, color: band.color }}
      title={band.label}
    >
      {value}%
    </span>
  );
}

export default function FieldQualityTable({ fields }) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            {[
              "Field",
              "Populated",
              "Empty",
              "Completeness",
              "Checked",
              "Invalid",
              "Validity",
            ].map((heading, index) => (
              <th
                key={heading}
                className={
                  index === 0
                    ? "px-2.5 py-1.5 text-left text-[9px] font-bold tracking-wide whitespace-nowrap text-ink-muted uppercase"
                    : "px-2.5 py-1.5 text-right text-[9px] font-bold tracking-wide whitespace-nowrap text-ink-muted uppercase"
                }
              >
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field.apiName} className="hover:bg-surface-sunken">
              <th
                scope="row"
                className="border-t border-line px-2.5 py-1.5 text-left font-semibold leading-tight whitespace-nowrap text-ink"
              >
                <span>{field.label}</span>
                <span className="mono mt-px block text-[10px] font-normal leading-tight text-ink-muted">
                  {field.apiName}
                </span>
              </th>
              <td className="mono border-t border-line px-2.5 py-1.5 text-right whitespace-nowrap">
                {formatNumber(field.populated)}
              </td>
              <td className="mono border-t border-line px-2.5 py-1.5 text-right whitespace-nowrap">
                {formatNumber(field.empty)}
              </td>
              <td className="border-t border-line px-2.5 py-1.5 text-right whitespace-nowrap">
                <RateCell value={field.completeness} />
              </td>
              <td className="mono border-t border-line px-2.5 py-1.5 text-right whitespace-nowrap">
                {field.checked === null ? "—" : formatNumber(field.checked)}
              </td>
              <td className="mono border-t border-line px-2.5 py-1.5 text-right whitespace-nowrap">
                {field.invalid === null ? "—" : formatNumber(field.invalid)}
              </td>
              <td className="border-t border-line px-2.5 py-1.5 text-right whitespace-nowrap">
                <RateCell value={field.validity} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
