import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

import { parsePublicEnv } from "./src/env";

const here = path.dirname(fileURLToPath(import.meta.url));

// Native runs (`pnpm dev:web`) share the monorepo-root .env with the API. Existing environment
// variables win; Docker builds have no root .env (excluded by .dockerignore) and pass values in.
const rootEnvFile = path.join(here, "../../.env");
if (existsSync(rootEnvFile)) process.loadEnvFile(rootEnvFile);

// NEXT_PUBLIC_* values are inlined at build time, so validate them when the config loads
// (dev server start and `next build`). Server-only variables are validated at runtime
// startup in src/instrumentation.ts.
parsePublicEnv({ NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL });

// Baseline response headers (docs/SECURITY.md §11). A nonce-based CSP is tracked separately; these
// already block framing (clickjacking), MIME sniffing and referrer leaks of one-time tokens.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  {
    key: "Content-Security-Policy",
    value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
  },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  output: "standalone",
  // Trace files from the monorepo root so workspace packages land in the standalone bundle.
  outputFileTracingRoot: path.join(here, "../.."),
  transpilePackages: ["@acs/ui", "@acs/shared-types"],
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
