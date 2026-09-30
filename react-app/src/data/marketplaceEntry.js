// Marketplace Web Tab entry is a UX flag only. It never authenticates
// or authorizes. Org/user/installation query values are ignored.

export const MARKETPLACE_SOURCE = "marketplace";
export const MARKETPLACE_SOURCE_PARAM = "source";
export const MARKETPLACE_ENTRY_COOKIE = "dhs-marketplace-entry";
const STORAGE_KEY = "dhs-marketplace-entry";
const IGNORED_QUERY_KEYS = new Set(["org_id", "user_id", "installation_id"]);

let capturedMarketplaceEntry = false;

function searchParams(search = currentLocationSearch()) {
  const value = String(search || "");
  return new URLSearchParams(value.startsWith("?") ? value.slice(1) : value);
}

function currentLocationSearch() {
  const search = window.location.search || "";
  if (search) return search;
  try {
    return new URL(window.location.href).search || "";
  } catch {
    return "";
  }
}

function hasExplicitMarketplaceSource(search = currentLocationSearch()) {
  return searchParams(search).get(MARKETPLACE_SOURCE_PARAM) === MARKETPLACE_SOURCE;
}

function dropIgnoredQueryParams(params) {
  for (const key of IGNORED_QUERY_KEYS) {
    params.delete(key);
  }
  return params;
}

function cookieSecureSuffix() {
  return window.location.protocol === "https:" ? "; Secure" : "";
}

function readMarketplaceCookie() {
  try {
    return document.cookie.split(";").some((part) => {
      const [name, value] = part.trim().split("=");
      return name === MARKETPLACE_ENTRY_COOKIE && value === "1";
    });
  } catch {
    return false;
  }
}

function writeMarketplaceCookie() {
  try {
    document.cookie = `${MARKETPLACE_ENTRY_COOKIE}=1; path=/; SameSite=Lax${cookieSecureSuffix()}`;
  } catch {
    // Ignore unavailable cookies.
  }
}

function clearMarketplaceCookie() {
  try {
    document.cookie = `${MARKETPLACE_ENTRY_COOKIE}=; path=/; max-age=0; SameSite=Lax${cookieSecureSuffix()}`;
  } catch {
    // Ignore unavailable cookies.
  }
}

export function resetMarketplaceEntryCapture() {
  capturedMarketplaceEntry = false;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore unavailable storage.
  }
  clearMarketplaceCookie();
}

export function hasCapturedMarketplaceEntry() {
  if (capturedMarketplaceEntry) {
    return true;
  }
  try {
    if (window.sessionStorage.getItem(STORAGE_KEY) === "1") {
      return true;
    }
  } catch {
    // Fall through to cookie.
  }
  return readMarketplaceCookie();
}

function persistMarketplaceCapture() {
  capturedMarketplaceEntry = true;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, "1");
  } catch {
    // Memory capture still selects Marketplace consent if storage is blocked.
  }
  writeMarketplaceCookie();
}

export function captureMarketplaceEntry(search = currentLocationSearch()) {
  if (
    hasExplicitMarketplaceSource(search) ||
    hasExplicitMarketplaceSource(currentLocationSearch())
  ) {
    persistMarketplaceCapture();
  } else if (hasCapturedMarketplaceEntry()) {
    persistMarketplaceCapture();
  }
}

export function isMarketplaceEntry(search = currentLocationSearch()) {
  return hasExplicitMarketplaceSource(search) || hasCapturedMarketplaceEntry();
}

export function searchForNavigation(search = currentLocationSearch()) {
  const params = dropIgnoredQueryParams(searchParams(search));
  if (isMarketplaceEntry(search)) {
    params.set(MARKETPLACE_SOURCE_PARAM, MARKETPLACE_SOURCE);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function pathnameWithoutIndexHtml(pathname = window.location.pathname) {
  if (pathname.endsWith("/index.html")) {
    return pathname.slice(0, -"index.html".length);
  }
  if (pathname.endsWith("index.html")) {
    return pathname.slice(0, -"index.html".length) || "/";
  }
  return pathname;
}

export function restoreMarketplaceSearch() {
  if (!hasCapturedMarketplaceEntry()) {
    return false;
  }
  const path = pathnameWithoutIndexHtml();
  const nextSearch = searchForNavigation();
  const next = `${path}${nextSearch}${window.location.hash}`;
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (current === next) {
    return false;
  }
  window.history.replaceState(window.history.state, "", next);
  return true;
}

export function marketplaceAppHref(origin = window.location.origin) {
  return `${origin}/app/?${MARKETPLACE_SOURCE_PARAM}=${MARKETPLACE_SOURCE}`;
}

export function isFramed() {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}

export function launchMarketplaceAppIfFramed() {
  if (!isMarketplaceEntry() || !isFramed()) {
    return false;
  }
  const target = marketplaceAppHref();
  try {
    window.top.location.assign(target);
  } catch {
    window.open(target, "_top");
  }
  return true;
}
