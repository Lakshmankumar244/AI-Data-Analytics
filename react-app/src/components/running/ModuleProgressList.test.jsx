import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ModuleProgressList from "./ModuleProgressList";
import {
  deriveModuleStage,
  moduleDisplayProgress,
} from "./scanStage";

describe("ModuleProgressList READY_TO_DOWNLOAD", () => {
  it("shows ready to download and 0 / 5 when nothing is downloaded", () => {
    const module = {
      moduleApiName: "Account",
      status: "READY_TO_DOWNLOAD",
      expectedRecordCount: 5,
      recordsDownloaded: 0,
      recordsProcessed: 0,
      bulkJobs: [{ status: "READY_TO_DOWNLOAD", providerRecordCount: 5 }],
    };
    const display = moduleDisplayProgress(module, { isActive: true });
    render(
      <ModuleProgressList
        modules={[{ apiName: "Account", label: "Accounts" }]}
        progress={{
          Account: {
            scanned: display.scanned,
            estimatedTotal: display.estimatedTotal,
            hasKnownTotal: display.hasKnownTotal,
            phase: deriveModuleStage(module).id,
            percent: display.percent,
          },
        }}
        completed={[]}
        activeModule="Account"
      />
    );

    expect(screen.getByText("Ready to download")).toBeInTheDocument();
    expect(screen.getByText("0 / 5 records")).toBeInTheDocument();
    expect(screen.queryByText("Downloading data")).not.toBeInTheDocument();
    expect(screen.queryByText("3 / 5 records")).not.toBeInTheDocument();
  });
});
