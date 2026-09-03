import { useAppState, useActions } from "../../state/AppContext";
import FilterBar from "../shared/FilterBar";
import TabNav from "../shared/TabNav";
import ComingSoonPanel from "./ComingSoonPanel";
import OverviewTab from "./overview/OverviewTab";
import ModulesTab from "./modules/ModulesTab";
import TrendTab from "./trend/TrendTab";
import RecordsTab from "./records/RecordsTab";
import FixTab from "./fix/FixTab";
import UsersTab from "./users/UsersTab";
import "./ReportShell.css";

// Every report tab resolves to a concrete component; the fallback protects
// against an unknown tab value restored from stale client state.
const TAB_COMPONENTS = {
  overview: OverviewTab,
  users: UsersTab,
  modules: ModulesTab,
  trend: TrendTab,
  records: RecordsTab,
  fix: FixTab,
};

export default function ReportShell() {
  const { tab } = useAppState();
  const { setTab } = useActions();

  const ActiveTab = TAB_COMPONENTS[tab];

  return (
    <div className="report-shell">
      <FilterBar />
      <TabNav active={tab} onChange={setTab} />
      <div className="report-shell-body">
        {ActiveTab ? <ActiveTab /> : <ComingSoonPanel tabLabel="Users" />}
      </div>
    </div>
  );
}
