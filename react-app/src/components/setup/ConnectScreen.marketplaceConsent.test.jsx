import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import ConnectScreen from "./ConnectScreen";
import { renderWithApp } from "../../test/appHarness";
import { ZOHO_CONSENT_URL, ZOHO_MARKETPLACE_CONSENT_URL } from "../../data/client";

describe("ConnectScreen Zoho consent URL", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState({}, "", "/");
  });

  it("assigns marketplace consent from /app/?source=marketplace", () => {
    window.history.replaceState({}, "", "/app/?source=marketplace");
    const assign = vi.fn();
    vi.stubGlobal("location", {
      ...window.location,
      assign,
      search: "?source=marketplace",
      href: `${window.location.origin}/app/?source=marketplace`,
      pathname: "/app/",
    });

    renderWithApp(<ConnectScreen />, { state: { phase: "connect" } });
    fireEvent.click(screen.getByRole("button", { name: /Connect Zoho CRM/i }));

    expect(assign).toHaveBeenCalledWith(ZOHO_MARKETPLACE_CONSENT_URL);
    expect(assign).not.toHaveBeenCalledWith(ZOHO_CONSENT_URL);
  });

  it("assigns marketplace consent from /app/ without a source query", () => {
    window.history.replaceState({}, "", "/app/");
    const assign = vi.fn();
    vi.stubGlobal("location", {
      ...window.location,
      assign,
      search: "",
      href: `${window.location.origin}/app/`,
      pathname: "/app/",
    });

    renderWithApp(<ConnectScreen />, { state: { phase: "connect" } });
    fireEvent.click(screen.getByRole("button", { name: /Connect Zoho CRM/i }));

    expect(assign).toHaveBeenCalledWith(ZOHO_MARKETPLACE_CONSENT_URL);
    expect(assign).not.toHaveBeenCalledWith(ZOHO_CONSENT_URL);
  });
});
