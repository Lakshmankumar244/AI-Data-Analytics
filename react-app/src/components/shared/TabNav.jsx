import { TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContentContainer } from "../layout";
import "./TabNav.css";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "users", label: "Users" },
  { id: "modules", label: "Modules" },
  { id: "trend", label: "Trend" },
  { id: "records", label: "Records" },
  { id: "fix", label: "Fix" },
];

/*
  Renders the tab list for the Tabs root that ReportShell owns, so the triggers
  and the panel share one Radix context: arrow-key navigation, roving focus and
  the aria wiring between tab and panel come from that rather than from a set
  of plain buttons.

  Each tab still resolves to a report component in ReportShell.
*/
export default function TabNav() {
  return (
    <div className="tab-nav">
      <ContentContainer className="tab-nav-inner">
        <TabsList className="tab-nav-list" aria-label="Report sections">
          {TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id} className="tab-nav-item">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </ContentContainer>
    </div>
  );
}
