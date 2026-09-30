import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { ThemeProvider } from "./theme/ThemeProvider.jsx";
import {
  captureMarketplaceEntry,
  launchMarketplaceAppIfFramed,
  restoreMarketplaceSearch,
} from "./data/marketplaceEntry";
import "./styles/global.css";

captureMarketplaceEntry();
restoreMarketplaceSearch();
if (launchMarketplaceAppIfFramed()) {
  // The Web Tab iframe must not run Catalyst login. Navigation continues top-level.
} else {
  const root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(
    <React.StrictMode>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </React.StrictMode>
  );
}
