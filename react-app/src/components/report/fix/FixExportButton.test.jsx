import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import FixExportButton from "./FixExportButton";
import { renderWithApp } from "../../../test/appHarness";
import * as api from "../../../data/client";

vi.mock("../../../data/client", async () => {
  const actual = await vi.importActual("../../../data/client");
  return {
    ...actual,
    startFixExport: vi.fn(),
    getFixExport: vi.fn(),
    downloadFixExportFile: vi.fn(),
  };
});

const FILTERS = {
  module: "Leads",
  q: "Acme",
  owners: ["owner_a"],
  severity: "HIGH",
  issueType: "INVALID_EMAIL",
};

describe("FixExportButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("queues the current filters then downloads after the worker succeeds", async () => {
    api.startFixExport.mockResolvedValue({
      exportId: "task_1",
      taskStatus: "QUEUED",
    });
    api.getFixExport.mockResolvedValue({
      exportId: "task_1",
      taskStatus: "SUCCEEDED",
      ready: true,
    });
    api.downloadFixExportFile.mockResolvedValue("fix-Leads-task_1.xlsx");

    renderWithApp(
      <FixExportButton scanId="scan_1" filters={FILTERS} />,
      { state: { phase: "report", scanId: "scan_1", tab: "fix" } }
    );
    fireEvent.click(screen.getByRole("button", { name: "Export XLSX" }));

    await waitFor(() => {
      expect(api.startFixExport).toHaveBeenCalledWith("scan_1", FILTERS);
    });
    await waitFor(() => {
      expect(api.downloadFixExportFile).toHaveBeenCalledWith("scan_1", "task_1");
    });
  });

  it("downloads immediately when the same export already succeeded", async () => {
    api.startFixExport.mockResolvedValue({
      exportId: "task_done",
      taskStatus: "SUCCEEDED",
      alreadyExported: true,
    });
    api.downloadFixExportFile.mockResolvedValue("fix-Leads-task_done.xlsx");

    renderWithApp(<FixExportButton scanId="scan_1" filters={FILTERS} />);
    fireEvent.click(screen.getByRole("button", { name: "Export XLSX" }));

    await waitFor(() => {
      expect(api.downloadFixExportFile).toHaveBeenCalledWith("scan_1", "task_done");
    });
    expect(api.getFixExport).not.toHaveBeenCalled();
  });
});
