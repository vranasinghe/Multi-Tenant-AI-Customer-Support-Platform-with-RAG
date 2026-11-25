import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the real stack: Next.js (started here if not already running) and the
 * Dockerized API, Postgres, Redis and Mailpit (`docker compose up -d postgres redis mailpit
 * migrate api`). Nothing is mocked.
 *
 * Browser: an installed Chrome by default (`E2E_BROWSER_CHANNEL=msedge` for Edge, or empty to
 * use Playwright's bundled Chromium after `pnpm exec playwright install chromium`).
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const channel = process.env.E2E_BROWSER_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  outputDir: "test-results",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], ...(channel ? { channel } : {}) },
    },
  ],
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --port 3000",
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
