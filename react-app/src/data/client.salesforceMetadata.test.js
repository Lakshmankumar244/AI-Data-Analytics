import { afterEach, describe, expect, it, vi } from "vitest";
import { getSalesforceMetadata } from "./client";

describe("getSalesforceMetadata", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls GET /api/salesforce/metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        organization: { name: "Acme Production" },
        objects: [{ apiName: "Account", label: "Account" }],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getSalesforceMetadata()).resolves.toEqual({
      organization: { name: "Acme Production" },
      objects: [{ apiName: "Account", label: "Account" }],
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/server/ai_data_analytics_function/api/salesforce/metadata",
      { credentials: "same-origin" }
    );
  });
});
