import { INSUFFICIENT_BAND } from "../../../utils/bands";

export default function UserStatusBadge({ standing }) {
  const band = standing ?? INSUFFICIENT_BAND;
  return (
    <span
      className="inline-flex max-w-full px-1.5 py-0.5 text-[12px] font-semibold tracking-tight"
      style={{ background: band.soft, color: band.color }}
    >
      {band.label}
    </span>
  );
}
