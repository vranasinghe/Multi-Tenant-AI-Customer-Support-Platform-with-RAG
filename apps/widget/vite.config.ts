import { defineConfig } from "vitest/config";

// Builds a single self-contained IIFE (`dist/loader.js`) that customers embed with one
// <script> tag. Kept dependency-free so it stays well under the 10 KB gzip budget (PRD FR-WID-1).
export default defineConfig({
  build: {
    lib: {
      entry: "src/loader.ts",
      name: "AcsChatWidget",
      formats: ["iife"],
      fileName: () => "loader.js",
    },
    target: "es2020",
    sourcemap: true,
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
