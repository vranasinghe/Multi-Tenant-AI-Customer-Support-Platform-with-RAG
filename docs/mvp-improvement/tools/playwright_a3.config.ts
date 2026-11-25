// A3 local QA only: preserve localhost origins while avoiding a separate IPv6 dev server.
// Existing tests/assertions remain unchanged; use the already-running project Docker web/API.
import { resolve } from "node:path";
import base from "../../../apps/web/playwright.config";

export default {
  ...base,
  testDir: resolve(process.cwd(), "e2e"),
  outputDir: resolve(process.cwd(), "test-results"),
  webServer: undefined,
  use: {
    ...base.use,
    launchOptions: {
      ...base.use?.launchOptions,
      args: ["--host-resolver-rules=MAP localhost 127.0.0.1"],
    },
  },
};
