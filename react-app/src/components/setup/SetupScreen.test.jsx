import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import SetupScreen from "./SetupScreen";
import {
  renderWithApp,
  SALESFORCE_CONNECTION,
  SALESFORCE_METADATA,
  ZOHO_CONNECTION,
} from "../../test/appHarness";
import { defaultScanConfig } from "../../state/initialState";
import * as api from "../../data/client";

vi.mock("../../data/client", async () => {
  const actual = await vi.importActual("../../data/client");
  return {
    ...actual,
    getSalesforceMetadata: vi.fn(),
    startScan: vi.fn(),
    getScorecard: vi.fn(),
  };
});

describe("SetupScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    api.startScan.mockResolvedValue({
      scanId: "scan_1",
      status: "CREATED",
      reused: false,
    });
  });

  it("keeps the existing Zoho configuration flow", async () => {
    renderWithApp(<SetupScreen />, {
      state: {
        connection: ZOHO_CONNECTION,
        salesforceConnection: null,
        scanConfig: { ...defaultScanConfig, modules: [] },
      },
    });

    expect(await screen.findByText("Zoho Org")).toBeInTheDocument();
    expect(await screen.findByText("Deals")).toBeInTheDocument();
    expect(screen.queryByText("Opportunity")).not.toBeInTheDocument();
    expect(screen.getByText(/API credits/i)).toBeInTheDocument();
    expect(api.getSalesforceMetadata).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Start scan" })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "Start scan" }));

    await waitFor(() => {
      expect(api.startScan).toHaveBeenCalledTimes(1);
    });
    const payload = api.startScan.mock.calls[0][0];
    expect(payload.modules).toEqual(["Leads", "Contacts", "Deals", "Accounts"]);
    expect(payload.depth).toBe("presales");
    expect(payload.clock).toBe("created");
    expect(payload.range).toEqual({ id: "90d", from: null, to: null });
  });

  it("loads Salesforce metadata and starts a scan with native object API names", async () => {
    api.getSalesforceMetadata.mockResolvedValue(SALESFORCE_METADATA);

    renderWithApp(<SetupScreen />, {
      state: {
        connection: null,
        salesforceConnection: SALESFORCE_CONNECTION,
        scanConfig: { ...defaultScanConfig, modules: [] },
      },
    });

    expect(await screen.findByText("Acme Production")).toBeInTheDocument();
    expect(api.getSalesforceMetadata).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /3 modules selected/i })
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Start scan" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: /3 modules selected/i }));
    const list = screen.getByRole("group", {
      name: "Modules to include in the scan",
    });
    expect(within(list).getByText("Account")).toBeInTheDocument();
    expect(within(list).getByText("Contact")).toBeInTheDocument();
    expect(within(list).getByText("Opportunity")).toBeInTheDocument();
    expect(within(list).queryByText("Deals")).not.toBeInTheDocument();
    expect(screen.queryByText(/API credits/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Select all"));
    fireEvent.click(within(list).getByLabelText("Account"));

    const start = screen.getByRole("button", { name: "Start scan" });
    expect(start).toBeEnabled();
    fireEvent.click(start);

    await waitFor(() => {
      expect(api.startScan).toHaveBeenCalledTimes(1);
    });
    const payload = api.startScan.mock.calls[0][0];
    expect(payload.modules).toEqual(["Account"]);
    expect(payload.modules).not.toContain("Deals");
    expect(payload.modules).not.toContain("Accounts");
    expect(payload.depth).toBe("presales");
    expect(payload.clock).toBe("created");
    expect(payload.range).toEqual({ id: "90d", from: null, to: null });
  });
});
