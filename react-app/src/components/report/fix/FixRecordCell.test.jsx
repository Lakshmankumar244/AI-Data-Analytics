import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import FixRecordCell from "./FixRecordCell";
import FixRecordsTable from "./FixRecordsTable";

function renderCell(props) {
  return render(
    <table>
      <tbody>
        <tr>
          <FixRecordCell apiName="Email" {...props} />
        </tr>
      </tbody>
    </table>
  );
}

function stateBox(text) {
  return screen.getByText(text).parentElement;
}

describe("FixRecordCell", () => {
  it("renders a valid value as a normal cell", () => {
    renderCell({ value: "john.smith@example.com", issues: [] });
    const value = screen.getByText("john.smith@example.com");
    expect(value).toBeInTheDocument();
    expect(stateBox("john.smith@example.com")).toHaveClass("bg-transparent");
    expect(stateBox("john.smith@example.com")).not.toHaveClass("bg-destructive/10");
    expect(stateBox("john.smith@example.com")).not.toHaveClass("bg-attention-soft");
    expect(screen.queryByText(/invalid|missing/i)).not.toBeInTheDocument();
  });

  it("keeps an invalid CRM value visible and uses destructive styling", () => {
    renderCell({
      value: "john.smith@",
      issues: [
        {
          fieldApiName: "Email",
          issueType: "INVALID_EMAIL",
          severity: "HIGH",
          messageCode: "INVALID_EMAIL_FORMAT",
          message: "Invalid email",
        },
      ],
    });
    const value = screen.getByText("john.smith@");
    const message = screen.getByText("Invalid email");
    const cell = value.closest("td");
    expect(cell.textContent.indexOf("john.smith@")).toBeLessThan(
      cell.textContent.indexOf("Invalid email")
    );
    expect(value).not.toHaveClass("text-destructive");
    expect(stateBox("john.smith@")).toHaveClass("bg-destructive/10");
    expect(stateBox("john.smith@")).toHaveClass("border-destructive/20");
    expect(message).toHaveClass("text-destructive");
  });

  it("shows — for a medium missing value with warning styling", () => {
    renderCell({
      value: "",
      issues: [
        {
          fieldApiName: "Last_Name",
          issueType: "MISSING_VALUE",
          severity: "MEDIUM",
          messageCode: "BUSINESS_CRITICAL_VALUE_MISSING",
          message: "Missing name",
        },
      ],
    });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("Missing name")).toBeInTheDocument();
    expect(stateBox("—")).toHaveClass("bg-attention-soft");
    expect(stateBox("—")).toHaveClass("border-attention/20");
    expect(screen.getByText("Missing name")).toHaveClass("text-attention");
    expect(stateBox("—")).not.toHaveClass("bg-destructive/10");
  });

  it("uses destructive styling for a high-severity missing value", () => {
    renderCell({
      value: "",
      issues: [
        {
          fieldApiName: "Last_Name",
          issueType: "MISSING_VALUE",
          severity: "HIGH",
          messageCode: "SYSTEM_MANDATORY_VALUE_MISSING",
          message: "Missing name",
        },
      ],
    });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Missing name")).toHaveClass("text-destructive");
    expect(stateBox("—")).toHaveClass("bg-destructive/10");
    expect(stateBox("—")).toHaveClass("border-destructive/20");
    expect(stateBox("—")).not.toHaveClass("bg-attention-soft");
  });

  it("keeps a standardization value visible with warning styling", () => {
    renderCell({
      apiName: "Phone",
      value: "9876543210",
      issues: [
        {
          fieldApiName: "Phone",
          issueType: "PHONE_STANDARDIZATION",
          severity: "LOW",
          messageCode: "PHONE_NEEDS_STANDARDIZATION",
          message: "Needs standardization",
        },
      ],
    });
    expect(screen.getByText("9876543210")).toBeInTheDocument();
    expect(screen.getByText("Needs standardization")).toBeInTheDocument();
    expect(stateBox("9876543210")).toHaveClass("bg-attention-soft");
    expect(screen.getByText("Needs standardization")).toHaveClass("text-attention");
    expect(stateBox("9876543210")).not.toHaveClass("bg-destructive/10");
  });

  it("applies destructive styling to a HIGH-severity issue on an arbitrary field", () => {
    renderCell({
      apiName: "Custom_Field_X",
      value: "abc-not-valid",
      issues: [
        {
          fieldApiName: "Custom_Field_X",
          issueType: "QUALITY_ISSUE",
          severity: "HIGH",
          messageCode: "CUSTOM_QUALITY_ISSUE",
          message: "Quality issue detected",
        },
      ],
    });
    expect(screen.getByText("abc-not-valid")).toBeInTheDocument();
    expect(screen.getByText("Quality issue detected")).toHaveClass("text-destructive");
    expect(stateBox("abc-not-valid")).toHaveClass("bg-destructive/10");
    expect(stateBox("abc-not-valid")).toHaveClass("border-destructive/20");
    expect(screen.getByText("abc-not-valid").closest("td")).toHaveAttribute(
      "data-field",
      "Custom_Field_X"
    );
  });

  it("applies warning styling to a MEDIUM-severity issue on a non-Email field", () => {
    renderCell({
      apiName: "Region_Code",
      value: "XX",
      issues: [
        {
          fieldApiName: "Region_Code",
          issueType: "MISSING_VALUE",
          severity: "MEDIUM",
          messageCode: "BUSINESS_CRITICAL_VALUE_MISSING",
          message: "Missing value",
        },
      ],
    });
    expect(screen.getByText("XX")).toBeInTheDocument();
    expect(screen.getByText("Missing value")).toHaveClass("text-attention");
    expect(stateBox("XX")).toHaveClass("bg-attention-soft");
    expect(stateBox("XX")).toHaveClass("border-attention/20");
    expect(stateBox("XX")).not.toHaveClass("bg-destructive/10");
  });

  it("applies warning styling to a LOW-severity issue on a non-Phone field", () => {
    renderCell({
      apiName: "Industry",
      value: "n/a",
      issues: [
        {
          fieldApiName: "Industry",
          issueType: "MISSING_VALUE",
          severity: "LOW",
          messageCode: "OPTIONAL_VALUE_MISSING",
          message: "Missing value",
        },
      ],
    });
    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.getByText("Missing value")).toHaveClass("text-attention");
    expect(stateBox("n/a")).toHaveClass("bg-attention-soft");
    expect(stateBox("n/a")).not.toHaveClass("bg-destructive/10");
  });

  it("shows the actual value once and stacks every issue message", () => {
    renderCell({
      value: "john@",
      issues: [
        {
          fieldApiName: "Email",
          issueType: "INVALID_EMAIL",
          severity: "HIGH",
          messageCode: "INVALID_EMAIL_FORMAT",
          message: "Invalid email",
        },
        {
          fieldApiName: "Email",
          issueType: "SUSPICIOUS_VALUE",
          severity: "MEDIUM",
          messageCode: "SUSPICIOUS_VALUE",
          message: "Suspicious value",
        },
      ],
    });
    expect(screen.getByText("john@")).toBeInTheDocument();
    expect(screen.getAllByText("john@")).toHaveLength(1);
    expect(screen.getByText("Invalid email")).toBeInTheDocument();
    expect(screen.getByText("Suspicious value")).toBeInTheDocument();
    expect(screen.getByText("Invalid email")).toHaveClass("text-destructive");
    expect(screen.getByText("Suspicious value")).toHaveClass("text-attention");
  });
});

describe("FixRecordsTable clean fields", () => {
  it("leaves clean fields on a defective record visually normal", () => {
    render(
      <FixRecordsTable
        columns={[
          { apiName: "Email", label: "Email" },
          { apiName: "Phone", label: "Phone" },
        ]}
        rows={[
          {
            crmRecordId: "crm_001",
            displayName: "John Smith",
            cells: { Email: "john.smith@", Phone: "9876543210" },
            issuesByField: {
              Email: [
                {
                  fieldApiName: "Email",
                  issueType: "INVALID_EMAIL",
                  severity: "HIGH",
                  messageCode: "INVALID_EMAIL_FORMAT",
                  message: "Invalid email",
                },
              ],
            },
          },
        ]}
      />
    );

    const emailCell = screen.getByText("john.smith@").closest("td");
    const phoneCell = screen.getByText("9876543210").closest("td");
    expect(within(emailCell).getByText("Invalid email")).toBeInTheDocument();
    expect(within(phoneCell).queryByText(/invalid|missing/i)).not.toBeInTheDocument();
    expect(stateBox("9876543210")).toHaveClass("bg-transparent");
    expect(stateBox("9876543210")).not.toHaveClass("bg-destructive/10");
    expect(stateBox("9876543210")).not.toHaveClass("bg-attention-soft");
    expect(phoneCell).not.toHaveClass("bg-destructive/10");
  });
});
