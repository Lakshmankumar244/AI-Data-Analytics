import { useAppState } from "../../state/AppContext";
import { ContentContainer, StickyHeaderStack } from "../layout";
import FilterBar from "../shared/FilterBar";
import ComingSoonPanel from "./ComingSoonPanel";
import OverviewTab from "./overview/OverviewTab";
import ModulesTab from "./modules/ModulesTab";
import TrendTab from "./trend/TrendTab";
import RecordsTab from "./records/RecordsTab";
import FixTab from "./fix/FixTab";
import UsersTab from "./users/UsersTab";
import "./ReportShell.css";

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
  const ActiveTab = TAB_COMPONENTS[tab];

  return (
    <div className="report-shell">
      <StickyHeaderStack>
        <FilterBar />
      </StickyHeaderStack>
      <ContentContainer className="report-shell-body">
        <div className="report-shell-panel" data-export-root>
          {ActiveTab ? <ActiveTab /> : <ComingSoonPanel tabLabel="Users" />}
        </div>
      </ContentContainer>
    </div>
  );
}
