import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { resetMarketplaceEntryCapture } from "../data/marketplaceEntry";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetMarketplaceEntryCapture();
});


