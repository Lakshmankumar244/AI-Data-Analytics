const PROVIDER_LABELS = {
  zoho: "Zoho CRM",
  salesforce: "Salesforce CRM",
};

export function connectionKey(provider, connectionId) {
  return `${provider}:${connectionId}`;
}

export function parseConnectionKey(value) {
  const match = /^(zoho|salesforce):(.+)$/.exec(String(value || "").trim());
  if (!match) return null;
  return { provider: match[1], connectionId: match[2] };
}

export function providerLabel(provider) {
  return PROVIDER_LABELS[provider] || provider;
}

function livePayload(value) {
  if (!value || value === "loading") return null;
  return value;
}

function connectedUserFrom(payload) {
  const user = payload?.connectedUser || {};
  return {
    id: String(user.id || ""),
    name: String(user.name || payload?.name || "").trim(),
    email: String(user.email || payload?.email || "").trim(),
  };
}

function organizationFrom(payload) {
  return {
    organizationId: String(payload?.organizationId || ""),
    organizationName: String(payload?.organizationName || ""),
  };
}

function entryIsActive(entry) {
  return entry?.isActive === true;
}

export function coalesceConnectedPayload(previous, incoming) {
  if (incoming && incoming !== "loading") return incoming;
  if (previous && previous !== "loading") return previous;
  return incoming ?? null;
}

export function adaptConnection(provider, payload, activeKey = null) {
  const live = livePayload(payload);
  if (!live) return null;
  const connectionId = String(live.connectionId || "").trim();
  if (!connectionId || (provider !== "zoho" && provider !== "salesforce")) {
    return null;
  }
  const key = connectionKey(provider, connectionId);
  return {
    provider,
    connectionId,
    connectionKey: key,
    ...organizationFrom(live),
    connectedUser: connectedUserFrom(live),
    isActive: activeKey ? key === activeKey : entryIsActive(live),
    instanceUrl: String(live.instanceUrl || ""),
  };
}

function addSwitchableConnection(items, seen, provider, entry, activeKey) {
  const connectionId = String(entry?.connectionId || "").trim();
  if (!connectionId) return;
  const key = connectionKey(provider, connectionId);
  if (seen.has(key)) return;
  seen.add(key);
  items.push({
    provider,
    connectionId,
    connectionKey: key,
    ...organizationFrom(entry),
    connectedUser: connectedUserFrom(entry),
    isActive: activeKey ? key === activeKey : entryIsActive(entry),
    instanceUrl: String(entry.instanceUrl || ""),
  });
}

export function listSwitchableConnections(
  zohoConnection,
  salesforceConnection,
  activeKey = null
) {
  const items = [];
  const seen = new Set();
  const zoho = livePayload(zohoConnection);
  if (zoho) {
    addSwitchableConnection(items, seen, "zoho", zoho, activeKey);
    for (const entry of zoho.availableConnections || []) {
      addSwitchableConnection(items, seen, "zoho", entry, activeKey);
    }
  }
  const salesforce = livePayload(salesforceConnection);
  if (salesforce) {
    addSwitchableConnection(items, seen, "salesforce", salesforce, activeKey);
    for (const entry of salesforce.availableConnections || []) {
      addSwitchableConnection(items, seen, "salesforce", entry, activeKey);
    }
  }
  return items;
}

export function deriveActiveConnection(
  zohoConnection,
  salesforceConnection,
  preferredKey = null
) {
  if (zohoConnection === "loading" || salesforceConnection === "loading") {
    return null;
  }
  const list = listSwitchableConnections(
    zohoConnection,
    salesforceConnection,
    preferredKey
  );
  if (preferredKey) {
    const preferred = list.find((item) => item.connectionKey === preferredKey);
    if (preferred) return { ...preferred, isActive: true };
  }
  const zoho = adaptConnection("zoho", zohoConnection, preferredKey);
  const salesforce = adaptConnection(
    "salesforce",
    salesforceConnection,
    preferredKey
  );
  if (zoho?.isActive && !salesforce?.isActive) return { ...zoho, isActive: true };
  if (salesforce?.isActive && !zoho?.isActive) {
    return { ...salesforce, isActive: true };
  }
  if (zoho && !salesforce) return { ...zoho, isActive: true };
  if (salesforce && !zoho) return { ...salesforce, isActive: true };
  if (zoho && salesforce) {
    if (preferredKey?.startsWith("salesforce:")) {
      return { ...salesforce, isActive: true };
    }
    return { ...zoho, isActive: true };
  }
  return null;
}

export function connectionSummary(connection) {
  if (!connection) return "";
  const user =
    connection.connectedUser?.name || connection.connectedUser?.email || "";
  const organization =
    connection.organizationName || connection.organizationId || "";
  return [organization, user].filter(Boolean).join(" · ");
}

export function activeConnectionLabels(activeConnection) {
  if (!activeConnection) return null;
  const user =
    activeConnection.connectedUser?.name ||
    activeConnection.connectedUser?.email ||
    "";
  const organization =
    activeConnection.organizationName ||
    activeConnection.organizationId ||
    "";
  const provider = providerLabel(activeConnection.provider);
  const account = [provider, user].filter(Boolean).join(" · ");
  if (!organization && !account) return null;
  return { organization, account };
}
