import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import HomeScreen from "./HomeScreen";
import {
  renderWithApp,
  SALESFORCE_CONNECTION,
  ZOHO_CONNECTION,
} from "../../test/appHarness";
import * as api from "../../data/client";

vi.mock("../../data/client", async () => {
  const actual = await vi.importActual("../../data/client");
  return {
    ...actual,
    getScanHistory: vi.fn(),
    getScorecard: vi.fn(),
    activateConnection: vi.fn(),
    advanceScan: vi.fn(),
  };
});

describe("HomeScreen Salesforce scan entry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getScanHistory.mockResolvedValue({ scans: [] });
    api.advanceScan.mockResolvedValue({
      scanId: "scan_1f09354578c7422c82d8f18d8a161052",
      currentStatus: "CREATED",
      submitted: true,
    });
  });

  it("does not block Salesforce scan creation", async () => {
    renderWithApp(<HomeScreen />, {
      state: {
        phase: "home",
        connection: null,
        salesforceConnection: SALESFORCE_CONNECTION,
      },
    });

    expect(
      screen.queryByText("Salesforce scanning is not available yet")
    ).not.toBeInTheDocument();
    const newScan = await screen.findByRole("button", { name: "New scan" });
    expect(newScan).toBeEnabled();
  });

  it("still offers New scan when Zoho is active", async () => {
    renderWithApp(<HomeScreen />, {
      state: {
        phase: "home",
        connection: ZOHO_CONNECTION,
        salesforceConnection: null,
      },
    });

    expect(await screen.findByRole("button", { name: "New scan" })).toBeEnabled();
    expect(
      screen.queryByText("Salesforce scanning is not available yet")
    ).not.toBeInTheDocument();
  });

  it("Resume posts /advance instead of only changing local UI state", async () => {
    const scan = {
      scanId: "scan_1f09354578c7422c82d8f18d8a161052",
      status: "CREATED",
      modules: ["Account"],
      depth: "presales",
      clock: "Created_Time",
      fromUtc: null,
      toUtc: "2026-09-16T12:00:00Z",
      hasResults: false,
      connection: {
        connectionId: "sf-1",
        organizationName: "Acme Production",
        email: "pat@example.com",
      },
    };
    api.getScanHistory.mockResolvedValue({ scans: [scan] });

    renderWithApp(<HomeScreen />, {
      state: {
        phase: "home",
        connection: null,
        salesforceConnection: SALESFORCE_CONNECTION,
        scanHistory: [scan],
      },
    });

    const resume = await screen.findByRole("button", { name: "Resume" });
    fireEvent.click(resume);

    await waitFor(() => {
      expect(api.advanceScan).toHaveBeenCalledWith(
        "scan_1f09354578c7422c82d8f18d8a161052"
      );
    });
    expect(api.getScorecard).not.toHaveBeenCalled();
  });
});
