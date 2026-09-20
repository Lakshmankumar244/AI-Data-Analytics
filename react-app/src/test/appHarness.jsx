import { render } from "@testing-library/react";
import { AppProvider } from "../state/AppContext";
import { buildInitialState } from "../state/initialState";
import { deriveActiveConnection } from "../data/activeConnection";

export const ZOHO_CONNECTION = {
  connectionId: "zoho-1",
  isActive: true,
  organizationName: "Zoho Org",
  organizationId: "org-z",
  connectedUser: { name: "Ananya Rao", email: "ananya@example.com" },
  accessibleModules: [
    { apiName: "Leads", label: "Leads", recordCount: 214 },
    { apiName: "Contacts", label: "Contacts", recordCount: 96 },
    { apiName: "Deals", label: "Deals", recordCount: 58 },
    { apiName: "Accounts", label: "Accounts", recordCount: 41 },
  ],
};

export const SALESFORCE_CONNECTION = {
  connectionId: "sf-1",
  provider: "salesforce",
  isActive: true,
  organizationName: "Stored Org",
  organizationId: "00D5g00000OrgIdAAA",
  connectedUser: { name: "Pat Lee", email: "pat@example.com" },
};

export const SALESFORCE_METADATA = {
  connectionId: "sf-1",
  organization: {
    id: "00D5g00000OrgIdA",
    name: "Acme Production",
    timeZone: "America/Los_Angeles",
    isSandbox: false,
    organizationType: "Enterprise Edition",
  },
  objects: [
    { apiName: "Account", label: "Account" },
    { apiName: "Contact", label: "Contact" },
    { apiName: "Opportunity", label: "Opportunity" },
  ],
};

export function appState(overrides = {}) {
  const initial = {
    ...buildInitialState(),
    phase: "setup",
    connection: null,
    salesforceConnection: null,
    ...overrides,
  };
  const activeConnection =
    overrides.activeConnection === undefined
      ? deriveActiveConnection(
          initial.connection,
          initial.salesforceConnection,
          initial.activeConnectionKey
        )
      : overrides.activeConnection;
  return {
    ...initial,
    activeConnection,
    activeConnectionKey: activeConnection?.connectionKey ?? null,
  };
}

export function renderWithApp(ui, { state, ...options } = {}) {
  return render(<AppProvider initialState={appState(state)}>{ui}</AppProvider>, options);
}
