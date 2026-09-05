import { formatNumber } from "../../../utils/format";
import QualityIndicator from "./QualityIndicator";
import UserIdentity from "./UserIdentity";
import UserStatusBadge from "./UserStatusBadge";

function OwnerRow({ owner }) {
  return (
    <tr className="hover:bg-surface-sunken">
      <td className="w-[30%] min-w-0 border-b border-line px-3 py-3.5 align-middle first:pl-1">
        <UserIdentity name={owner.ownerName} modules={owner.modules} />
      </td>
      <td className="w-[12%] min-w-0 border-b border-line px-3 py-3.5 text-right align-middle">
        <strong className="mono text-sm font-semibold tracking-tight text-ink">
          {formatNumber(owner.recordCount)}
        </strong>
      </td>
      <td className="w-[20%] min-w-0 border-b border-line px-3 py-3.5 align-middle">
        <QualityIndicator score={owner.overall} size="lg" emphasize />
      </td>
      <td className="w-[22%] min-w-0 border-b border-line px-3 py-3.5 align-middle">
        <div className="flex flex-col gap-2">
          <QualityIndicator label="Completeness" score={owner.completeness} size="sm" />
          <QualityIndicator label="Validity" score={owner.validity} size="sm" />
        </div>
      </td>
      <td className="w-[16%] min-w-0 border-b border-line px-3 py-3.5 text-left align-middle last:pr-1">
        <UserStatusBadge score={owner.overall} />
      </td>
    </tr>
  );
}

function OwnerCard({ owner }) {
  return (
    <li className="flex min-w-0 flex-col gap-3 border-t border-line py-4 first:border-t-0 first:pt-0">
      <UserIdentity name={owner.ownerName} modules={owner.modules} />
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
            Records
          </span>
          <strong className="mono text-lg tracking-tight text-ink">
            {formatNumber(owner.recordCount)}
          </strong>
        </div>
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
            Quality
          </span>
          <strong className="mono text-lg tracking-tight text-ink">
            {typeof owner.overall === "number" ? owner.overall : "—"}
          </strong>
        </div>
      </div>
      <QualityIndicator score={owner.overall} size="lg" emphasize />
      <div className="flex flex-col gap-2.5">
        <QualityIndicator label="Completeness" score={owner.completeness} size="sm" />
        <QualityIndicator label="Validity" score={owner.validity} size="sm" />
      </div>
      <UserStatusBadge score={owner.overall} />
    </li>
  );
}

export default function UserQualityTable({ owners }) {
  return (
    <section className="min-w-0">
      <header className="mb-2.5">
        <p className="eyebrow">Users</p>
      </header>

      <div className="min-w-0 overflow-x-clip @max-[820px]:hidden">
        <table className="w-full table-fixed border-collapse text-[13px]">
          <caption className="sr-only">
            Data quality by CRM owner, including records, overall score,
            completeness, validity, and standing
          </caption>
          <thead>
            <tr>
              <th
                scope="col"
                className="w-[30%] min-w-0 border-b border-line px-3 py-3.5 pl-1 text-left align-middle text-[11px] font-semibold tracking-wider text-ink-muted uppercase"
              >
                User
              </th>
              <th
                scope="col"
                className="w-[12%] min-w-0 border-b border-line px-3 py-3.5 text-right align-middle text-[11px] font-semibold tracking-wider text-ink-muted uppercase"
              >
                Records
              </th>
              <th
                scope="col"
                className="w-[20%] min-w-0 border-b border-line px-3 py-3.5 text-left align-middle text-[11px] font-semibold tracking-wider text-ink-muted uppercase"
              >
                Quality
              </th>
              <th
                scope="col"
                className="w-[22%] min-w-0 border-b border-line px-3 py-3.5 text-left align-middle text-[11px] font-semibold tracking-wider text-ink-muted uppercase"
              >
                Completeness and validity
              </th>
              <th
                scope="col"
                className="w-[16%] min-w-0 border-b border-line px-3 py-3.5 pr-1 text-left align-middle text-[11px] font-semibold tracking-wider text-ink-muted uppercase"
              >
                Standing
              </th>
            </tr>
          </thead>
          <tbody className="[&>tr:last-child>td]:border-b-0">
            {owners.map((owner) => (
              <OwnerRow key={owner.ownerKey} owner={owner} />
            ))}
          </tbody>
        </table>
      </div>

      <ul className="m-0 hidden list-none flex-col p-0 @max-[820px]:flex">
        {owners.map((owner) => (
          <OwnerCard key={owner.ownerKey} owner={owner} />
        ))}
      </ul>
    </section>
  );
}
