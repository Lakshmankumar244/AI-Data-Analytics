import { useMemo } from "react";
import { useAppState } from "../../../state/AppContext";
import { groupOwnerAnalytics } from "../../../data/ownerAnalytics";
import UserQualityTable from "./UserQualityTable";
import { recordsNeedingActionInsight } from "./usersModel";

function UsersEmpty({ title, children }) {
  return (
    <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <section className="min-w-0">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-2 max-w-[46ch] text-sm leading-relaxed text-ink-soft">
          {children}
        </p>
      </section>
    </div>
  );
}

export default function UsersTab() {
  const { scan, filterModules, filterUsers, scanConfig } = useAppState();
  const minRecords = scanConfig?.rules?.minRecordsPerUser ?? 25;
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
  const insight = useMemo(
    () => recordsNeedingActionInsight(owners, minRecords),
    [minRecords, owners]
  );

  if (!hasOwnerAnalytics) {
    return (
      <UsersEmpty title="User analytics were not measured">
        Run a new scan after this feature was deployed.
      </UsersEmpty>
    );
  }

  if (!owners.length) {
    return (
      <UsersEmpty title="No users match the current filters">
        Clear the Users or Modules filter.
      </UsersEmpty>
    );
  }

  return (
    <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <UserQualityTable owners={owners} minRecords={minRecords} insight={insight} />
    </div>
  );
}
