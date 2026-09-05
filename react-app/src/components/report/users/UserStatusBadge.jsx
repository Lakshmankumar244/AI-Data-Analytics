import Band from "../../shared/Band";
import { orgBand } from "../../../utils/bands";

const UNMEASURED = {
  id: "na",
  label: "Not measured",
  color: "var(--muted)",
  soft: "var(--surface-sunken)",
};

export default function UserStatusBadge({ score }) {
  const band = typeof score === "number" ? orgBand(score) : UNMEASURED;
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <span
        className="size-[7px] shrink-0 rounded-full"
        style={{ background: band.color }}
        aria-hidden="true"
      />
      <Band band={band} size="sm" />
    </span>
  );
}
