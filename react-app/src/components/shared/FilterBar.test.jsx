import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import FilterBar from "./FilterBar";
import { renderWithApp } from "../../test/appHarness";

const SCAN = {
  scanId: "scan_1",
  moduleFindings: [{ apiName: "Leads", label: "Leads" }],
  moduleAnalytics: [],
};

describe("FilterBar Fix tab export", () => {
  it("hides the generic CSV Export control on the Fix tab", () => {
    renderWithApp(<FilterBar />, {
      state: {
        phase: "report",
        scanId: "scan_1",
        tab: "fix",
        scan: SCAN,
      },
    });
    expect(screen.queryByRole("button", { name: /Export/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Print" })).toBeInTheDocument();
  });

  it("keeps the generic Export control on other report tabs", () => {
    renderWithApp(<FilterBar />, {
      state: {
        phase: "report",
        scanId: "scan_1",
        tab: "records",
        scan: SCAN,
      },
    });
    expect(screen.getByRole("button", { name: /Export/ })).toBeInTheDocument();
  });
});
