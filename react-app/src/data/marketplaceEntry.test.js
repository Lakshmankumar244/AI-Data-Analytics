import { afterEach, describe, expect, it, vi } from "vitest";
import {
  captureMarketplaceEntry,
  isMarketplaceEntry,
  launchMarketplaceAppIfFramed,
  marketplaceAppHref,
  restoreMarketplaceSearch,
  searchForNavigation,
} from "./marketplaceEntry";
import { ZOHO_MARKETPLACE_CONSENT_URL, zohoConsentUrl } from "./client";
import { navigateTo, pathFor } from "../navigation";

describe("marketplace Web Tab entry", () => {
  afterEach(() => {
    window.sessionStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.unstubAllGlobals();
  });

  it("explicit /app/?source=marketplace captures Marketplace mode", () => {
    window.history.replaceState({}, "", "/app/?source=marketplace");
    captureMarketplaceEntry();
    expect(isMarketplaceEntry()).toBe(true);
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
  });

  it("standalone /app/ does not capture Marketplace mode", () => {
    window.history.replaceState({}, "", "/app/");
    captureMarketplaceEntry();
    restoreMarketplaceSearch();
    expect(isMarketplaceEntry()).toBe(false);
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
    expect(window.location.search).toBe("");
  });

  it("zohoConsentUrl recaptures Marketplace mode from /app/?source=marketplace at call time", () => {
    window.history.replaceState({}, "", "/app/?source=marketplace");
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
  });

  it("keeps Marketplace consent after connect navigation drops the query", () => {
    window.history.replaceState({}, "", "/app/?source=marketplace");
    captureMarketplaceEntry();
    window.sessionStorage.clear();
    window.history.replaceState({}, "", "/app/connect");
    expect(window.location.search).toBe("");
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
  });

  it("Marketplace state survives /app/index.html return and restores ?source=marketplace", () => {
    captureMarketplaceEntry("?source=marketplace");
    window.history.replaceState({}, "", "/app/index.html");
    expect(window.location.search).toBe("");
    expect(isMarketplaceEntry()).toBe(true);
    restoreMarketplaceSearch();
    expect(window.location.pathname).toBe("/app/");
    expect(window.location.search).toBe("?source=marketplace");
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
  });

  it("Marketplace cookie restores ?source=marketplace after login_redirect index.html", () => {
    document.cookie = "dhs-marketplace-entry=1; path=/";
    window.history.replaceState({}, "", "/app/index.html");
    captureMarketplaceEntry();
    restoreMarketplaceSearch();
    expect(isMarketplaceEntry()).toBe(true);
    expect(window.location.pathname).toBe("/app/");
    expect(window.location.search).toBe("?source=marketplace");
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
  });

  it("does not invent Marketplace state when index.html loads without a prior capture", () => {
    window.history.replaceState({}, "", "/app/index.html");
    captureMarketplaceEntry();
    restoreMarketplaceSearch();
    expect(isMarketplaceEntry()).toBe(false);
    expect(window.location.pathname).toBe("/app/index.html");
    expect(window.location.search).toBe("");
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
  });

  it("navigateTo preserves Marketplace source", () => {
    captureMarketplaceEntry("?source=marketplace");
    window.history.replaceState({}, "", "/app/index.html");
    navigateTo({ name: "setup" });
    expect(window.location.search).toBe("?source=marketplace");
    expect(window.location.pathname).toBe(pathFor({ name: "setup" }));
    navigateTo({ name: "connect" });
    expect(window.location.pathname).toBe(pathFor({ name: "connect" }));
    expect(window.location.search).toBe("?source=marketplace");
  });

  it("standalone navigation remains unchanged", () => {
    const setupPath = pathFor({ name: "setup" });
    window.history.replaceState({}, "", setupPath);
    navigateTo({ name: "setup" });
    expect(window.location.pathname).toBe(setupPath);
    expect(window.location.search).toBe("");
    navigateTo({ name: "connect" });
    expect(window.location.pathname).toBe(pathFor({ name: "connect" }));
    expect(window.location.search).toBe("");
    expect(zohoConsentUrl()).toBe(ZOHO_MARKETPLACE_CONSENT_URL);
  });

  it("org/user/installation URL parameters are ignored", () => {
    captureMarketplaceEntry(
      "?org_id=800612345&user_id=forged&installation_id=99"
    );
    expect(isMarketplaceEntry()).toBe(false);
    expect(searchForNavigation("?org_id=1&user_id=2&installation_id=3")).toBe(
      ""
    );

    captureMarketplaceEntry(
      "?source=marketplace&org_id=forged&user_id=forged&installation_id=99"
    );
    window.history.replaceState(
      {},
      "",
      "/app/index.html?source=marketplace&org_id=forged&user_id=forged&installation_id=99"
    );
    restoreMarketplaceSearch();
    expect(window.location.search).toBe("?source=marketplace");
    expect(window.location.search).not.toContain("org_id");
    expect(window.location.search).not.toContain("user_id");
    expect(window.location.search).not.toContain("installation_id");
    expect(marketplaceAppHref("https://app.example.test")).toBe(
      "https://app.example.test/app/?source=marketplace"
    );
  });

  it("breaks out of a Marketplace iframe to the top-level React app", () => {
    captureMarketplaceEntry("?source=marketplace");
    const assign = vi.fn();
    Object.defineProperty(window, "top", {
      configurable: true,
      value: { location: { assign } },
    });
    expect(launchMarketplaceAppIfFramed()).toBe(true);
    expect(assign).toHaveBeenCalledWith(
      `${window.location.origin}/app/?source=marketplace`
    );
  });

  it("does not break out of an iframe for standalone entry", () => {
    const assign = vi.fn();
    Object.defineProperty(window, "top", {
      configurable: true,
      value: { location: { assign } },
    });
    expect(launchMarketplaceAppIfFramed()).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });
});
