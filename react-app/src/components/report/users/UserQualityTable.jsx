import { formatNumber } from "../../../utils/format";
import QualityIndicator from "./QualityIndicator";
import UserIdentity from "./UserIdentity";
import UserStatusBadge from "./UserStatusBadge";

function OwnerRow({ owner }) {
  return (
    <tr>
      <td>
        <UserIdentity name={owner.ownerName} modules={owner.modules} />
      </td>
      <td className="users-cell-records">
        <strong className="mono">{formatNumber(owner.recordCount)}</strong>
      </td>
      <td className="users-cell-quality">
        <QualityIndicator score={owner.overall} size="lg" emphasize />
      </td>
      <td className="users-cell-dimensions">
        <QualityIndicator label="Completeness" score={owner.completeness} size="sm" />
        <QualityIndicator label="Validity" score={owner.validity} size="sm" />
      </td>
      <td className="users-cell-standing">
        <UserStatusBadge score={owner.overall} />
      </td>
    </tr>
  );
}

function OwnerCard({ owner }) {
  return (
    <li className="users-card">
      <UserIdentity name={owner.ownerName} modules={owner.modules} />
      <div className="users-card-facts">
        <div>
          <span>Records</span>
          <strong className="mono">{formatNumber(owner.recordCount)}</strong>
        </div>
        <div>
          <span>Quality</span>
          <strong className="mono">
            {typeof owner.overall === "number" ? owner.overall : "—"}
          </strong>
        </div>
      </div>
      <QualityIndicator score={owner.overall} size="lg" emphasize />
      <div className="users-card-dimensions">
        <QualityIndicator label="Completeness" score={owner.completeness} size="sm" />
        <QualityIndicator label="Validity" score={owner.validity} size="sm" />
      </div>
      <UserStatusBadge score={owner.overall} />
    </li>
  );
}

export default function UserQualityTable({ owners }) {
  return (
    <section className="users-workspace panel">
      <div className="panel-header users-panel-header">
        <p className="eyebrow">Users</p>
      </div>

      <div className="users-table-wrap">
        <table className="users-table">
          <caption className="sr-only">
            Data quality by CRM owner, including records, overall score,
            completeness, validity, and standing
          </caption>
          <thead>
            <tr>
              <th scope="col">User</th>
              <th scope="col" className="users-cell-records">
                Records
              </th>
              <th scope="col">Quality</th>
              <th scope="col">Completeness and validity</th>
              <th scope="col">Standing</th>
            </tr>
          </thead>
          <tbody>
            {owners.map((owner) => (
              <OwnerRow key={owner.ownerKey} owner={owner} />
            ))}
          </tbody>
        </table>
      </div>

      <ul className="users-list-mobile">
        {owners.map((owner) => (
          <OwnerCard key={owner.ownerKey} owner={owner} />
        ))}
      </ul>
    </section>
  );
}
