import { describe, expect, it } from "vitest";
import {
  defaultAccessibleModuleNames,
  retainedAccessibleModules,
  salesforceAccessibleModules,
  salesforceOrganizationName,
} from "./scanSetup";

describe("salesforceAccessibleModules", () => {
  it("keeps native Salesforce API names and does not map Opportunity to Deals", () => {
    const modules = salesforceAccessibleModules({
      objects: [
        { apiName: "Account", label: "Accounts" },
        { apiName: "Contact", label: "Contacts" },
        { apiName: "Opportunity", label: "Opportunities" },
      ],
    });
    expect(modules.map((module) => module.apiName)).toEqual([
      "Account",
      "Contact",
      "Opportunity",
    ]);
    expect(modules.map((module) => module.label)).toEqual([
      "Account",
      "Contact",
      "Opportunity",
    ]);
    expect(modules.some((module) => module.apiName === "Deals")).toBe(false);
  });

  it("reads the Salesforce organization name from metadata", () => {
    expect(
      salesforceOrganizationName(
        { organization: { name: "Acme Production" } },
        "Stored Org"
      )
    ).toBe("Acme Production");
  });

  it("drops persisted Zoho module names from a Salesforce selection", () => {
    const accessible = salesforceAccessibleModules({
      objects: [{ apiName: "Account" }, { apiName: "Opportunity" }],
    });
    expect(
      retainedAccessibleModules(["Deals", "Account", "Leads"], accessible)
    ).toEqual(["Account"]);
    expect(defaultAccessibleModuleNames(accessible)).toEqual([
      "Account",
      "Opportunity",
    ]);
  });
});
