import { cellValue } from "../../../data/fixRecords";
import FixRecordCell from "./FixRecordCell";

function recordTitle(row) {
  const name = String(row?.displayName || "").trim();
  if (name) return name;
  const id = String(row?.crmRecordId || "").trim();
  return id || "Unnamed record";
}

export default function FixRecordsTable({ columns, rows }) {
  return (
    <div className="min-w-0 overflow-x-auto overscroll-x-contain">
      <table className="w-full min-w-[52rem] border-collapse text-[13px]">
        <caption className="sr-only">
          Defective CRM records with field values and quality issues
        </caption>
        <thead>
          <tr>
            <th className="min-w-[10rem] border-b border-line py-2.5 pr-4 text-left align-middle">
              <span className="eyebrow">Record</span>
            </th>
            {columns.map((column) => (
              <th
                key={column.apiName}
                className="min-w-[8rem] border-b border-line px-3 py-2.5 text-left align-middle"
              >
                <span className="eyebrow">{column.label}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const title = recordTitle(row);
            const identity = row.crmRecordId;
            return (
              <tr
                key={identity || `${title}:${index}`}
                className="hover:bg-surface-sunken/70"
              >
                <td className="min-w-[10rem] border-b border-line py-3 pr-4 align-top">
                  <p className="font-semibold tracking-tight text-ink [overflow-wrap:anywhere]">
                    {title}
                  </p>
                  {identity && identity !== title && (
                    <p className="mono mt-0.5 text-[11px] text-ink-muted [overflow-wrap:anywhere]">
                      {identity}
                    </p>
                  )}
                </td>
                {columns.map((column) => (
                  <FixRecordCell
                    key={column.apiName}
                    apiName={column.apiName}
                    value={cellValue(row.cells, column.apiName)}
                    issues={row.issuesByField?.[column.apiName] || []}
                  />
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
