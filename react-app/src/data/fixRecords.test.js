import { describe, expect, it } from "vitest";
import {
  FIX_PAGE_SIZE,
  cellValue,
  isFixIndexUnavailable,
  issueMessage,
  normalizeFixRecords,
} from "./fixRecords";

const RAW = {
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
  kpis: { affectedRecordCount: 198, issueCount: 612 },
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
        },
      ],
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
        },
      ],
    },
  ],
};

describe("normalizeFixRecords", () => {
  it("preserves actual cell values and maps issues separately", () => {
    const mapped = normalizeFixRecords(RAW);
    expect(mapped.rows[0].cells.Email).toBe("john.smith@");
    expect(mapped.rows[0].cells.Email).not.toMatch(/invalid/i);
    expect(mapped.rows[0].issues[0].message).toBe("Invalid email");
    expect(mapped.rows[0].issuesByField.Email[0].issueType).toBe("INVALID_EMAIL");
    expect(cellValue(mapped.rows[0].cells, "Email")).toBe("john.smith@");
  });

  it("keeps empty CRM values empty instead of substituting a label", () => {
    const mapped = normalizeFixRecords(RAW);
    expect(mapped.rows[1].cells.Email).toBe("");
    expect(mapped.rows[1].issues[0].message).toBe("Missing value");
  });

  it("forces fixedCount to 0", () => {
    const mapped = normalizeFixRecords({
      ...RAW,
      kpis: { affectedRecordCount: 10, issueCount: 12, fixedCount: 9 },
    });
    expect(mapped.kpis).toEqual({
      affectedRecordCount: 10,
      issueCount: 12,
      fixedCount: 0,
    });
    expect(mapped.pageSize).toBe(FIX_PAGE_SIZE);
  });

  it("does not replace defect labels into cell values", () => {
    const mapped = normalizeFixRecords({
      ...RAW,
      rows: [
        {
          crmRecordId: "1",
          cells: { Phone: "12345" },
          issues: [
            {
              fieldApiName: "Phone",
              issueType: "INVALID_PHONE",
              messageCode: "INVALID_PHONE_FORMAT",
            },
          ],
        },
      ],
    });
    expect(mapped.rows[0].cells.Phone).toBe("12345");
    expect(mapped.rows[0].issues[0].message).toBe("Invalid phone");
  });
});

describe("issueMessage", () => {
  it("maps known codes without using the cell value", () => {
    expect(issueMessage({ issueType: "INVALID_URL", messageCode: "INVALID_URL_FORMAT" })).toBe(
      "Invalid URL"
    );
    expect(issueMessage({ issueType: "MISSING_VALUE" })).toBe("Missing value");
  });
});

describe("isFixIndexUnavailable", () => {
  it("detects the 409 Fix index error", () => {
    expect(isFixIndexUnavailable({ code: "FIX_INDEX_UNAVAILABLE", status: 409 })).toBe(true);
    expect(isFixIndexUnavailable({ message: "failed" })).toBe(false);
  });
});
