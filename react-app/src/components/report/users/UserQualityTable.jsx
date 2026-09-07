import { useRef } from "react";
import { formatNumber } from "../../../utils/format";
import { exportVisibleTables } from "../../../utils/exportTable";
import QualityIndicator from "./QualityIndicator";
import UserIdentity from "./UserIdentity";
import UserStatusBadge from "./UserStatusBadge";
import StateBreakdown from "../../shared/StateBreakdown";
import {
  isInsufficient,
  userCleanShare,
  userStanding,
} from "./usersModel";
import { Button } from "@/components/ui/button";

function MixCell({ owner, minRecords }) {
  if (isInsufficient(owner, minRecords)) {
    return (
      <p className="m-0 text-[12px] leading-snug text-ink-muted">
        Fewer than {minRecords} records in this period
      </p>
    );
  }
  if (owner.stateBreakdown) {
    return <StateBreakdown breakdown={owner.stateBreakdown} compact />;
  }
  return <QualityIndicator score={owner.overall} size="lg" emphasize />;
}

function OwnerRow({ owner, minRecords }) {
  const standing = userStanding(owner, minRecords);
  const cleanShare = userCleanShare(owner, minRecords);

  return (
    <tr className="hover:bg-surface-sunken/70">
      <td className="min-w-[11rem] border-b border-line py-3 pr-4 align-middle first:pl-0">
        <UserIdentity name={owner.ownerName} modules={owner.modules} />
      </td>
      <td className="min-w-[5.5rem] border-b border-line px-3 py-3 align-middle text-ink-soft">
        {owner.team || "—"}
      </td>
      <td className="min-w-[4.5rem] border-b border-line px-3 py-3 text-right align-middle">
        <strong className="mono text-[15px] font-semibold tracking-tight text-ink">
          {formatNumber(owner.recordCount)}
        </strong>
      </td>
      <td className="min-w-[4.5rem] border-b border-line px-3 py-3 align-middle">
        <QualityIndicator score={cleanShare} variant="pill" emphasize />
      </td>
      <td className="min-w-[12rem] border-b border-line px-3 py-3 align-middle">
        <MixCell owner={owner} minRecords={minRecords} />
      </td>
      <td className="min-w-[7.5rem] border-b border-line px-3 py-3 align-middle">
        <UserStatusBadge standing={standing} />
      </td>
      <td className="min-w-[9rem] border-b border-line py-3 pl-3 align-middle last:pr-0">
        <span className="text-[13px] leading-snug text-ink-soft">{standing.action}</span>
      </td>
    </tr>
  );
}

function OwnerCard({ owner, minRecords }) {
  const standing = userStanding(owner, minRecords);
  const cleanShare = userCleanShare(owner, minRecords);

  return (
    <li className="flex min-w-0 flex-col gap-3 border-t border-line py-4 first:border-t-0 first:pt-0">
      <div className="flex min-w-0 items-start justify-between gap-4">
        <UserIdentity name={owner.ownerName} modules={owner.modules} />
        <span className="shrink-0 text-[13px] text-ink-muted">{owner.team || "—"}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        <div className="min-w-0">
          <span className="eyebrow">Records</span>
          <strong className="mono mt-1 block text-[17px] tracking-tight text-ink">
            {formatNumber(owner.recordCount)}
          </strong>
        </div>
        <div className="min-w-0">
          <span className="eyebrow">% Clean</span>
          <div className="mt-1">
            <QualityIndicator score={cleanShare} variant="pill" emphasize />
          </div>
        </div>
        <div className="col-span-2 min-w-0">
          <span className="eyebrow">What their records look like</span>
          <div className="mt-2">
            <MixCell owner={owner} minRecords={minRecords} />
          </div>
        </div>
        <div className="min-w-0">
          <span className="eyebrow">Where they stand</span>
          <div className="mt-1.5">
            <UserStatusBadge standing={standing} />
          </div>
        </div>
        <div className="min-w-0">
          <span className="eyebrow">Suggested next step</span>
          <p className="mt-1.5 m-0 text-[13px] leading-snug text-ink-soft">
            {standing.action}
          </p>
        </div>
      </div>
    </li>
  );
}

export default function UserQualityTable({ owners, minRecords, insight }) {
  const rootRef = useRef(null);

  return (
    <section
      ref={rootRef}
      className="flex min-w-0 flex-col rounded-md border border-line bg-surface p-5 @min-[640px]:p-6"
    >
      <header className="mb-4 flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          Users
        </h2>
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto px-0 print:hidden"
          onClick={() => exportVisibleTables(rootRef.current, "user-accountability")}
        >
          Export
        </Button>
      </header>

      <div className="min-w-0 overflow-x-auto overscroll-x-contain @max-[960px]:hidden">
        <table className="w-full min-w-[52rem] border-collapse text-[13px]">
          <caption className="sr-only">
            User quality analysis, including team, records, percent clean, record
            mix, standing, and suggested next step
          </caption>
          <thead>
            <tr>
              <th scope="col" className="min-w-[11rem] border-b border-line py-2.5 pr-4 text-left align-middle first:pl-0">
                <span className="eyebrow">User</span>
              </th>
              <th scope="col" className="min-w-[5.5rem] border-b border-line px-3 py-2.5 text-left align-middle">
                <span className="eyebrow">Team</span>
              </th>
              <th scope="col" className="min-w-[4.5rem] border-b border-line px-3 py-2.5 text-right align-middle">
                <span className="eyebrow">Records</span>
              </th>
              <th scope="col" className="min-w-[4.5rem] border-b border-line px-3 py-2.5 text-left align-middle">
                <span className="eyebrow">% Clean</span>
              </th>
              <th scope="col" className="min-w-[12rem] border-b border-line px-3 py-2.5 text-left align-middle">
                <span className="eyebrow">What their records look like</span>
              </th>
              <th scope="col" className="min-w-[7.5rem] border-b border-line px-3 py-2.5 text-left align-middle">
                <span className="eyebrow">Where they stand</span>
              </th>
              <th scope="col" className="min-w-[9rem] border-b border-line py-2.5 pl-3 text-left align-middle last:pr-0">
                <span className="eyebrow">Suggested next step</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {owners.map((owner) => (
              <OwnerRow key={owner.ownerKey} owner={owner} minRecords={minRecords} />
            ))}
          </tbody>
        </table>
      </div>

      <ul className="m-0 hidden list-none flex-col p-0 @max-[960px]:flex">
        {owners.map((owner) => (
          <OwnerCard key={owner.ownerKey} owner={owner} minRecords={minRecords} />
        ))}
      </ul>

      {insight && (
        <aside
          className="mt-5 border-l-[3px] border-brand bg-brand-soft px-4 py-3 text-[13px] font-semibold leading-snug text-brand-strong"
          role="note"
        >
          {insight}
        </aside>
      )}
    </section>
  );
}
