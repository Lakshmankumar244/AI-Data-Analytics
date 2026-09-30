import { afterEach, describe, expect, it, vi } from "vitest";
import {
  downloadFixExportFile,
  fixExportFileUrl,
  getFixExport,
  startFixExport,
} from "./client";

describe("Fix export client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("enqueues the current filters without sending rows", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        scanId: "scan_1",
        exportId: "task_1",
        taskStatus: "QUEUED",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await startFixExport("scan_1", {
      module: "Leads",
      q: "Acme",
      owners: ["owner_a"],
      severity: "HIGH",
      issueType: "INVALID_EMAIL",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/server/ai_data_analytics_function/api/scans/scan_1/fix-export",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({
          module: "Leads",
          q: "Acme",
          owners: ["owner_a"],
          severity: "HIGH",
          issueType: "INVALID_EMAIL",
        }),
      })
    );
    expect(result.exportId).toBe("task_1");
  });

  it("polls export status and downloads through the backend file route", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          scanId: "scan_1",
          exportId: "task_1",
          taskStatus: "SUCCEEDED",
          ready: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name) =>
            name === "Content-Disposition" ? 'attachment; filename="fix-Leads-task_1.xlsx"' : null,
        },
        blob: async () => new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:fix-export");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.fn();
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "a") {
        return { href: "", download: "", rel: "", click, remove: vi.fn() };
      }
      return realCreate(tag);
    });
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => node);

    await expect(getFixExport("scan_1", "task_1")).resolves.toMatchObject({
      ready: true,
      taskStatus: "SUCCEEDED",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/server/ai_data_analytics_function/api/scans/scan_1/fix-export/task_1",
      { credentials: "same-origin" }
    );
    expect(fixExportFileUrl("scan_1", "task_1")).toBe(
      "/server/ai_data_analytics_function/api/scans/scan_1/fix-export/task_1/file"
    );

    const filename = await downloadFixExportFile("scan_1", "task_1");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/server/ai_data_analytics_function/api/scans/scan_1/fix-export/task_1/file",
      { credentials: "same-origin" }
    );
    expect(filename).toBe("fix-Leads-task_1.xlsx");
    expect(click).toHaveBeenCalled();
  });
});
