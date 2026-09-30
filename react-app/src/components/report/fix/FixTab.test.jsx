import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import FixTab from "./FixTab";
import { renderWithApp } from "../../../test/appHarness";
import * as api from "../../../data/client";

vi.mock("../../../data/client", async () => {
  const actual = await vi.importActual("../../../data/client");
  return {
    ...actual,
    getFixRecords: vi.fn(),
    getFixPlan: vi.fn(),
    startFixExport: vi.fn(),
    getFixExport: vi.fn(),
    downloadFixExportFile: vi.fn(),
  };
});

const SCAN = {
  scanId: "scan_1",
  moduleFindings: [{ apiName: "Leads", label: "Leads" }],
  moduleAnalytics: [
    {
      moduleApiName: "Leads",
      ownerAnalytics: [
        {
          data: {
            ownerKey: "owner_a",
            ownerName: "Ada Lovelace",
            recordCount: 12,
          },
        },
      ],
    },
  ],
};

const PAGE = {
  scanId: "scan_1",
  module: "Leads",
  measured: true,
  schemaVersion: "record-findings-v5",
  pageSize: 20,
  nextCursor: "29",
  hasMore: true,
  columns: [
    { apiName: "Email", label: "Email" },
    { apiName: "Company", label: "Company" },
  ],
  kpis: { affectedRecordCount: 198, issueCount: 612, fixedCount: 0 },
  rows: [
    {
      crmRecordId: "crm_001",
      displayName: "Acme Lead",
      ownerKey: "owner_a",
      cells: { Email: "john.smith@", Company: "Acme" },
      issues: [
        {
          fieldApiName: "Email",
          issueType: "INVALID_EMAIL",
          severity: "HIGH",
          messageCode: "INVALID_EMAIL_FORMAT",
          fieldLabel: "Email",
          message: "Invalid email",
        },
      ],
      issuesByField: {
        Email: [
          {
            fieldApiName: "Email",
            issueType: "INVALID_EMAIL",
            severity: "HIGH",
            messageCode: "INVALID_EMAIL_FORMAT",
            fieldLabel: "Email",
            message: "Invalid email",
          },
        ],
      },
    },
    {
      crmRecordId: "crm_002",
      displayName: "Northwind",
      ownerKey: "",
      cells: { Email: "", Company: "Northwind" },
      issues: [
        {
          fieldApiName: "Email",
          issueType: "MISSING_VALUE",
          severity: "MEDIUM",
          messageCode: "BUSINESS_CRITICAL_VALUE_MISSING",
          fieldLabel: "Email",
          message: "Missing value",
        },
      ],
      issuesByField: {
        Email: [
          {
            fieldApiName: "Email",
            issueType: "MISSING_VALUE",
            severity: "MEDIUM",
            messageCode: "BUSINESS_CRITICAL_VALUE_MISSING",
            fieldLabel: "Email",
            message: "Missing value",
          },
        ],
      },
    },
  ],
};

function renderFixTab() {
  return renderWithApp(<FixTab />, {
    state: {
      phase: "report",
      scanId: "scan_1",
      tab: "fix",
      scan: SCAN,
    },
  });
}

describe("FixTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getFixRecords.mockResolvedValue(PAGE);
  });

  it("loads the defective-record grid instead of the remediation plan", async () => {
    renderFixTab();
    expect(await screen.findByText("john.smith@")).toBeInTheDocument();
    expect(screen.getByText("Acme Lead")).toBeInTheDocument();
    expect(screen.getByText("Invalid email")).toBeInTheDocument();
    expect(screen.queryByText("Remediation plan")).not.toBeInTheDocument();
    expect(api.getFixPlan).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Export XLSX" })).toBeInTheDocument();
    expect(api.getFixRecords).toHaveBeenCalledWith(
      "scan_1",
      expect.objectContaining({
        module: "Leads",
        pageSize: 20,
        cursor: null,
      })
    );
  });

  it("keeps the actual CRM value visible and shows — for empty values", async () => {
    renderFixTab();
    expect(await screen.findByText("john.smith@")).toBeInTheDocument();
    const emailCell = screen.getByText("john.smith@").closest("td");
    expect(within(emailCell).queryByText(/^Invalid$/)).not.toBeInTheDocument();
    expect(screen.getByText("Missing value")).toBeInTheDocument();
    const missingCell = screen.getByText("Missing value").closest("td");
    expect(within(missingCell).getByText("—")).toBeInTheDocument();
  });

  it("places Export XLSX in the page header and Search on the table toolbar", async () => {
    renderFixTab();
    await screen.findByText("john.smith@");
    expect(screen.getAllByRole("button", { name: "Export XLSX" })).toHaveLength(1);
    expect(screen.getAllByRole("searchbox", { name: "Search records" })).toHaveLength(1);
    const heading = screen.getByRole("heading", { name: /Fix · 198/ });
    const toolbar = heading.parentElement;
    expect(within(toolbar).getByRole("searchbox", { name: "Search records" })).toBeInTheDocument();
    expect(within(toolbar).queryByRole("button", { name: "Export XLSX" })).not.toBeInTheDocument();
  });

  it("shows API KPIs and keeps Fixed at 0", async () => {
    renderFixTab();
    expect(await screen.findByText("Defective records")).toBeInTheDocument();
    expect(screen.getByText("198")).toBeInTheDocument();
    expect(screen.getByText("612")).toBeInTheDocument();
    expect(screen.getByText("Fixed")).toBeInTheDocument();
    expect(screen.getByText("This app does not write back to CRM")).toBeInTheDocument();
  });

  it("uses cursor pagination without page numbers", async () => {
    api.getFixRecords
      .mockResolvedValueOnce(PAGE)
      .mockResolvedValueOnce({ ...PAGE, nextCursor: null, hasMore: false, rows: [PAGE.rows[1]] });
    renderFixTab();
    const next = await screen.findByRole("button", { name: "Next" });
    expect(screen.queryByText(/Page \d/)).not.toBeInTheDocument();
    fireEvent.click(next);
    await waitFor(() => {
      expect(api.getFixRecords).toHaveBeenLastCalledWith(
        "scan_1",
        expect.objectContaining({ cursor: "29", module: "Leads" })
      );
    });
  });

  it("resets the cursor when search changes", async () => {
    api.getFixRecords
      .mockResolvedValueOnce(PAGE)
      .mockResolvedValueOnce({ ...PAGE, hasMore: false, nextCursor: null });
    renderFixTab();
    await screen.findByText("john.smith@");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(api.getFixRecords).toHaveBeenCalledWith(
        "scan_1",
        expect.objectContaining({ cursor: "29" })
      );
    });
    const search = screen.getByRole("searchbox", { name: "Search records" });
    fireEvent.change(search, { target: { value: "North" } });
    fireEvent.submit(search.closest("form"));
    await waitFor(() => {
      expect(api.getFixRecords).toHaveBeenLastCalledWith(
        "scan_1",
        expect.objectContaining({ q: "North", cursor: null })
      );
    });
  });

  it("shows an explicit re-run state when the Fix index is missing", async () => {
    const failure = new Error("Re-run the scan to use Fix");
    failure.code = "FIX_INDEX_UNAVAILABLE";
    failure.status = 409;
    api.getFixRecords.mockRejectedValue(failure);
    renderFixTab();
    expect(await screen.findByText("Re-run scan to use Fix")).toBeInTheDocument();
    expect(screen.queryByText("Remediation plan")).not.toBeInTheDocument();
  });

  it("shows the empty filtered state", async () => {
    api.getFixRecords.mockResolvedValue({
      ...PAGE,
      rows: [],
      hasMore: false,
      nextCursor: null,
    });
    renderFixTab();
    expect(await screen.findByText("No matching records")).toBeInTheDocument();
  });
});
