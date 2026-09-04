import { useMemo } from "react";
import { useAppState } from "../../../state/AppContext";
import { groupOwnerAnalytics } from "../../../data/ownerAnalytics";
import UserQualityTable from "./UserQualityTable";
import "./UsersTab.css";

export default function UsersTab() {
  const { scan, filterModules, filterUsers } = useAppState();
  const owners = useMemo(() => {
    const grouped = groupOwnerAnalytics(scan?.moduleAnalytics ?? [], filterModules);
    if (!filterUsers.length) return grouped;
    const selected = new Set(filterUsers);
    return grouped.filter((owner) => selected.has(owner.ownerKey));
  }, [filterModules, filterUsers, scan]);
  const hasOwnerAnalytics = useMemo(
    () => groupOwnerAnalytics(scan?.moduleAnalytics ?? [], []).length > 0,
    [scan]
  );

  if (!hasOwnerAnalytics) {
    return (
      <div className="users-tab">
        <section className="panel users-empty">
          <p className="eyebrow">Users</p>
          <h2>User analytics were not measured in this scan</h2>
          <p>
            Owner-level aggregates will appear for scans processed after this
            feature was deployed. Older reports remain available without them.
          </p>
        </section>
      </div>
    );
  }

  if (!owners.length) {
    return (
      <div className="users-tab">
        <section className="panel users-empty">
          <p className="eyebrow">Users</p>
          <h2>No users match the current filters</h2>
          <p>
            Clear the Users or Modules filter to see owner-level quality again.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="users-tab">
      <UserQualityTable owners={owners} />
    </div>
  );
}
