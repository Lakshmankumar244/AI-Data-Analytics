import { useMemo } from "react";
import { useAppState } from "../../../state/AppContext";
import { groupOwnerAnalytics } from "../../../data/ownerAnalytics";
import UserQualityTable from "./UserQualityTable";

function UsersEmpty({ title, children }) {
  return (
    <div className="flex min-w-0 flex-col gap-6 py-6 pb-12 @max-[560px]:gap-4 @max-[560px]:py-4 @max-[560px]:pb-8">
      <section className="min-w-0">
        <p className="eyebrow">Users</p>
        <h2 className="mt-1 font-heading text-lg font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-2 max-w-[46ch] text-[13px] leading-normal text-ink-soft">
          {children}
        </p>
      </section>
    </div>
  );
}

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
      <UsersEmpty title="User analytics were not measured in this scan">
        Owner-level aggregates will appear for scans processed after this
        feature was deployed. Older reports remain available without them.
      </UsersEmpty>
    );
  }

  if (!owners.length) {
    return (
      <UsersEmpty title="No users match the current filters">
        Clear the Users or Modules filter to see owner-level quality again.
      </UsersEmpty>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-6 py-6 pb-12 @max-[560px]:gap-4 @max-[560px]:py-4 @max-[560px]:pb-8">
      <UserQualityTable owners={owners} />
    </div>
  );
}
