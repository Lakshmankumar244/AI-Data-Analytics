import { cn } from "@/lib/utils";
import { issueMessage } from "../../../data/fixRecords";

const ERROR_SEVERITIES = new Set(["HIGH", "CRITICAL"]);

function issueTone(issue = {}) {
  const severity = String(issue.severity || "").trim().toUpperCase();
  return ERROR_SEVERITIES.has(severity) ? "error" : "warning";
}

function cellTone(issues) {
  if (!issues.length) return "normal";
  return issues.some((issue) => issueTone(issue) === "error")
    ? "error"
    : "warning";
}

const CELL_STATE_CLASS = {
  error: "border-destructive/20 bg-destructive/10",
  warning: "border-attention/20 bg-attention-soft",
  normal: "border-transparent bg-transparent",
};

const ISSUE_TEXT_CLASS = {
  error: "text-destructive",
  warning: "text-attention",
};

export default function FixRecordCell({ apiName, value, issues = [] }) {
  const text = value == null ? "" : String(value);
  const empty = text.trim() === "";
  const tone = cellTone(issues);

  return (
    <td
      className="min-w-[8rem] border-b border-line px-2 py-2 align-top"
      data-field={apiName}
    >
      <div
        className={cn(
          "min-w-0 rounded-md border px-2 py-1.5",
          CELL_STATE_CLASS[tone]
        )}
      >
        <div className="text-[13px] leading-snug text-ink [overflow-wrap:anywhere]">
          {empty ? "—" : text}
        </div>
        {issues.length > 0 && (
          <div className="mt-0.5 flex flex-col gap-0.5">
            {issues.map((issue) => (
              <div
                key={`${issue.issueType}:${issue.messageCode}:${issue.fieldApiName}`}
                className={cn(
                  "text-[12px] leading-tight",
                  ISSUE_TEXT_CLASS[issueTone(issue)]
                )}
              >
                {issue.message || issueMessage(issue)}
              </div>
            ))}
          </div>
        )}
      </div>
    </td>
  );
}
