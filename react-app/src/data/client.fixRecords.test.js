import { afterEach, describe, expect, it, vi } from "vitest";
import { getFixRecords } from "./client";

describe("getFixRecords", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls GET /api/scans/{id}/fix-records with cursor filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        scanId: "scan_1",
        module: "Leads",
        measured: true,
        schemaVersion: "record-findings-v5",
        pageSize: 20,
        nextCursor: "40",
        hasMore: true,
        columns: [{ apiName: "Email", label: "Email" }],
        kpis: { affectedRecordCount: 198, issueCount: 612 },
        rows: [
          {
            crmRecordId: "crm_001",
            displayName: "Acme",
            cells: { Email: "john.smith@" },
            issues: [
              {
                fieldApiName: "Email",
                issueType: "INVALID_EMAIL",
                messageCode: "INVALID_EMAIL_FORMAT",
              },
            ],
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getFixRecords("scan_1", {
      module: "Leads",
      cursor: "21",
      pageSize: 20,
      q: "Acme",
      owners: ["owner_a"],
      severity: "HIGH",
      issueType: "INVALID_EMAIL",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/server/ai_data_analytics_function/api/scans/scan_1/fix-records?module=Leads&cursor=21&pageSize=20&q=Acme&owners=owner_a&severity=HIGH&issueType=INVALID_EMAIL",
      { credentials: "same-origin" }
    );
    expect(result.rows[0].cells.Email).toBe("john.smith@");
    expect(result.kpis.fixedCount).toBe(0);
  });

  it("surfaces FIX_INDEX_UNAVAILABLE without fetching more pages", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        error: {
          code: "FIX_INDEX_UNAVAILABLE",
          message: "Re-run the scan to use Fix",
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getFixRecords("scan_old", { module: "Leads" })).rejects.toMatchObject({
      code: "FIX_INDEX_UNAVAILABLE",
      status: 409,
    });
  });
});
