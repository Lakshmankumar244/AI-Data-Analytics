import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const CLIENT_PACKAGE_JSON = "client-package.json";

// catalyst.json points the client resource at this build directory, so the
// directory has to be a complete Catalyst deploy artifact:
//   - client-package.json is validated by the CLI next to index.html. It stays
//     at the package root (outside public/) because it is deploy configuration
//     rather than a served static asset.
//   - .gitkeep is tracked so the directory exists before the first build. The
//     CLI runs the pre-deploy/pre-serve script with this directory as its
//     working directory and cannot spawn it otherwise.
function catalystDeployArtifact() {
  let root;
  return {
    name: "catalyst-deploy-artifact",
    apply: "build",
    configResolved(config) {
      root = config.root;
    },
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: CLIENT_PACKAGE_JSON,
        source: readFileSync(resolve(root, CLIENT_PACKAGE_JSON), "utf8"),
      });
      this.emitFile({ type: "asset", fileName: ".gitkeep", source: "" });
    },
  };
}

export default defineConfig({
  // Catalyst web client hosting serves the app under /app.
  base: "/app/",
  plugins: [react(), tailwindcss(), catalystDeployArtifact()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "build",
    emptyOutDir: true,
  },
  server: {
    port: 3000,
  },
});
