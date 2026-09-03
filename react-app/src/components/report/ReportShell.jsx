import { useAppState, useActions } from "../../state/AppContext";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { ContentContainer, StickyHeaderStack } from "../layout";
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

  /*
    The Tabs root spans the whole report so the tab list in the sticky header
    and the panel below it belong to the same Radix context. Selection still
    lives in app state - Tabs is driven by it, not the other way round.
  */
  return (
    <Tabs value={tab} onValueChange={setTab} className="report-shell">
      <StickyHeaderStack>
        <FilterBar />
        <TabNav />
      </StickyHeaderStack>
      <ContentContainer className="report-shell-body">
        <TabsContent value={tab} className="report-shell-panel">
          {ActiveTab ? <ActiveTab /> : <ComingSoonPanel tabLabel="Users" />}
        </TabsContent>
      </ContentContainer>
    </Tabs>
  );
}
