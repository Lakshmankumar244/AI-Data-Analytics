import { formatNumber } from "../../../utils/format";
import { matrixBand } from "../../../utils/bands";
import "./FieldQualityTable.css";

function RateCell({ value, unavailableLabel = "Not checked" }) {
  if (value === null || value === undefined) {
    return <span className="field-quality-na">{unavailableLabel}</span>;
  }
  const band = matrixBand(value);
  return (
    <span
      className="field-quality-rate mono"
      style={{ background: band.soft, color: band.color }}
      title={band.label}
    >
      {value}%
    </span>
  );
}

export default function FieldQualityTable({ fields }) {
  return (
    <div className="field-quality-wrap">
      <table className="field-quality-table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Populated</th>
            <th>Empty</th>
            <th>Completeness</th>
            <th>Checked</th>
            <th>Invalid</th>
            <th>Validity</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field.apiName}>
              <th scope="row">
                <span>{field.label}</span>
                <span className="field-quality-api mono">{field.apiName}</span>
              </th>
              <td className="mono">{formatNumber(field.populated)}</td>
              <td className="mono">{formatNumber(field.empty)}</td>
              <td><RateCell value={field.completeness} /></td>
              <td className="mono">
                {field.checked === null ? "—" : formatNumber(field.checked)}
              </td>
              <td className="mono">
                {field.invalid === null ? "—" : formatNumber(field.invalid)}
              </td>
              <td><RateCell value={field.validity} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
