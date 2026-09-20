import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import useScanAnalytics from "./useScanAnalytics";
import * as api from "../data/client";

vi.mock("../data/client", async () => {
  const actual = await vi.importActual("../data/client");
  return {
    ...actual,
    advanceScan: vi.fn(),
    getScanStatus: vi.fn(),
    getScanResults: vi.fn(),
  };
});

describe("useScanAnalytics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getScanStatus.mockResolvedValue({
      scanId: "scan_sf",
      status: "CREATED",
      modules: [{ moduleApiName: "Account", status: "PLANNED" }],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls GET /status and does not drive orchestration via /advance", async () => {
    const { result, unmount } = renderHook(() => useScanAnalytics("scan_sf"));

    await waitFor(() => {
      expect(api.getScanStatus).toHaveBeenCalledWith("scan_sf");
      expect(result.current.status?.status).toBe("CREATED");
    });
    expect(api.advanceScan).not.toHaveBeenCalled();
    unmount();
  });
});
